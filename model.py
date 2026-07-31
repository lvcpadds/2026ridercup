"""
The projection model — best-5-of-7 with regression-to-mean.
This is the same logic baked into the HTML, kept in one place so the
scraper and the site never drift apart.
"""
import json
import os
import config


def _load_baseline():
    """Frozen pre-Round-6 ranks, so the Round 6 Tracker can show movement.
    Missing file just means zero movement (rankBaseline == current rank)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "baseline_ranks.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}



def best_n(scores, n=config.BEST_N):
    """Sum of the best n scores (the drop math)."""
    s = sorted(scores, reverse=True)
    return round(sum(s[:n]), 1)


def field_mean_pace(history):
    """Average per-round pace across everyone who's played — the regression anchor."""
    paces = []
    for rounds in history.values():
        vals = [v for v in rounds if v is not None]
        if vals:
            paces.append(sum(vals) / len(vals))
    return sum(paces) / len(paces) if paces else 55.0


def shrink_k(played):
    """Tiered regression strength: fewer rounds -> pull harder toward the mean."""
    if played >= 4:
        return 2
    if played == 3:
        return 5
    return 8  # 2 rounds


def compute(history, static_ranks):
    """
    history: {name: [r1, r2, ... rN]}  (None allowed for missed rounds)
    static_ranks: {name: {'proRank':.., 'steveRank':..}}
    returns: list of mainData dicts, ranked.
    """
    fmean = field_mean_pace(history)

    rows = []
    for name, rounds in history.items():
        scores = [v for v in rounds if v is not None]
        played = len(scores)
        if played < 2:
            continue  # not enough to rank

        # Remaining = how many of the two final events (R6, R7) this player
        # hasn't posted yet: 2 before R6, 1 once R6 is in, 0 after both.
        final_slots = list(rounds[5:7]) + [None] * (2 - len(rounds[5:7]))
        rem = sum(1 for v in final_slots if v is None)

        total = round(sum(scores), 1)
        raw_pace = sum(scores) / played
        k = shrink_k(played)
        weight = played / (played + k)
        adj_pace = round(weight * raw_pace + (1 - weight) * fmean, 2)

        floor = best_n(scores + [20.0] * rem)
        ceiling = best_n(scores + [100.0] * rem)
        projection = best_n(scores + [adj_pace] * rem)

        rows.append({
            "name": name, "played": played, "total": total,
            "pace": round(raw_pace, 1), "adjPace": adj_pace,
            "weight": round(weight, 2), "worst": round(min(scores), 1),
            "worst_incomplete": False,
            "floor": floor, "ceiling": ceiling, "projection": projection,
        })

    # Rank by adjusted pace projection, with the hard small-sample cap:
    # no 2-round player may crack the top 60 no matter how hot.
    def sort_key(p):
        penalty = 0 if p["played"] >= 3 else 1  # 2-round guys sink below the proven field
        return (penalty, -p["projection"], -p["total"])
    rows.sort(key=sort_key)

    for i, p in enumerate(rows, 1):
        p["rank"] = i
        p["isYou"] = False
        p["tier"], p["comment"] = _tier_and_comment(p)

    # Pro Shop rank = strict total-points rank (recomputed live as scores post).
    for i, p in enumerate(sorted(rows, key=lambda x: -x["total"]), 1):
        p["proRank"] = i
    # Steve's unofficial rank stays frozen at its Week-5 snapshot.
    for p in rows:
        p["steveRank"] = static_ranks.get(p["name"], {}).get("steveRank")

    # Avg Rank = clean integer ordinal ranking of the blended average (no dupes/decimals).
    for p in rows:
        vals = [v for v in [p["rank"], p["proRank"], p["steveRank"]] if v is not None]
        p["avgMean"] = round(sum(vals) / len(vals), 1) if vals else None
    ordered = sorted(rows, key=lambda p: (p["avgMean"] if p["avgMean"] is not None else 9999,
                                          p["rank"], p["name"]))
    for i, p in enumerate(ordered, 1):
        p["avgRank"] = i

    # Frozen pre-R6 rank so the Round 6 Tracker can show movement.
    baseline = _load_baseline()
    for p in rows:
        p["rankBaseline"] = baseline.get(p["name"], p["rank"])

    return rows


def _tier_and_comment(p):
    ceil, floor, proj = p["ceiling"], p["floor"], p["projection"]
    if ceil < 300:
        t = "TOAST"
    elif ceil < 320:
        t = "NEEDS_MIRACLE"
    elif floor >= 320:
        t = "LOCK"
    elif proj >= 320:
        t = "COMFORTABLE"
    elif proj >= 300:
        t = "PROBABLE"
    elif proj >= 280:
        t = "BUBBLE"
    else:
        t = "LONGSHOT"

    pools = {
        "LOCK": ["Mathematically bulletproof — go pick out the team polo.",
                 "Could three-putt through August and still waltz in.",
                 "Already decided. Send Justin your shirt size."],
        "COMFORTABLE": ["Would need a name-it-after-you collapse to miss this.",
                        "In, barring a full meltdown.",
                        "Plenty of cushion — enjoy the back nine of the season."],
        "PROBABLE": ["Trending well — a couple of solid rounds locks it up.",
                     "On track, no heroics required — just keep showing up.",
                     "Good shape — just avoid an honest-to-God disaster round."],
        "BUBBLE": ["Right on the number. Every round from here matters now.",
                   "Coin-flip territory — time to care about every three-footer.",
                   "Bubble watch. One hot round changes the conversation."],
        "LONGSHOT": ["Needs a hot stretch — two big rounds, starting now.",
                     "Outside looking in — the last Saturdays must be season-bests.",
                     "The math says 'maybe.' Vegas says 'no.'"],
        "NEEDS_MIRACLE": ["Alive on a technicality — perfect golf plus a soft cutoff.",
                          "Only survives maxing out AND a friendlier-than-projected line."],
        "TOAST": ["Mathematically eliminated — even a perfect finish won't reach the line.",
                  "Officially playing for pride (and skins). Next year's a fresh scorecard.",
                  "Toast, mathematically speaking. The calendar ran out before the game did."],
    }
    # deterministic pick so comments are stable run-to-run
    idx = abs(hash(p["name"])) % len(pools[t])
    c = pools[t][idx]
    if t in ("LOCK", "COMFORTABLE", "PROBABLE") and p["played"] == 2:
        c = c.rstrip(".") + " — capped out of the top 60 on only 2 rounds; needs a 3rd first."
    return t, c
