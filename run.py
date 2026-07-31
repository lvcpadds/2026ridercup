"""
Orchestrator: guard the window -> scrape -> merge -> recompute -> inject -> push.
This is what cron/launchd calls every 15 minutes.
"""
import json, sys, subprocess
from datetime import datetime
import config, model, scrape, update_html


def within_window():
    if not config.ENFORCE_WINDOW:
        return True
    now = datetime.now()
    if now.strftime("%Y-%m-%d") != config.RUN_DATE:
        return False
    start = datetime.strptime(f"{config.RUN_DATE} {config.RUN_START}", "%Y-%m-%d %H:%M")
    end = datetime.strptime(f"{config.RUN_DATE} {config.RUN_END}", "%Y-%m-%d %H:%M")
    return start <= now <= end


def load_history():
    with open(config.HISTORY_JSON, encoding="utf-8") as f:
        return json.load(f)


def save_history(h):
    with open(config.HISTORY_JSON, "w", encoding="utf-8") as f:
        json.dump(h, f, indent=1)


def merge_round(history, scraped, round_no):
    """Fold this round's scraped points into each player's history at position round_no."""
    idx = round_no - 1
    added, updated, unseen = 0, 0, 0
    for name, pts in scraped.items():
        rounds = history.setdefault(name, [None] * config.TOTAL_EVENTS)
        while len(rounds) < config.TOTAL_EVENTS:
            rounds.append(None)
        if rounds[idx] is None:
            added += 1
        else:
            updated += 1
        rounds[idx] = pts
    scraped_names = set(scraped)
    for name in history:
        if name not in scraped_names:
            unseen += 1
    print(f"  merged R{round_no}: {added} new, {updated} updated, {unseen} not in this pull")
    return history


def git_push():
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = config.GIT_COMMIT_MSG.format(round=config.CURRENT_ROUND, stamp=stamp)
    cwd = config.GIT_REPO_DIR
    try:
        subprocess.run(["git", "add", "-A"], cwd=cwd, check=True)
        # nothing changed? don't make an empty commit
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=cwd)
        if diff.returncode == 0:
            print("  no changes to push.")
            return
        subprocess.run(["git", "commit", "-m", msg], cwd=cwd, check=True)
        subprocess.run(["git", "push", "origin", config.GIT_BRANCH], cwd=cwd, check=True)
        print(f"  pushed: {msg}")
    except subprocess.CalledProcessError as e:
        print(f"  !! git step failed: {e}")


def main():
    force = "--force" in sys.argv          # ignore the date/time window
    no_push = "--no-push" in sys.argv       # do everything except git push (safe test)
    sample = "--sample" in sys.argv         # use randomized fake scores instead of scraping

    if not force and not within_window():
        print(f"[{datetime.now():%H:%M}] outside run window — skipping.")
        return

    print(f"[{datetime.now():%H:%M}] run start (R{config.CURRENT_ROUND})"
          f"{' [SAMPLE]' if sample else ''}{' [NO-PUSH]' if no_push else ''}")

    if sample:
        scraped = _sample_scores()
        print(f"  generated {len(scraped)} randomized sample scores")
    else:
        # MUST run headed — Golf Genius blocks headless (returns a blank page).
        scraped = scrape.scrape(headless=False)
        if not scraped:
            print("  scrape returned 0 players — aborting (session or selectors may need a look).")
            return
        print(f"  scraped {len(scraped)} players")

    history = load_history()
    history = merge_round(history, scraped, config.CURRENT_ROUND)
    if not sample:                          # never persist fake data into real history
        save_history(history)

    static_ranks = json.load(open(config.STATIC_RANKS, encoding="utf-8"))
    main_data = model.compute(history, static_ranks)
    rounds_data = update_html.rounds_data_from_history(history)
    path = update_html.update(main_data, rounds_data)
    print(f"  wrote {path} ({len(main_data)} ranked players)")

    if no_push or sample:
        print("  (skipping git push)")
    else:
        git_push()
    print(f"[{datetime.now():%H:%M}] done.")


def _sample_scores():
    """Randomized-but-realistic R6 scores for the field, for end-to-end testing.
    Draws each player's fake score from their own historical range so nothing is absurd."""
    import random
    hist = load_history()
    out = {}
    for name, rounds in hist.items():
        played = [v for v in rounds[:5] if v is not None]
        if not played:
            continue
        lo, hi = min(played), max(played)
        out[name] = round(random.uniform(lo, hi) * 2) / 2  # nearest 0.5
    return out


if __name__ == "__main__":
    main()
