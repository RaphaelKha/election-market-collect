"""Polymarket Israeli-election events (config.yaml polymarket.event_slugs): YES price history per market.

Public APIs, no key: gamma-api (event -> markets/tokens) and clob /prices-history (price series).
Output: data/prediction_markets/polymarket/{event_slug}/{1m,1h}/{market}.parquet, index ts_utc, column price.

    python collect_polymarket.py          # last 3 days at 1-minute fidelity (hourly cron)
    python collect_polymarket.py --full   # whole history at 1h + last ~29 days at 1m (one-off)
    python collect_polymarket.py --cron   # no-op after collect_until
    python collect_polymarket.py --full --only <slug> ...   # backfill newly added events
"""
import argparse
import datetime as dt
import json
import re
import time
import urllib.parse
import urllib.request

import pandas as pd

from common import BACKOFF_S, DATA, RETRIES, load_config, merge_save, past_cron_window, setup_logging

log = setup_logging()

GAMMA = "https://gamma-api.polymarket.com/events?slug="
CLOB = "https://clob.polymarket.com/prices-history?"
OUT = DATA / "prediction_markets" / "polymarket"


def get_json(url):
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "election-market-collect"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as e:
            if attempt == RETRIES:
                raise
            log.warning("GET failed (%s), retry %d: %s", e, attempt, url)
            time.sleep(BACKOFF_S * 2 ** (attempt - 1))


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
    args = ap.parse_args()

    cfg = load_config()
    if args.cron and past_cron_window(cfg):
        log.info("Past collect_until=%s, nothing to do", cfg["collect_until"])
        return

    slugs = args.only or cfg["polymarket"]["event_slugs"]
    now = dt.datetime.now(dt.timezone.utc)
    # (resolution, fidelity in minutes, start, window size in days)
    jobs = [("1m", 1, now - dt.timedelta(days=29 if args.full else 3), 3)]
    n_markets, failed = 0, []
    for slug in slugs:
        try:
            markets = get_json(GAMMA + slug)[0]["markets"]
        except Exception as e:
            failed.append(slug)
            log.error("polymarket event %s: FAILED %s", slug, e)
            continue
        for m in markets:
            name = m.get("groupItemTitle") or m["question"]
            fname = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
            tokens = json.loads(m.get("clobTokenIds") or "[]")
            if not tokens:
                continue
            n_markets += 1
            market_jobs = list(jobs)
            if args.full:
                created = pd.Timestamp(m.get("startDate") or m["createdAt"]).to_pydatetime()
                market_jobs.append(("1h", 60, created, 14))
            try:
                for res, fidelity, start, step in market_jobs:
                    # tokens[0] = YES (outcomes are ["Yes", "No"])
                    parts = [price_history(tokens[0], a, b, fidelity) for a, b in windows(start, now, step)]
                    parts = [p for p in parts if not p.empty]
                    if not parts:
                        continue
                    df = pd.concat(parts)
                    n = merge_save(df, OUT / slug / res / f"{fname}.parquet")
                    log.info("polymarket %-3s %.30s / %-20.20s: +%d pts -> %d, last p=%.3f", res, slug, name, len(df), n, df["price"].iloc[-1])
            except Exception as e:
                failed.append(f"{slug}/{name}")
                log.error("polymarket %s / %s: FAILED %s", slug, name, e)
    log.info("Polymarket done: %d events, %d markets, %d failed %s", len(slugs), n_markets, len(failed), failed)


if __name__ == "__main__":
    main()
