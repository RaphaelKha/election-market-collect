**English** · [עברית](README.he.md)

# Election Night Tape 🇮🇱

**Markets around the election for the 26th Knesset, 27 October 2026.** This repository holds the code I use to record, minute by minute, how the shekel, the Tel Aviv Stock Exchange (TASE), Israeli companies listed in New York and prediction markets moved as the results came in.

This is a **personal observation and research project**. The code places no orders, and nothing here is investment advice.

> **What was published before the results, and what was not.** The questions at the end of this page were published on 27 Oct 2026 at 08:59 UTC, before the exit polls (commit `7403a52`). The measurement method below was written on 28 Oct 2026 around 09:00 UTC, **after** the exit polls. It is not pre-registered and should be read with that in mind.

Companion project: [**TA–NY Parity Monitor**](https://github.com/RaphaelKha/TA-NY-parity-monitor), the minute-by-minute price gap between Tel Aviv and New York for dual-listed Israeli stocks. It started as Part 2 of this repository and now lives on its own.

---

## Why this window

- On election day, **27 Oct 2026**, the **TASE is closed** (public holiday). US markets are open.
- The **exit polls** are released when voting ends, at 22:00 Israel time, i.e. **20:00 UTC**. That is **exactly the New York close** (16:00 ET). The first market reaction should therefore show up in the US after-hours trading of Israeli stocks, before Tel Aviv reopens.
- Much of this data **cannot be downloaded later**. Yahoo keeps 1-minute bars for only a few weeks and keeps no history of option chains, so they have to be recorded as they happen.

---

## Data collected (26–31 Oct 2026)

| Category | What is tracked | Frequency |
|---|---|---|
| FX | USD/ILS, EUR/ILS, US dollar index (DXY) | 1-minute bars, fetched hourly |
| Tel Aviv | TA-35 and TA-125 indices; Leumi, Hapoalim, Discount and Mizrahi-Tefahot banks; Teva, Elbit Systems, NICE, ICL | 1 minute |
| Israeli stocks in New York | TEVA, ESLT, CHKP, NICE, ICL, plus the EIS ETF (iShares MSCI Israel), including pre- and after-market | 1 minute |
| Israeli government bonds | Tel-Gov indices (all, 0–2y, 2–5y, 5–10y, CPI-linked) | 1 minute |
| Volatility | VTA35 (TA-35 volatility), VIX9D, GVZ (gold), OVX (oil) | 1 minute |
| Benchmarks | S&P 500, Nasdaq, VIX, bitcoin, gold, WTI crude | 1 minute |
| Options | full chains (calls and puts, expiries up to 31 Dec 2026) on TEVA, CHKP, ESLT, NICE, ICL | hourly snapshot |
| Polymarket | 12 election events (next prime minister, largest party, seat counts, blocs, coalition…), 189 markets in total | 1-minute prices (**see the incident below**) |
| Polls | Wikipedia polling and election pages, saved at every new revision | hourly |

**Schedule (UTC)**
- Every hour: 1-minute bars (:05), options (:20), Polymarket (:35), polls (:50).
- Election night (27 Oct): an options snapshot at 19:50, just before the exit polls, then a full pass at 20:15.
- 30 Oct, 22:00: a final snapshot of longer histories (5-minute, hourly and daily bars).
- These jobs stop on their own after 31 Oct.

`collect_history.py` also downloads daily prices around **past Knesset elections**, so that this reaction can be compared with earlier ones.

### Incident: Polymarket collection interrupted from 28 Oct, 08:42 UTC

- **What happened.** From 28 Oct 2026 at 08:42 UTC, Polymarket's metadata API (`gamma-api`, which maps each election event to its markets) answered every request from the collection server with **HTTP 429 "Too Many Requests"**. Without that mapping, the collector could not ask for prices, and recorded nothing.
- **What was not affected.** Election night is complete. Up to the last successful run (28 Oct, 07:35 UTC), no market has more than about 5 minutes between two recorded prices, including around the exit polls (27 Oct, 20:00 UTC).
- **What it was not.** Polymarket itself kept running. During the block, its website and its price-history API (`clob`) answered normally. The block was on this server's requests, not a market closure, so it says nothing about trading activity on Polymarket during that time.
- **Cause.** The block covered the whole `gamma-api` domain for this server's IP address (HTTP 429 from CloudFront, on every endpoint, with no `Retry-After`), and it was still in place on 1 Nov. `clob` was never blocked.
- **What was done.** Polymarket keeps full price histories, so the missing period can be fetched after the fact. The event-to-market mapping (`markets.json`: 12 events, 189 markets) was built once from another network and copied to the server; the prices themselves still come from `clob`, fetched by the server. `collect_polymarket.py` now spaces its requests 1 s apart, retries a 429 with exponential backoff, and `--recover` keeps per-market progress so that an interrupted run resumes where it stopped. It refetches 1-minute prices from 28 Oct 00:00 UTC onward.
- **Status:** *backfill in progress since 1 Nov 2026* (first event done: 8 markets, no error). To be updated here with the date it completes and any minutes that could not be recovered.

---

## Method: measuring the reaction

Written on 28 Oct 2026, after the exit polls (see the note at the top).

**Primary endpoints.** Only these get a significance claim; every other series or window checked is exploratory and reported as such.

| Series | Window | Statistic |
|---|---|---|
| USD/ILS | 15 min after 20:00 UTC | cumulative log return |
| TA-35 | first 5 min after Tel Aviv reopens | opening-gap return |
| ADR basket (TEVA, ESLT, NICE, ICL, CHKP), after-hours | 15 min after 20:00 UTC | average cumulative log return |
| Polymarket "largest party" market | from 20:00 UTC | time of first sustained move (see below) |

**Abnormal move.** For a window of length *h* minutes starting at the event time $t_0$:

```math
r_h(t_0) \;=\; \ln \frac{P(t_0 + h)}{P(t_0)}
```

The null: compute the same statistic, same clock time, same *h*, on every other trading day in the 1-minute history (28 Sep onward, election day excluded): the control sample, of size *N* (about 20 days). Rank $r_h(t_0)$ for 27 Oct inside that sample and report the empirical two-sided p-value $p = \text{rank} / (N + 1)$. With *N* ≈ 20, that is the honest resolution available (coarse, multiples of about 5%); no normal-distribution p-value is claimed on a sample this small.

**Who moved first.** For each primary series, find the first minute $t \ge$ 20:00 UTC where the move since $t_0$ is large relative to that series' own recent noise, and stays large:

```math
T_s \;=\; \min\left\{ t \ge t_0 \;:\; \frac{\left|r(t_0, t)\right|}{\sigma \sqrt{t - t_0}} > 2 \ \text{for 2 consecutive minutes} \right\}
```

where σ is the standard deviation of 1-minute log returns over the 60 minutes ending just before 20:00 UTC. One minute above the threshold is noise, not a signal. Rank the $T_s$ across series and report pairwise gaps in minutes. Limitation: Polymarket trades continuously while Yahoo bars are minute-binned, so a lead or lag of a minute or two can be a reporting artifact, not a real one.

**Implied volatility, before and after** (`compute_iv.py`). From the hourly option-chain snapshots, on the near-the-money contract (strike closest to spot) at the nearest expiry at least 7 days after 27 Oct: invert Black-Scholes on the bid/ask mid, call and put averaged, with a constant 4% US risk-free rate and no dividend yield. No Tel Aviv option data is collected, so this is a US-market IV on the ADR, not a TASE one (flagged, not corrected). Track IV at every hourly snapshot from 25 Oct 00:00 to 29 Oct 00:00 UTC. Report the event jump $IV(\text{20:15}) - IV(\text{19:50})$ and the one-day move $IV(+24\text{h}) - IV(-24\text{h})$, each ranked against the hour-to-hour IV changes of the three preceding weeks, as for the abnormal move above.

**Comparison with 2019 and 2020.** Daily bars only (`collect_history.py`), so day 0 = first trading session after each election:

```math
\mathrm{CAR}[0, k] \;=\; \sum_{d=0}^{k} r_d \quad (k = 1, 3), \qquad \text{effect size} \;=\; \frac{\mathrm{CAR}[0, k]}{\sigma_{30}}
```

where $r_d$ is the daily log return and $\sigma_{30}$ the realized volatility over the 30 sessions before day 0; reported for TA-35 and USD/ILS. With only two past elections as reference, this is **descriptive, not a statistical test**, and no p-value is attached.

**Caveats that apply to the method, not just to the data:** the control-day sample mixes pre-campaign and campaign-close days, which are not a clean null; a handful of series (bonds, GVZ/OVX, individual ADRs beyond the basket) will be looked at but are exploratory by the rule above, however suggestive they turn out to be.

---

## Questions this study asks

As published before the exit polls; a fourth question, on the Tel Aviv / New York gap, moved to [TA–NY Parity Monitor](https://github.com/RaphaelKha/TA-NY-parity-monitor).

1. How did the shekel, the TASE, Israeli stocks in New York and Israeli government bonds react around 20:00 UTC on 27 Oct?
2. Who priced the result in first: Polymarket, the shekel, or Israeli stocks in New York?
3. How did the implied volatility of options on Israeli stocks change before and after the vote?
4. How does this reaction compare with previous Knesset elections?

---

## What will be published, and when

- **Now:** the questions, the method and the code (this repository).
- **Once collection is over and the Polymarket backfill is done:** the collected data and the analysis that answers the questions above.

The data (`data/`) and logs (`logs/`) are not in the repository for now. They stay on the collection server.

---

## Repository layout

| File | Purpose |
|---|---|
| `config.yaml` | tickers, Polymarket events, Wikipedia pages |
| `collect_intraday.py` | 1-minute bars (Yahoo keeps about 7 days) |
| `collect_options.py` | hourly option-chain snapshots |
| `collect_polymarket.py` | Polymarket price histories (public API, no key); `--recover` for the backfill |
| `collect_polls.py` | copies of the Wikipedia polling and election pages |
| `collect_snapshots.py` | longer histories (5-minute, hourly, daily) |
| `collect_history.py` | daily prices around past elections |
| `compute_iv.py` | Black-Scholes implied volatility from the option-chain snapshots |
| `status.py` | health check: latest data point, missing days, latest runs |
| `common.py` | shared helpers (config, logging, downloads with retries, duplicate-free merges) |

---

## Setup

Tested with Python 3.12.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/python status.py                     # collection status
.venv/bin/python compute_iv.py                 # implied volatility from the option snapshots
.venv/bin/python collect_polymarket.py --recover   # Polymarket backfill (no-op once done)
```

Scheduled jobs run with `cron` on a Linux server set to UTC. With `--cron`, the collectors do nothing after the `collect_until` date in `config.yaml`; `--recover` is not limited by that date.
