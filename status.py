"""Quick health check of the collected data.

    python status.py           # 1m intraday (the time-critical part) + last runs from the log
    python status.py --all     # every dataset under data/

Gap heuristics (intraday): weekdays with no bar at all between first and last day (holidays show up
here too, e.g. TASE closed on 27/10), and "partial" days with < 50% of the ticker's median bars/day
(today excluded, still in progress). Daily: gaps > 4 calendar days.
"""
import argparse
import datetime as dt

import pandas as pd

from common import DATA, LOGS

NOW = pd.Timestamp.now(tz="UTC")


def short_days(days, k=3):
    days = [d.strftime("%m-%d") for d in days]
    return ",".join(days[:k]) + (f"+{len(days) - k}" if len(days) > k else "")


def intraday_row(df):
    ts = df.index
    per_day = pd.Series(1, index=ts.normalize()).groupby(level=0).sum()
    weekdays = pd.bdate_range(per_day.index[0], per_day.index[-1], tz="UTC")
    empty = weekdays.difference(per_day.index)
    done = per_day[per_day.index < NOW.normalize()]
    partial = done[done < 0.5 * per_day.median()].index
    lag_h = (NOW - ts[-1]).total_seconds() / 3600
    gaps = []
    if len(empty):
        gaps.append(f"{len(empty)} j vides ({short_days(empty)})")
    if len(partial):
        gaps.append(f"{len(partial)} j partiels ({short_days(partial)})")
    return [len(df), ts[0].strftime("%Y-%m-%d %H:%M"), ts[-1].strftime("%Y-%m-%d %H:%M"), f"{lag_h:.1f}h", len(per_day), "; ".join(gaps) or "-"]


def daily_row(df):
    ts = df.index
    big = ts.to_series().diff().dt.days
    big = big[big > 4]
    gaps = f"{len(big)} trous >4j (max {int(big.max())}j, {big.idxmax().date()})" if len(big) else "-"
    return [len(df), ts[0].strftime("%Y-%m-%d"), ts[-1].strftime("%Y-%m-%d"), "", "", gaps]


def table(section, files):
    rows = []
    for f in files:
        try:
            df = pd.read_parquet(f, columns=[])
            row = intraday_row(df) if isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None else daily_row(df)
        except Exception as e:
            row = [0, "", "", "", "", f"ILLISIBLE: {e}"]
        rows.append([f.relative_to(section).with_suffix("").as_posix()] + row)
    if not rows:
        print(f"\n== {section.relative_to(DATA)}: aucun fichier")
        return
    out = pd.DataFrame(rows, columns=["fichier", "lignes", "premier (UTC)", "dernier (UTC)", "retard", "jours", "trous"])
    print(f"\n== {section.relative_to(DATA)} ({len(rows)} fichiers)")
    print(out.to_string(index=False))


def snapshot_dirs(section, pattern):
    """Point-in-time collections (options, polls): number of snapshots and the latest one per folder."""
    print(f"\n== {section.relative_to(DATA)}")
    dirs = sorted(d for d in section.glob("*") if d.is_dir()) if section.exists() else []
    if not dirs:
        print("  aucun fichier")
    for d in dirs:
        files = sorted(d.glob(pattern))
        print(f"  {d.name:<70.70} {len(files):>4} snapshots, dernier: {files[-1].stem if files else '-'}")


def last_runs():
    log_file = LOGS / "collect.log"
    if not log_file.exists():
        return
    lines = [ln.rstrip() for ln in log_file.read_text().splitlines() if " done" in ln or "DEAD" in ln]
    print("\n== dernières fins de run (logs/collect.log)")
    for ln in lines[-5:]:
        print(" ", ln)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    print(f"Maintenant: {NOW:%Y-%m-%d %H:%M} UTC")
    sections = [DATA / "intraday" / "1m"]
    if args.all:
        sections += [DATA / "intraday" / "5m", DATA / "intraday" / "1h", DATA / "daily"]
        sections += sorted((DATA / "elections").glob("*")) + sorted((DATA / "prediction_markets" / "polymarket").glob("*/*"))
    for s in sections:
        table(s, sorted(s.rglob("*.parquet")))
    snapshot_dirs(DATA / "options", "*.parquet")
    snapshot_dirs(DATA / "polls" / "wikipedia", "*.wikitext")
    last_runs()


if __name__ == "__main__":
    main()
