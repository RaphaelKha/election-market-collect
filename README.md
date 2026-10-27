**English** · [עברית](README.he.md)

# Markets around the 2026 Israeli election 🇮🇱

This repository holds the code I use to **watch financial markets around the election for the 26th Knesset on 27 October 2026**. The study has two parts:

1. **How markets react to the election.** I track the shekel, the Tel Aviv Stock Exchange (TASE), Israeli companies listed in New York, and prediction markets as the results come in.
2. **The Tel Aviv / New York price gap.** Several Israeli companies are listed in both places. Converted into dollars, the two prices should be the same. I measure, minute by minute, how far apart they drift and how long the gap lasts, to see whether it would leave room for arbitrage once trading costs are paid.

This is a **personal observation and research project**. The code places no orders, and nothing here is investment advice.

> This README was published before the exit polls (27 Oct 2026, 20:00 UTC), on purpose: it states the questions before the answers are known.

---

## Why this window

- On election day, **27 Oct 2026**, the **TASE is closed** (public holiday). US markets are open.
- The **exit polls** are released when voting ends, at 22:00 Israel time, i.e. **20:00 UTC**. That is **exactly the New York close** (16:00 ET). The first market reaction should therefore show up in the US after-hours trading of Israeli stocks, before Tel Aviv reopens.
- Much of this data **cannot be downloaded later**. Yahoo keeps 1-minute bars for only a few weeks and keeps no history of option chains, so they have to be recorded as they happen.

---

## Part 1: data collected around the election (26–31 Oct 2026)

| Category | What is tracked | Frequency |
|---|---|---|
| FX | USD/ILS, EUR/ILS, US dollar index (DXY) | 1-minute bars, fetched hourly |
| Tel Aviv | TA-35 and TA-125 indices; Leumi, Hapoalim, Discount and Mizrahi-Tefahot banks; Teva, Elbit Systems, NICE, ICL | 1 minute |
| Israeli stocks in New York | TEVA, ESLT, CHKP, NICE, ICL, plus the EIS ETF (iShares MSCI Israel), including pre- and after-market | 1 minute |
| Israeli government bonds | Tel-Gov indices (all, 0–2y, 2–5y, 5–10y, CPI-linked) | 1 minute |
| Volatility | VTA35 (TA-35 volatility), VIX9D, GVZ (gold), OVX (oil) | 1 minute |
| Benchmarks | S&P 500, Nasdaq, VIX, bitcoin, gold, WTI crude | 1 minute |
| Options | full chains (calls and puts, expiries up to 31 Dec 2026) on TEVA, CHKP, ESLT, NICE, ICL | hourly snapshot |
| Polymarket | 12 election events (next prime minister, largest party, seat counts, blocs, coalition…), 189 markets in total | 1-minute prices |
| Polls | Wikipedia polling and election pages, saved at every new revision | hourly |

**Schedule (UTC)**
- Every hour: 1-minute bars (:05), options (:20), Polymarket (:35), polls (:50).
- Election night (27 Oct): an options snapshot at 19:50, just before the exit polls, then a full pass at 20:15.
- 30 Oct, 22:00: a final snapshot of longer histories (5-minute, hourly and daily bars).
- These jobs stop on their own after 31 Oct.

`collect_history.py` also downloads daily prices around **past Knesset elections**, so that this reaction can be compared with earlier ones.

---

## Part 2: Tel Aviv / New York price gap (`parity_track.py`)

### Method

A Teva share bought in Tel Aviv and a Teva share bought in New York are the same security, so their dollar prices should match. For every minute in which **the stock actually traded in both places**:

```
TASE price in USD = (TASE price in agorot / 100) / USDILS × ratio
gap (basis points) = (New York price / TASE price in USD − 1) × 10,000
```

One basis point (bp) is 0.01%.

A small, stable gap is normal (fees, taxes, the usual direction of flows). What matters is the **deviation from the usual gap**: the current gap minus its median over the previous 300 common minutes.

An **episode** is a run of consecutive minutes in which that deviation stays beyond a threshold, on the same side. Three thresholds are tested, 20, 40 and 60 bp, standing for different round-trip trading costs. Only episodes lasting **at least 3 minutes** count, since shorter ones leave no time to trade both legs.

### Pairs

| New York | Tel Aviv | Ratio |
|---|---|---|
| TEVA | TEVA.TA | 1 : 1 (ordinary shares on both exchanges since 14 Sep 2026) |
| NICE | NICE.TA | 1 : 1 (to re-check against the latest 20-F) |
| ESLT | ESLT.TA | 1 : 1 (to be verified) |
| ICL | ICL.TA | 1 : 1 (to be verified) |

Check Point (CHKP) is not listed in Tel Aviv, so it is left out of this part.

### Common trading window

The two exchanges are open at the same time for only a short period each day:
- about **1 hour** (13:30–14:30 UTC) until 23 Oct;
- about **2 hours** (13:30–15:30 UTC) since Israel moved to winter time on 25 Oct;
- about 1 hour again from 1 Nov, when the US moves to winter time.

On Fridays the Tel Aviv session ends before New York opens, so there is no common window.

Tracking started on 5 Oct 2026 and runs **every weekday at 21:30 UTC**, after the US close, **beyond 31 Oct**.

### Limitations

- Gaps are computed from the **last traded price** of each minute, not from bid and ask quotes. Some one-minute gaps are just trades bouncing between the bid and the ask, so the counts are an **upper bound**.
- The exchange rate is Yahoo's USD/ILS quote, which is not necessarily a tradable rate.
- Several ratios still need to be confirmed (see the pairs table).
- Yahoo Finance data is unofficial and can have holes.

---

## Questions this study asks

1. How did the shekel, the TASE, Israeli stocks in New York and Israeli government bonds react around 20:00 UTC on 27 Oct?
2. Who priced the result in first: Polymarket, the shekel, or Israeli stocks in New York?
3. How did the implied volatility of options on Israeli stocks change before and after the vote?
4. Does the Tel Aviv / New York price gap widen around the election, and does it ever stay wide enough, for long enough, to cover trading costs?
5. How does this reaction compare with previous Knesset elections?

---

## What will be published, and when

- **Now:** the method and the code (this repository).
- **Later, once collection is over:** the collected data and the analysis that answers the questions above.

The data (`data/`) and logs (`logs/`) are not in the repository for now. They stay on the collection server.

---

## Repository layout

| File | Purpose |
|---|---|
| `config.yaml` | tickers, Polymarket events, Wikipedia pages, price-gap settings |
| `collect_intraday.py` | 1-minute bars (Yahoo keeps about 7 days) |
| `collect_options.py` | hourly option-chain snapshots |
| `collect_polymarket.py` | Polymarket price histories (public API, no key) |
| `collect_polls.py` | copies of the Wikipedia polling and election pages |
| `collect_snapshots.py` | longer histories (5-minute, hourly, daily) |
| `collect_history.py` | daily prices around past elections |
| `parity_track.py` | daily tracking of the Tel Aviv / New York price gap |
| `parity_check.py` | first, one-off version of the gap analysis |
| `status.py` | health check: latest data point, missing days, latest runs |
| `common.py` | shared helpers (config, logging, downloads with retries, duplicate-free merges) |

---

## Setup

Tested with Python 3.12.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python status.py                    # collection status
.venv/bin/python parity_track.py              # Tel Aviv / New York gap (fetches the last 5 days)
.venv/bin/python parity_track.py --no-fetch   # recompute from data already on disk
```

Scheduled jobs run with `cron` on a Linux server set to UTC. With `--cron`, the collectors do nothing after the `collect_until` date in `config.yaml`.
