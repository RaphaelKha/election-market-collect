"""Shared helpers: config, logging, yfinance download with retries, idempotent parquet merge."""
import datetime as dt
import logging
import os
import sys
import time
import warnings
from logging.handlers import RotatingFileHandler
from pathlib import Path

import pandas as pd
import yaml

import yfinance as yf

# yfinance 1.x triggers pandas 3 deprecation warnings ("inplace keyword") on every call: pure noise.
warnings.filterwarnings("ignore", message=".*inplace keyword.*")

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
LOGS = ROOT / "logs"
CONFIG_FILE = ROOT / "config.yaml"
DISABLED_FILE = ROOT / "disabled_tickers.yaml"

RETRIES = 4
BACKOFF_S = 5  # 5, 10, 20 s between attempts

log = logging.getLogger("collect")


def setup_logging():
    LOGS.mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s [%(script)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    script = Path(sys.argv[0]).stem
    logging.Formatter.converter = time.gmtime  # log timestamps in UTC like the data
    file_h = RotatingFileHandler(LOGS / "collect.log", maxBytes=5_000_000, backupCount=5)
    console_h = logging.StreamHandler()
    for h in (file_h, console_h):
        h.setFormatter(fmt)
        h.addFilter(lambda r: setattr(r, "script", script) or True)
        log.addHandler(h)
    log.setLevel(logging.INFO)
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)  # we log failures ourselves
    return log


def load_config():
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)


def past_cron_window(cfg):
    """True once we are past `collect_until` (stops yearly cron entries from firing in 2027)."""
    return dt.datetime.now(dt.timezone.utc).date() > dt.date.fromisoformat(str(cfg["collect_until"]))


def load_disabled():
    if not DISABLED_FILE.exists():
        return None
    with open(DISABLED_FILE) as f:
        return yaml.safe_load(f) or {}


def active_tickers(cfg):
    """[(group, ticker, prepost)] for every ticker not disabled. Runs the check on first launch."""
    disabled = load_disabled()
    if disabled is None:
        disabled = verify_tickers(cfg)
    out = []
    for group, spec in cfg["groups"].items():
        for t in spec["tickers"]:
            if t not in disabled:
                out.append((group, t, bool(spec.get("prepost", False))))
    return out


def verify_tickers(cfg):
    """Check every configured ticker returns data; write the dead ones to disabled_tickers.yaml."""
    log.info("Verifying tickers (first launch or --verify)...")
    disabled, no_daily = {}, []
    for group, spec in cfg["groups"].items():
        for t in spec["tickers"]:
            daily = safe_fetch(t, period="1mo", interval="1d", retries=2)
            intraday = safe_fetch(t, period="5d", interval="1m", retries=2)
            if daily is None and intraday is None:
                disabled[t] = f"no data from yfinance (group {group}, checked {dt.date.today()})"
                log.error("DEAD ticker %s (%s): disabled", t, group)
            elif daily is None or len(daily) < 5:
                no_daily.append(t)
                log.warning("%s (%s): intraday OK but no usable daily history on Yahoo", t, group)
            else:
                log.info("OK %s (%s)", t, group)
    with open(DISABLED_FILE, "w") as f:
        f.write("# Written by verify_tickers(). Tickers listed here are skipped by every collector.\n")
        f.write("# Delete this file (or run collect_intraday.py --verify) to re-check.\n")
        yaml.safe_dump(disabled, f, sort_keys=True)
    log.info("Verification done: %d dead %s, %d without daily history %s",
             len(disabled), sorted(disabled), len(no_daily), no_daily)
    for todo in cfg.get("todo", []):
        log.warning("TODO: %s", todo)
    return disabled


def fetch(ticker, retries=RETRIES, **kwargs):
    """yfinance history() with exponential backoff on transient errors. Raises after the last attempt.

    "No data" answers (holiday window, no daily history for that ticker) are final: not retried."""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            df = yf.Ticker(ticker).history(auto_adjust=False, actions=False, raise_errors=True, **kwargs)
            if not df.empty:
                return df
            raise RuntimeError(f"{ticker} {kwargs}: empty response")
        except yf.exceptions.YFPricesMissingError as e:
            raise RuntimeError(f"{ticker} {kwargs}: no data ({e})") from None
        except Exception as e:  # network errors, rate limits...
            last_err = f"{type(e).__name__}: {e}"
        if attempt < retries:
            time.sleep(BACKOFF_S * 2 ** (attempt - 1))
    raise RuntimeError(f"{ticker} {kwargs}: {last_err}")


def safe_fetch(ticker, retries=RETRIES, **kwargs):
    try:
        return fetch(ticker, retries=retries, **kwargs)
    except RuntimeError:
        return None


def to_utc(df):
    """Intraday bars: tz-aware UTC index."""
    df.index = df.index.tz_convert("UTC")
    df.index.name = "ts_utc"
    return df


def to_session_date(df):
    """Daily bars: naive local session date (converting to UTC would shift TASE dates to the day before)."""
    df.index = df.index.tz_localize(None).normalize()
    df.index.name = "date"
    return df


def merge_save(df, path):
    """Append idempotently: union with the existing file, newest download wins on duplicate timestamps."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        df = pd.concat([pd.read_parquet(path), df])
    df = df[~df.index.duplicated(keep="last")].sort_index()
    tmp = path.with_suffix(".parquet.tmp")
    df.to_parquet(tmp)
    os.replace(tmp, path)  # atomic: a crash never leaves a half-written file
    return len(df)
