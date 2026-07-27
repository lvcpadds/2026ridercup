"""
Inject fresh data into the site HTML by swapping the two JS consts.
Uses string slicing (not re.sub) — the comment text contains characters
that break regex replacement escaping.
"""
import re, json
import config


def _replace_const(html, const_name, data):
    pat = re.compile(r"const " + const_name + r" = \[.*?\];", re.DOTALL)
    m = pat.search(html)
    if not m:
        raise ValueError(f"Anchor for `{const_name}` not found in HTML.")
    new = f"const {const_name} = {json.dumps(data)};"
    return html[:m.start()] + new + html[m.end():]


def update(main_data, rounds_data, path=None):
    path = path or config.HTML_TEMPLATE
    html = open(path, encoding="utf-8").read()
    html = _replace_const(html, "mainData", main_data)
    html = _replace_const(html, "roundsData", rounds_data)

    # stamp a "last updated" marker if the placeholder exists in the template
    from datetime import datetime
    stamp = datetime.now().strftime("%a %b %-d, %-I:%M %p")
    html = re.sub(r"<!--LAST_UPDATED-->.*?<!--/LAST_UPDATED-->",
                  f"<!--LAST_UPDATED-->Updated {stamp}<!--/LAST_UPDATED-->",
                  html, flags=re.DOTALL)

    open(path, "w", encoding="utf-8").write(html)
    return path


def rounds_data_from_history(history):
    """Turn {name:[r1..rN]} back into the roundsData shape the table expects."""
    out = []
    for name, rounds in history.items():
        rec = {"name": name, "isYou": False}
        tot = 0.0
        for i in range(1, config.TOTAL_EVENTS + 1):
            v = rounds[i - 1] if i - 1 < len(rounds) else None
            rec[f"r{i}"] = v
            if v is not None:
                tot += v
        rec["total"] = round(tot, 1)
        out.append(rec)
    return out
