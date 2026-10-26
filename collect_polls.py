"""Wikipedia polling / election pages: saves the raw wikitext of every new revision.

Polls table (all Israeli pollsters), leadership polls, and the election page where exit polls and
results are posted on election night. Parsing is left to the analysis repo. Wikipedia keeps every
revision, so a missed run loses nothing: this is a convenience copy with collection timestamps.
Output: data/polls/wikipedia/{page}/{revision timestamp}_{revid}.wikitext

    python collect_polls.py
    python collect_polls.py --cron   # no-op after collect_until
"""
import argparse
import json
import re
import time
import urllib.parse
import urllib.request

from common import BACKOFF_S, DATA, RETRIES, load_config, past_cron_window, setup_logging

log = setup_logging()

API = "https://en.wikipedia.org/w/api.php?"
OUT = DATA / "polls" / "wikipedia"


def latest_revision(title):
    q = urllib.parse.urlencode(dict(action="query", prop="revisions", rvprop="ids|timestamp|content", rvslots="main",
                                    format="json", formatversion=2, titles=title))
    for attempt in range(1, RETRIES + 1):
        try:
            req = urllib.request.Request(API + q, headers={"User-Agent": "election-market-collect (research project)"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)["query"]["pages"][0]["revisions"][0]
        except Exception as e:
            if attempt == RETRIES:
                raise
            log.warning("wikipedia GET failed (%s), retry %d", e, attempt)
            time.sleep(BACKOFF_S * 2 ** (attempt - 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cron", action="store_true")
    args = ap.parse_args()

    cfg = load_config()
    if args.cron and past_cron_window(cfg):
        log.info("Past collect_until=%s, nothing to do", cfg["collect_until"])
        return

    failed = []
    for title in cfg["wikipedia_pages"]:
        try:
            rev = latest_revision(title)
            page_dir = OUT / re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_")
            path = page_dir / f"{rev['timestamp'].replace(':', '')}_{rev['revid']}.wikitext"
            if path.exists():
                log.info("wikipedia %-60.60s: unchanged (rev %s)", title, rev["revid"])
                continue
            page_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(rev["slots"]["main"]["content"])
            log.info("wikipedia %-60.60s: new rev %s (%s)", title, rev["revid"], rev["timestamp"])
        except Exception as e:
            failed.append(title)
            log.error("wikipedia %s: FAILED %s", title, e)
    log.info("Polls run done: %d failed %s", len(failed), failed)


if __name__ == "__main__":
    main()
