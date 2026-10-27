"""Daily TASE vs US parity tracker on the common trading window (Yahoo 1m bars).

    python parity_track.py              # fetch the last 5 days of 1m bars, recompute, print the report
    python parity_track.py --no-fetch   # recompute from the bars already on disk

gap_bps = (US_price_USD / (TASE_agorot / 100 / USDILS * ratio) - 1) * 10_000, on minutes where both legs traded.
dev_bps = gap - trailing median of the gap (past minutes only), i.e. the move away from the usual bias.
Episode = consecutive minutes with |dev| > threshold on the same side. Only episodes lasting >= min_run_min
leave time to detect and execute both legs; 1-minute ones are mostly bid/ask bounce between last-trade prices,
which bars without quotes cannot tell apart from a real gap. So these counts are an upper bound.

Unlike the election collectors, this keeps running after collect_until: it refreshes the 1m files of its own
tickers only. Outputs: data/parity/gaps/<pair>.parquet (minute detail), data/parity/daily.csv (session x pair).
"""
import argparse

import pandas as pd

from common import DATA, fetch, load_config, merge_save, setup_logging, to_utc

log = setup_logging()
OUT = DATA / "parity"


def ticker_groups(cfg):
    return {t: (g, bool(s.get("prepost", False))) for g, s in cfg["groups"].items() for t in s["tickers"]}


def bars_path(cfg, ticker):
    return DATA / "intraday" / "1m" / ticker_groups(cfg)[ticker][0] / f"{ticker}.parquet"


def refresh(cfg, pcfg):
    """Same files and settings as collect_intraday.py, so both can write them (serialized by .collect.lock)."""
    groups = ticker_groups(cfg)
    failed = []
    for t in [pcfg["fx"]] + [x for us, p in pcfg["pairs"].items() for x in (us, p["tase"])]:
        try:
            df = to_utc(fetch(t, interval="1m", period="5d", prepost=groups[t][1]))
            log.info("parity fetch %-8s: +%d bars -> %d total", t, len(df), merge_save(df, bars_path(cfg, t)))
        except Exception as e:  # one ticker failing never stops the others
            failed.append(t)
            log.error("parity fetch %s: FAILED %s", t, e)
    return failed


def load_bars(cfg, ticker):
    df = pd.read_parquet(bars_path(cfg, ticker))
    df.index = pd.to_datetime(df.index, utc=True)
    df.columns = [c.lower() for c in df.columns]
    return df.sort_index()


def pair_gaps(us, tase, fx, ratio, bias_window):
    df = pd.concat({"us": us["close"], "us_v": us["volume"], "tase": tase["close"], "tase_v": tase["volume"]},
                   axis=1, join="inner")
    df = df[(df.us_v > 0) & (df.tase_v > 0)]  # both legs traded in that minute: no stale price
    # USD/ILS quotes have holes: last quote at most 5 minutes old
    df["fx"] = fx["close"].reindex(df.index, method="ffill", tolerance=pd.Timedelta("5min"))
    df = df.dropna(subset=["fx"])
    df["gap_bps"] = (df.us / (df.tase / 100 / df.fx * ratio) - 1) * 1e4
    df["bias_bps"] = df.gap_bps.rolling(bias_window, min_periods=30).median().shift()
    df["dev_bps"] = df.gap_bps - df.bias_bps
    return df.dropna(subset=["dev_bps"])


def episodes(dev, threshold):
    """Lengths in minutes of the runs of consecutive minutes with |dev| > threshold on the same side."""
    x = dev.asfreq("1min")  # a missing minute breaks the run
    side = (x > threshold).astype(int) - (x < -threshold).astype(int)
    run_id = (side != side.shift()).cumsum()
    return side[side != 0].groupby(run_id[side != 0]).size()


def session_rows(df, pair, thresholds, min_run):
    rows = []
    for day, d in df.groupby(df.index.date):
        r = {"date": day, "pair": pair, "minutes": len(d),
             "first_utc": d.index[0].strftime("%H:%M"), "last_utc": d.index[-1].strftime("%H:%M"),
             "gap_median_bps": round(d.gap_bps.median(), 1),
             "dev_abs_p95_bps": round(d.dev_bps.abs().quantile(.95), 1)}
        for t in thresholds:
            ep = episodes(d.dev_bps, t)
            r[f"pct_min_gt{t}"] = round((d.dev_bps.abs() > t).mean(), 4)
            r[f"episodes_gt{t}"] = len(ep)
            r[f"persistent_gt{t}"] = int((ep >= min_run).sum())
        rows.append(r)
    return rows


def report(daily, thresholds, min_run):
    last = daily.date.max()
    for title, d in ((f"Dernière séance ({last})", daily[daily.date == last]), ("Cumul", daily)):
        print(f"\n== {title}")
        print(f"{'paire':6} {'séances':>7} {'minutes':>7} {'biais méd':>9} {'|dev| p95':>9}  "
              + "  ".join(f"{'>' + str(t) + ' bps: %min / épis. / >=' + str(min_run) + 'min':>30}" for t in thresholds))
        for pair, g in d.groupby("pair"):
            cells = []
            for t in thresholds:
                pct = (g[f"pct_min_gt{t}"] * g.minutes).sum() / g.minutes.sum()
                cells.append(f"{pct:>12.1%} / {g[f'episodes_gt{t}'].sum():>5} / {g[f'persistent_gt{t}'].sum():>5}")
            print(f"{pair:6} {len(g):>7} {g.minutes.sum():>7} {g.gap_median_bps.median():>+9.1f} "
                  f"{g.dev_abs_p95_bps.median():>9.1f}  " + "  ".join(f"{c:>30}" for c in cells))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    pcfg = cfg["parity"]
    failed = [] if args.no_fetch else refresh(cfg, pcfg)

    fx = load_bars(cfg, pcfg["fx"])
    rows = []
    for us_t, p in pcfg["pairs"].items():
        df = pair_gaps(load_bars(cfg, us_t), load_bars(cfg, p["tase"]), fx, p["ratio"], pcfg["bias_window_min"])
        if df.empty:
            log.warning("parity %s: no common minute with both legs traded", us_t)
            continue
        merge_save(df, OUT / "gaps" / f"{us_t}.parquet")
        rows += session_rows(df, us_t, pcfg["thresholds_bps"], pcfg["min_run_min"])

    if not rows:
        return
    daily = pd.DataFrame(rows).sort_values(["date", "pair"])
    daily.to_csv(OUT / "daily.csv", index=False)
    report(daily, pcfg["thresholds_bps"], pcfg["min_run_min"])
    log.info("Parity run done: %d sessions, %d failed fetches %s", daily.date.nunique(), len(failed), failed)


if __name__ == "__main__":
    main()
