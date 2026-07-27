"""
One-time: seed history.json from the roundsData already in the site HTML.
Run this ONCE before the first live pull. After that, run.py maintains it.
"""
import re, json
import config

html = open(config.HTML_TEMPLATE, encoding="utf-8").read()
m = re.search(r"const roundsData = (\[.*?\]);", html, re.DOTALL)
rounds = json.loads(m.group(1))

history = {}
for p in rounds:
    history[p["name"]] = [p.get(f"r{i}") for i in range(1, config.TOTAL_EVENTS + 1)]

with open(config.HISTORY_JSON, "w", encoding="utf-8") as f:
    json.dump(history, f, indent=1)

print(f"Seeded {config.HISTORY_JSON} with {len(history)} players "
      f"(R1–R{config.CURRENT_ROUND-1} banked).")
