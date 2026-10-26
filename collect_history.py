"""Daily bars around past Knesset elections, for the estimation window and cross-election comparison.

Downloads a calendar window wide enough to contain >= 150 sessions before and >= 10 sessions after
each election for every market (TASE traded Sun-Thu until 2026, so session counts differ by market);
trimming to [-150, +10] sessions is left to the analysis.

    python collect_history.py                  # all elections
    python collect_history.py --only 2026-10-27  # e.g. rerun mid-November to get the 2026 post-event days
"""
import argparse
import datetime as dt

from common import DATA, active_tickers, fetch, load_config, merge_save, setup_logging, to_session_date

log = setup_logging()

ELECTIONS = ["2019-04-09", "2019-09-17", "2020-03-02", "2021-03-23", "2022-11-01", "2026-10-27"]
DAYS_BEFORE = 240  # calendar days, ~165 US sessions
DAYS_AFTER = 20    # calendar days, ~13 US sessions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="+", default=ELECTIONS)
    args = ap.parse_args()

    tickers = active_tickers(load_config())
    for election in args.only:
        day = dt.date.fromisoformat(election)
        start, end = day - dt.timedelta(days=DAYS_BEFORE), day + dt.timedelta(days=DAYS_AFTER)
        ok, missing = 0, []
        for group, t, _ in tickers:
            try:
                df = to_session_date(fetch(t, start=start, end=end, interval="1d"))
                df["group"] = group
                merge_save(df, DATA / "elections" / election / f"{t}.parquet")
                before, after = (df.index < str(day)).sum(), (df.index > str(day)).sum()
                log.info("%s %-10s: %d sessions before, %d after", election, t, before, after)
                ok += 1
            except Exception as e:
                missing.append(t)
                log.warning("%s %s: no data (%s)", election, t, e)
        log.info("Election %s: %d tickers ok, %d without data %s", election, ok, len(missing), missing)


if __name__ == "__main__":
    main()
