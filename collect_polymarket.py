"""Polymarket Israeli-election events (config.yaml polymarket.event_slugs): YES price history per market.

Public APIs, no key: gamma-api (event -> markets/tokens) and clob /prices-history (price series).
Output: data/prediction_markets/polymarket/{event_slug}/{1m,1h}/{market}.parquet, index ts_utc, column price.

    python collect_polymarket.py          # last 3 days at 1-minute fidelity (hourly cron)
    python collect_polymarket.py --full   # whole history at 1h + last ~29 days at 1m (one-off)
    python collect_polymarket.py --cron   # no-op after collect_until
    python collect_polymarket.py --full --only <slug> ...   # backfill newly added events
    python collect_polymarket.py --recover  # 1m since polymarket.recover_from, until one clean run

The event -> token mapping is cached in markets.json after the first successful gamma-api call, so
routine runs only hit clob. gamma-api has blocked this server's IP (HTTP 429 from CloudFront, no
Retry-After, every endpoint) since 2026-10-28 08:42 UTC, so markets.json may have to be built
elsewhere and copied here. Requests are spaced by MIN_INTERVAL_S; a 429 is retried with exponential
backoff (or Retry-After when given) and ends the run once retries are exhausted. --recover keeps
per-market progress in .recover_progress.json and resumes from it.
"""
import argparse
import datetime as dt
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

from common import BACKOFF_S, DATA, RETRIES, load_config, merge_save, past_cron_window, setup_logging

log = setup_logging()

GAMMA = "https://gamma-api.polymarket.com/events?slug="
CLOB = "https://clob.polymarket.com/prices-history?"
OUT = DATA / "prediction_markets" / "polymarket"
MARKETS_CACHE = OUT / "markets.json"
RECOVERED = OUT / ".recovered"
RECOVER_PROGRESS = OUT / ".recover_progress.json"
MIN_INTERVAL_S = 1.0      # between any two requests
RATE_LIMIT_BACKOFF_S = 30  # 30, 60, 120 s after a 429 without Retry-After
MAX_RETRY_AFTER_S = 600    # a longer Retry-After ends the run instead of sleeping

_last_request = 0.0


class RateLimited(Exception):
    pass


def retry_after_s(e):
    try:
        return float(e.headers.get("Retry-After"))
    except (TypeError, ValueError):
        return None


def get_json(url):
    global _last_request
    for attempt in range(1, RETRIES + 1):
        time.sleep(max(0.0, _last_request + MIN_INTERVAL_S - time.monotonic()))
        _last_request = time.monotonic()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "election-market-collect"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429:
                if attempt == RETRIES:
                    raise
                log.warning("GET failed (%s), retry %d: %s", e, attempt, url)
                time.sleep(BACKOFF_S * 2 ** (attempt - 1))
                continue
            wait = retry_after_s(e)
            if wait is None:
                wait = RATE_LIMIT_BACKOFF_S * 2 ** (attempt - 1)
            if attempt == RETRIES or wait > MAX_RETRY_AFTER_S:
                raise RateLimited(url) from None
            log.warning("HTTP 429 (Retry-After %s), waiting %.0f s, retry %d: %s",
                        e.headers.get("Retry-After"), wait, attempt, url)
            time.sleep(wait)
        except Exception as e:
            if attempt == RETRIES:
                raise
            log.warning("GET failed (%s), retry %d: %s", e, attempt, url)
            time.sleep(BACKOFF_S * 2 ** (attempt - 1))


def event_markets(slug, cache, refresh):
    """[{name, token, start}] for the event's markets, from the cache unless refresh or not cached yet."""
    if slug in cache and not refresh:
        return cache[slug]
    markets = []
    for m in get_json(GAMMA + slug)[0]["markets"]:
        tokens = json.loads(m.get("clobTokenIds") or "[]")
        if tokens:  # tokens[0] = YES (outcomes are ["Yes", "No"])
            markets.append({"name": m.get("groupItemTitle") or m["question"], "token": tokens[0],
                            "start": m.get("startDate") or m["createdAt"]})
    cache[slug] = markets
    MARKETS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    MARKETS_CACHE.write_text(json.dumps(cache, indent=1))
    return markets


def price_history(token, start, end, fidelity):
    q = urllib.parse.urlencode(dict(market=token, startTs=int(start.timestamp()), endTs=int(end.timestamp()), fidelity=fidelity))
    hist = get_json(CLOB + q).get("history", [])
    if not hist:
        return pd.DataFrame(columns=["price"])
    df = pd.DataFrame(hist).rename(columns={"p": "price"})
    df.index = pd.to_datetime(df.pop("t"), unit="s", utc=True).rename("ts_utc")
    return df


def windows(start, end, step_days):
    while start < end:
        yield start, min(start + dt.timedelta(days=step_days), end)
        start += dt.timedelta(days=step_days)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--cron", action="store_true")
    ap.add_argument("--only", nargs="+", help="subset of event slugs")
    ap.add_argument("--recover", action="store_true", help="1m since polymarket.recover_from; no-op once done")
    args = ap.parse_args()

    cfg = load_config()
    if args.cron and past_cron_window(cfg):
        log.info("Past collect_until=%s, nothing to do", cfg["collect_until"])
        return
    if args.recover and RECOVERED.exists():
        log.info("Polymarket recovery already done (%s), nothing to do", RECOVERED)
        return

    slugs = args.only or cfg["polymarket"]["event_slugs"]
    now = dt.datetime.now(dt.timezone.utc)
    if args.recover:
        start_1m = pd.Timestamp(cfg["polymarket"]["recover_from"]).to_pydatetime()
    else:
        start_1m = now - dt.timedelta(days=29 if args.full else 3)
    # (resolution, fidelity in minutes, start, window size in days)
    jobs = [("1m", 1, start_1m, 3)]
    cache = json.loads(MARKETS_CACHE.read_text()) if MARKETS_CACHE.exists() else {}
    # --recover resumes: markets already backfilled by an earlier (interrupted) run are skipped
    done = set(json.loads(RECOVER_PROGRESS.read_text())) if args.recover and RECOVER_PROGRESS.exists() else set()
    n_markets, n_skipped, failed = 0, 0, []
    try:
        for slug in slugs:
            try:
                markets = event_markets(slug, cache, refresh=args.full)
            except RateLimited:
                raise
            except Exception as e:
                failed.append(slug)
                log.error("polymarket event %s: FAILED %s", slug, e)
                continue
            for m in markets:
                fname = re.sub(r"[^a-z0-9]+", "_", m["name"].lower()).strip("_")
                key = f"{slug}/{fname}"
                if key in done:
                    n_skipped += 1
                    continue
                n_markets += 1
                market_jobs = list(jobs)
                if args.full:
                    market_jobs.append(("1h", 60, pd.Timestamp(m["start"]).to_pydatetime(), 14))
                try:
                    for res, fidelity, start, step in market_jobs:
                        parts = [price_history(m["token"], a, b, fidelity) for a, b in windows(start, now, step)]
                        parts = [p for p in parts if not p.empty]
                        if not parts:
                            continue
                        df = pd.concat(parts)
                        n = merge_save(df, OUT / slug / res / f"{fname}.parquet")
                        log.info("polymarket %-3s %.30s / %-20.20s: +%d pts -> %d, last p=%.3f", res, slug, m["name"], len(df), n, df["price"].iloc[-1])
                    if args.recover:
                        done.add(key)
                        RECOVER_PROGRESS.write_text(json.dumps(sorted(done), indent=1))
                except RateLimited:
                    raise
                except Exception as e:
                    failed.append(f"{slug}/{m['name']}")
                    log.error("polymarket %s / %s: FAILED %s", slug, m["name"], e)
    except RateLimited as e:
        log.error("polymarket: HTTP 429 on %s after %d tries, stopping this run", e, RETRIES)
        failed.append("rate-limited")
    log.info("Polymarket done: %d events, %d markets, %d skipped (already recovered), %d failed %s",
             len(slugs), n_markets, n_skipped, len(failed), failed)
    # complete only when every configured event is mapped and all its markets are done (not just --only)
    all_keys = {f"{s}/{re.sub(r'[^a-z0-9]+', '_', m['name'].lower()).strip('_')}"
                for s in cfg["polymarket"]["event_slugs"] for m in cache.get(s, [])}
    complete = all(s in cache for s in cfg["polymarket"]["event_slugs"]) and all_keys <= done
    if args.recover and not failed and complete:
        RECOVERED.write_text(f"{now.isoformat()}\n")
        log.info("Polymarket recovery complete: 1m since %s", start_1m)


if __name__ == "__main__":
    main()
