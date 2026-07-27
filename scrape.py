"""
Scrape the current-round net points off the Golf Genius leaderboard.

AUTH MODEL (Option A): the bot drives REAL Chrome using a dedicated profile
folder (./chrome_profile) that carries your Golf Genius magic-link session.
You authenticate that profile ONCE via `python scrape.py --login`; every run
after that reuses the saved session headlessly. No passwords in the code.

Order of operations the first time:
  1) python scrape.py --login     # opens Chrome, you get logged in, saves session
  2) python scrape.py --inspect   # now authenticated, dumps the real table layout
  3) (fill the 3 selectors below to match what --inspect shows)
  4) python scrape.py --headed    # confirm it reads ~74 players
"""
import sys, os, json, re
import config
from playwright.sync_api import sync_playwright

PROFILE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chrome_profile")


def _run(fn, headless=True):
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(
            PROFILE_DIR,
            channel="chrome",          # use real Google Chrome, not bundled Chromium
            headless=headless,
            viewport={"width": 1400, "height": 1000},
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            return fn(pw, ctx, page)
        finally:
            ctx.close()


def _clean_name(raw):
    raw = re.sub(r"\s+", " ", raw).strip()
    if "," in raw:
        return raw
    parts = raw.split(" ")
    return f"{parts[-1]}, {' '.join(parts[:-1])}" if len(parts) >= 2 else raw


def _to_points(raw):
    raw = raw.strip().replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def login():
    """One-time: open real Chrome so you can authenticate; session is saved."""
    def _fn(pw, ctx, page):
        page.goto(config.LEADERBOARD_URL, wait_until="domcontentloaded", timeout=60000)
        print("\n>>> A Chrome window just opened.")
        print(">>> If the leaderboard shows, you're already logged in — skip to Enter.")
        print(">>> If not: in that window (or your email) get your magic link.")
        print(">>> You can paste the magic-link URL here and I'll open it for you,")
        print(">>> or just finish logging in inside the window itself.\n")
        link = input("Paste magic-link URL (or leave blank if already in): ").strip()
        if link:
            page.goto(link, wait_until="domcontentloaded", timeout=60000)
        input("\nWhen you can SEE the leaderboard in the window, press Enter to save... ")
        print(f"Session stored in {PROFILE_DIR}")
    _run(_fn, headless=False)


def inspect():
    """Dump the real DOM so we can wire selectors. Runs authenticated + headless."""
    def _fn(pw, ctx, page):
        page.goto(config.LEADERBOARD_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(3000)
        html = page.content()
        open("leaderboard_debug.html", "w", encoding="utf-8").write(html)
        page.screenshot(path="leaderboard_debug.png", full_page=True)
        print(f"Page HTML length: {len(html)}  (saved leaderboard_debug.html)")

        tables = page.query_selector_all("table")
        print(f"\nMain document: {len(tables)} <table>(s).")
        for ti, t in enumerate(tables):
            rows = t.query_selector_all("tr")
            print(f"  TABLE {ti}: {len(rows)} rows")
            for r in rows[:3]:
                cells = [c.inner_text().strip()[:22] for c in r.query_selector_all("th,td")]
                print("     ", cells)

        # Golf Genius often renders inside an iframe — scan those too.
        for fi, fr in enumerate(page.frames):
            if fr == page.main_frame:
                continue
            ftables = fr.query_selector_all("table")
            if ftables:
                print(f"\n  IFRAME {fi} ({fr.url[:50]}...): {len(ftables)} table(s)")
                for ti, t in enumerate(ftables):
                    rows = t.query_selector_all("tr")
                    print(f"    TABLE {ti}: {len(rows)} rows")
                    for r in rows[:3]:
                        cells = [c.inner_text().strip()[:22] for c in r.query_selector_all("th,td")]
                        print("       ", cells)

        # If no <table> anywhere, GG may use div-rows — surface repeated structures.
        if not tables:
            print("\nNo <table> found — looking for repeated row-like containers:")
            candidates = page.eval_on_selector_all(
                "*",
                """els => {
                    const counts = {};
                    els.forEach(e => {
                      if (e.children.length >= 5) {
                        const kids = [...e.children].map(c => c.tagName+'.'+(c.className||'').split(' ')[0]);
                        const sig = kids[0];
                        counts[e.tagName+'>'+sig] = (counts[e.tagName+'>'+sig]||0)+1;
                      }
                    });
                    return Object.entries(counts).sort((a,b)=>b[1]-a[1]).slice(0,8);
                }"""
            )
            for sig, n in candidates:
                print(f"   {n:>4}x  {sig}")
        print("\nDone. Paste this output back to finish the selectors.")
    _run(_fn, headless=True)


def scrape(headless=True, round_no=None):
    """Pull the Mens League Points (net points) standings for one round.

    The leaderboard lives inside an <iframe> (tournament_results widget), not
    the top-level page. Its "Select a Date" <select id="round"> holds one
    option per round (e.g. "Round 5 at The Club (Sat, ...)"); picking one
    reloads that iframe's section contents. Each section (Player Points
    Summary, Mens League Points, Gross Score, ...) is a collapsed
    div.tournament_container with an <h2 class="tournament"> header — clicking
    its a.expand-tournament link AJAX-loads a table.result_scope with one
    tr.aggregate-row per player (name in td.name a.open-aggregate-details,
    net points in td.points).
    """
    round_no = config.CURRENT_ROUND if round_no is None else round_no

    def _fn(pw, ctx, page):
        page.goto(config.LEADERBOARD_URL, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(2500)

        frame = next(f for f in page.frames if "tournament_results" in f.url)

        # ---- select the target round in the "Select a Date" dropdown ----
        select_el = frame.query_selector("select#round")
        target_value = None
        for opt in select_el.query_selector_all("option"):
            if re.search(rf"\bRound {round_no}\b", opt.inner_text()):
                target_value = opt.get_attribute("value")
                break
        if target_value is None:
            raise RuntimeError(f"No 'Round {round_no}' option found in the date dropdown.")
        select_el.select_option(value=target_value)
        page.wait_for_timeout(4000)

        # ---- expand the Mens League Points section ----
        container = frame.locator(
            "div.tournament_container",
            has=frame.locator("h2.tournament", has_text="Men's League Points"),
        )
        container.locator("a.expand-tournament").click()

        # ---- wait for its results table to render ----
        rows = container.locator("table.result_scope tr.aggregate-row")
        rows.first.wait_for(timeout=15000)
        page.wait_for_timeout(1000)

        out = {}
        for i in range(rows.count()):
            row = rows.nth(i)
            n = row.locator("td.name a.open-aggregate-details")
            pt = row.locator("td.points")
            if n.count() == 0 or pt.count() == 0:
                continue
            name = _clean_name(n.inner_text())
            pts = _to_points(pt.inner_text())
            if name and pts is not None:
                out[name] = pts
        return out
    return _run(_fn, headless=headless)


if __name__ == "__main__":
    if "--login" in sys.argv:
        login()
    elif "--inspect" in sys.argv:
        inspect()
    else:
        data = scrape(headless="--headed" not in sys.argv)
        print(json.dumps(data, indent=2))
        print(f"\n{len(data)} players scraped.")
