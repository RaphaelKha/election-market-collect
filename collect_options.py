"""Hourly option-chain snapshots (implied vol around the election). Point-in-time: Yahoo keeps no history.

One file per ticker and run: data/options/{ticker}/{YYYYmmddTHHMM}.parquet (calls + puts, all expiries
<= options.max_expiry), with the underlying price at snapshot time.

    python collect_options.py
    python collect_options.py --cron   # no-op after collect_until
"""
import argparse
import datetime as dt

import pandas as pd
import yfinance as yf

from common import DATA, load_config, past_cron_window, setup_logging

log = setup_logging()

COLS = ["contractSymbol", "strike", "bid", "ask", "lastPrice", "lastTradeDate", "volume", "openInterest", "impliedVolatility"]


def snapshot(ticker, max_expiry):
    tk = yf.Ticker(ticker)
    underlying = tk.fast_info["last_price"]
    parts = []
    for exp in tk.options:
        if exp > max_expiry:
            continue
        chain = tk.option_chain(exp)
        for kind, df in (("call", chain.calls), ("put", chain.puts)):
            parts.append(df[COLS].assign(expiry=exp, type=kind))
    df = pd.concat(parts, ignore_index=True)
    df["underlying"] = underlying
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cron", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    if args.cron and past_cron_window(cfg):
        log.info("Past collect_until=%s, nothing to do", cfg["collect_until"])
        return

    now = dt.datetime.now(dt.timezone.utc)
    failed = []
    for t in cfg["options"]["tickers"]:
        try:
            df = snapshot(t, str(cfg["options"]["max_expiry"]))
            df["snapshot_utc"] = pd.Timestamp(now)
            path = DATA / "options" / t / f"{now:%Y%m%dT%H%M}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(path, index=False)
            log.info("options %-5s: %d contracts, %d expiries, underlying %.2f", t, len(df), df["expiry"].nunique(), df["underlying"].iloc[0])
        except Exception as e:
            failed.append(t)
            log.error("options %s: FAILED %s", t, e)
    log.info("Options run done: %d failed %s", len(failed), failed)


if __name__ == "__main__":
    main()
