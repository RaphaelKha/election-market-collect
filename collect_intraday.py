"""Hourly 1m collection. yfinance keeps 1m bars for ~7 days (30 via date ranges): download and merge.

    python collect_intraday.py              # period=7d for every active ticker
    python collect_intraday.py --backfill   # also 1m from ~29 days ago, in 7-day chunks (one-off)
    python collect_intraday.py --verify     # re-check tickers, rewrite disabled_tickers.yaml
    python collect_intraday.py --cron       # no-op after collect_until (used by crontab)
"""
import argparse
import datetime as dt

from common import DATA, active_tickers, fetch, load_config, merge_save, past_cron_window, setup_logging, to_utc, verify_tickers

log = setup_logging()


def backfill_ranges():
    today = dt.datetime.now(dt.timezone.utc).date()
    # 28, not 29: Yahoo's 30-day limit is checked against local midnight, which TASE (UTC+3) overshoots at 29.
    return [(today - dt.timedelta(days=lo), today - dt.timedelta(days=lo - 7)) for lo in (28, 21, 14)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--cron", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    if args.cron and past_cron_window(cfg):
        log.info("Past collect_until=%s, nothing to do", cfg["collect_until"])
        return
    if args.verify:
        verify_tickers(cfg)

    tickers = active_tickers(cfg)
    log.info("1m run start: %d tickers%s", len(tickers), " (+backfill)" if args.backfill else "")
    failed = []
    for group, t, prepost in tickers:
        path = DATA / "intraday" / "1m" / group / f"{t}.parquet"
        requests = [dict(period="7d")]
        if args.backfill:
            requests += [dict(start=a, end=b) for a, b in backfill_ranges()]
        for req in requests:
            try:
                df = to_utc(fetch(t, interval="1m", prepost=prepost, **req))
                n = merge_save(df, path)
                log.info("%-10s %-6s %s: +%d bars -> %d total, last %s", t, group, req, len(df), n, df.index[-1])
            except Exception as e:  # one ticker failing never stops the others
                failed.append(t)
                log.error("%s %s: FAILED %s", t, req, e)
    log.info("1m run done: %d ok, %d failed %s", len(tickers) - len(set(failed)), len(set(failed)), sorted(set(failed)))


if __name__ == "__main__":
    main()
