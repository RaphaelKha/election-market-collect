"""Black-Scholes implied vol from the hourly option-chain snapshots, on the near-the-money contract.

    python compute_iv.py             # every ticker in options.tickers
    python compute_iv.py TEVA ESLT   # just these

For each ticker, the target expiry is fixed once (nearest available expiry >= election_date +
options_iv.min_days_after_event), so the term structure doesn't shift under the comparison. At every
snapshot, picks the strike closest to that snapshot's underlying price, and averages the call and put
IV at that strike (put-call parity: should roughly agree, and averaging damps one noisy quote).

No scipy: a vol=0.5 Newton start, falling back to bisection (bs_price is monotonic in sigma) since some
quotes are thin enough that Newton can overshoot.

Limitation (see README): constant risk-free rate, no dividend yield, US-listed options only (no TASE
option data is collected) -> this is a US-market IV on the ADR, not a Tel Aviv one.
"""
import argparse
import math

import pandas as pd

from common import DATA, load_config, setup_logging

log = setup_logging()
OUT = DATA / "options_iv"


def norm_cdf(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def norm_pdf(x):
    return math.exp(-0.5 * x * x) / math.sqrt(2 * math.pi)


def bs_price(spot, strike, t, r, sigma, kind):
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma * sigma) * t) / (sigma * math.sqrt(t))
    d2 = d1 - sigma * math.sqrt(t)
    if kind == "call":
        return spot * norm_cdf(d1) - strike * math.exp(-r * t) * norm_cdf(d2)
    return strike * math.exp(-r * t) * norm_cdf(-d2) - spot * norm_cdf(-d1)


def vega(spot, strike, t, r, sigma):
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma * sigma) * t) / (sigma * math.sqrt(t))
    return spot * norm_pdf(d1) * math.sqrt(t)


def implied_vol(price, spot, strike, t, r, kind, lo=1e-3, hi=5.0):
    sigma = 0.5
    for _ in range(50):
        step = (bs_price(spot, strike, t, r, sigma, kind) - price) / vega(spot, strike, t, r, sigma)
        sigma -= step
        if not (lo < sigma < hi):
            break
        if abs(step) < 1e-6:
            return sigma
    if bs_price(spot, strike, t, r, lo, kind) > price or bs_price(spot, strike, t, r, hi, kind) < price:
        return None  # quote outside what any vol in [lo, hi] can produce (crossed/stale bid-ask)
    for _ in range(80):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if bs_price(spot, strike, t, r, mid, kind) < price else (lo, mid)
    return (lo + hi) / 2


def target_expiry(expiries, event_date, min_days):
    threshold = pd.Timestamp(event_date).tz_localize(None) + pd.Timedelta(days=min_days)
    candidates = sorted(e for e in expiries if pd.Timestamp(e) >= threshold)
    return candidates[0] if candidates else max(expiries)


def snapshot_iv(df, expiry, r, max_cp_disagreement=0.15):
    """Both call and put at the chosen strike must quote, and their IVs must roughly agree (put-call
    parity): a single quoted leg, or two that disagree a lot, usually means a stale or crossed quote
    rather than a real vol level, so it's dropped rather than averaged into noise."""
    d = df[df.expiry == expiry]
    if d.empty:
        return None
    spot = d.underlying.iloc[0]
    snapshot_utc = d.snapshot_utc.iloc[0]
    t = (pd.Timestamp(expiry).tz_localize("UTC") + pd.Timedelta(hours=21) - snapshot_utc) / pd.Timedelta(days=365.25)
    if t <= 0:
        return None
    d = d[(d.bid > 0) & (d.ask > 0)].assign(mid=lambda x: (x.bid + x.ask) / 2)
    both = d.groupby("strike").type.nunique()
    strikes = both[both == 2].index
    if strikes.empty:
        return None
    strike = min(strikes, key=lambda s: abs(s - spot))
    row = d[d.strike == strike]
    ivs = {}
    for kind in ("call", "put"):
        iv = implied_vol(row[row.type == kind].mid.iloc[0], spot, strike, t, r, kind)
        if iv is None:
            return None
        ivs[kind] = iv
    if abs(ivs["call"] - ivs["put"]) > max_cp_disagreement:
        return None
    return {"snapshot_utc": snapshot_utc, "expiry": expiry, "strike": strike, "underlying": spot,
            "t_years": t, "call_iv": ivs["call"], "put_iv": ivs["put"],
            "iv": (ivs["call"] + ivs["put"]) / 2, "moneyness": strike / spot}


def report(out, event_ts):
    before, after = out[out.snapshot_utc <= event_ts], out[out.snapshot_utc > event_ts]
    if before.empty or after.empty:
        return
    b, a = before.iv.iloc[-1], after.iv.iloc[0]
    print(f"    exit-poll jump: {b:.1%} ({before.snapshot_utc.iloc[-1]:%m-%d %H:%M}) -> "
          f"{a:.1%} ({after.snapshot_utc.iloc[0]:%m-%d %H:%M}), {((a - b) * 1e4):+.0f} bp")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="*")
    args = ap.parse_args()

    cfg = load_config()
    ocfg = cfg.get("options_iv", {})
    r = ocfg.get("risk_free_rate", 0.04)
    min_days = ocfg.get("min_days_after_event", 7)
    event_ts = pd.Timestamp(cfg["election_date"], tz="UTC") + pd.Timedelta(hours=20)
    tickers = args.tickers or cfg["options"]["tickers"]

    for t in tickers:
        files = sorted((DATA / "options" / t).glob("*.parquet"))
        if not files:
            log.warning("iv %s: no snapshots", t)
            continue
        expiry = target_expiry(pd.read_parquet(files[0]).expiry.unique(), event_ts.normalize(), min_days)
        rows = [snapshot_iv(pd.read_parquet(f), expiry, r) for f in files]
        rows = [row for row in rows if row is not None]
        if not rows:
            log.warning("iv %s: no usable quote at expiry %s", t, expiry)
            continue
        out = pd.DataFrame(rows).sort_values("snapshot_utc")
        OUT.mkdir(parents=True, exist_ok=True)
        out.to_parquet(OUT / f"{t}.parquet", index=False)
        log.info("iv %-5s: %d/%d snapshots usable, expiry %s, latest %.1f%%", t, len(out), len(files), expiry, out.iv.iloc[-1] * 100)
        report(out, event_ts)


if __name__ == "__main__":
    main()
