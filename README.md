# Rider Cup bot

Auto-pulls the Golf Genius leaderboard, recomputes the projection model, and
pushes the updated standings page to GitHub Pages. Built to run every 15 minutes
on **Friday July 31, 8:00 AM – 3:00 PM MT** and then get out of your way.

## Files
| File | Job |
|---|---|
| `config.py` | Every knob you touch weekly (URL, round #, repo path). Start here. |
| `scrape.py` | Playwright scraper. **Has the one on-device TODO** (selectors). |
| `model.py` | The best-5-of-7 + regression model. Same math as the HTML. |
| `update_html.py` | Swaps the `mainData`/`roundsData` consts in the site file. |
| `run.py` | Orchestrator cron calls. Window guard → scrape → merge → push. |
| `bootstrap_history.py` | Run **once** to seed `history.json` from the current HTML. |
| `history.json` | Banked per-round points. The bot maintains it after bootstrap. |
| `static_ranks.json` | Pro Shop + Steve ranks (don't change week to week). |
| `site/…html` | The page that gets injected and pushed. |

## One-time setup (on the Mac Mini)

```bash
cd riderscup_bot
python3 -m venv .venv && source .venv/bin/activate
pip install playwright
python -m playwright install chromium
```

1. **Edit `config.py`** — paste `LEADERBOARD_URL`, set `GIT_REPO_DIR` to your local
   Pages clone, and make sure `site/…html` lives inside that repo (move it there
   and update `HTML_TEMPLATE` if needed).
2. **Seed history:** `python bootstrap_history.py`
3. **Finish the scraper** (the only part I couldn't write blind):
   ```bash
   python scrape.py --inspect
   ```
   This prints every table on the page and saves `leaderboard_debug.png`.
   Hand both to Claude Code — *"fill in ROW_SELECTOR / NAME_SELECTOR /
   POINTS_SELECTOR in scrape.py to match this table"* — and it'll wire the three
   selectors to the real DOM. Then confirm:
   ```bash
   python scrape.py --headed      # watch it work; should print ~74 players
   ```
4. **Dry run the whole chain** without waiting for Friday:
   ```bash
   python run.py --force
   ```
   Check the site file updated and `git log` shows the commit.

## Schedule it (cron)

`crontab -e`, then:
```
# Rider Cup — every 15 min, 8a–3p, Jul 31 only
*/15 8-14 31 7 * cd /Users/landon/riderscup_bot && .venv/bin/python run.py >> bot.log 2>&1
0    15   31 7 * cd /Users/landon/riderscup_bot && .venv/bin/python run.py >> bot.log 2>&1
```
The `run.py` window guard is belt-and-suspenders: even if cron fires early it
refuses to run outside the date/time in `config.py`. Tail `bot.log` to watch.

> macOS note: give `cron` (and your terminal) Full Disk Access in System
> Settings → Privacy, or use `launchd` instead — happy to hand you a `.plist`.

## Each following week (30 seconds)
Bump `CURRENT_ROUND`, drop `REMAINING_EVENTS` by one, update the `RUN_*` window.
That's it — the model and push logic don't change.

## Design notes
- **History is the source of truth.** A live pull only sees the current round;
  `history.json` holds R1–R5 so the model always recomputes on the full picture.
- **Idempotent.** Re-scraping the same round overwrites that round's cell — running
  twice never double-counts. And an unchanged page produces no git commit.
- **`REMAINING_EVENTS` is the number that bit us before.** It's the count of events
  *after* the one being scraped — everyone shares it, regardless of rounds played.
