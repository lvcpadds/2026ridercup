"""
Round tee-sheet tracker — daily count + who's new since the baseline.

Round-aware: reads the tee-sheet URL for config.CURRENT_ROUND from
config.TEE_SHEET_URLS, and names its baseline/snapshot files per round so
Round 6 and Round 7 never collide. For Round 7 you just add its URL to
config.TEE_SHEET_URLS, set CURRENT_ROUND = 7, and run the same command.

  python tee_sheet.py             # scrape today's sheet, print count + new names
  python tee_sheet.py --baseline  # (re)set the baseline to today's list

Reuses the authenticated Chrome profile + _run + _clean_name from scrape.py.

>>> ONE ON-DEVICE TODO: the row + name selectors in fetch_tee_sheet (below).
    Have Claude Code wire them against the live page, same as the results page.
"""
import sys, os, json
from datetime import date
import config
from scrape import _run, _clean_name

ROUND = config.CURRENT_ROUND
URL = config.TEE_SHEET_URLS.get(ROUND)
BASELINE = f"tee_sheet_r{ROUND}_baseline.json"
SNAPSHOTS = f"tee_sheet_r{ROUND}_snapshots.json"


def fetch_tee_sheet():
    """Return the set of player names on this round's tee sheet.

    The page lives inside an <iframe> (next_round widget). Its roster is one
    <table class="attending_roster_table">, with each <tr> holding up to four
    <td class="name"><strong>Last, First</strong></td> cells (one foursome per
    row). Flattening every td.name across every row — not just the first row —
    is what catches the whole roster.
    """
    def _fn(pw, ctx, page):
        page.goto(URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2500)

        frame = next(f for f in page.frames if "next_round" in f.url)
        frame.wait_for_selector("table.attending_roster_table td.name", timeout=15000)

        names = set()
        for cell in frame.query_selector_all("table.attending_roster_table td.name"):
            nm = _clean_name(cell.inner_text())
            if nm:
                names.add(nm)
        return names
    return _run(_fn, headless=False)


def load_json(path, default):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else default


def main():
    if not URL:
        print(f"No tee-sheet URL for Round {ROUND}. Add it to "
              f"config.TEE_SHEET_URLS[{ROUND}].")
        return

    current = fetch_tee_sheet()
    if not current:
        print("Nothing scraped — check the URL and the selectors in fetch_tee_sheet.")
        return

    baseline = load_json(BASELINE, None)
    if baseline is None or "--baseline" in sys.argv:
        json.dump(sorted(current), open(BASELINE, "w"), indent=1)
        print(f"Round {ROUND} baseline set to today's list: {len(current)} players.")
        baseline = sorted(current)

    baseline_set = set(baseline)
    new_since_baseline = sorted(current - baseline_set)
    dropped = sorted(baseline_set - current)

    snaps = load_json(SNAPSHOTS, {})
    prev = sorted(snaps.keys())
    new_since_yesterday = sorted(current - set(snaps[prev[-1]])) if prev else []

    snaps[str(date.today())] = sorted(current)
    json.dump(snaps, open(SNAPSHOTS, "w"), indent=1)

    print(f"\n=== Round {ROUND} tee sheet — {date.today()} ===")
    print(f"Total signed up: {len(current)}   (baseline was {len(baseline_set)})")
    if new_since_baseline:
        print(f"\nNEW since baseline ({len(new_since_baseline)}):")
        for n in new_since_baseline:
            print(f"  + {n}")
    else:
        print("\nNo new names since baseline.")
    if new_since_yesterday:
        print(f"\nNew since last check ({len(new_since_yesterday)}):")
        for n in new_since_yesterday:
            print(f"  + {n}")
    if dropped:
        print(f"\nDropped off since baseline ({len(dropped)}):")
        for n in dropped:
            print(f"  - {n}")


if __name__ == "__main__":
    main()
