#!/bin/sh
# Status line: records Claude Code's status JSON and rate-limit usage for budget guards
# (scripts/review/review.py quota), then prints a short summary.
python3 -c '
import json, os, sys, time
d = json.load(sys.stdin)
base = os.path.expanduser("~/.claude/usage")
os.makedirs(base, exist_ok=True)
d["captured_at"] = int(time.time())
tmp = os.path.join(base, "statusline.json.tmp")
with open(tmp, "w") as f:
    json.dump(d, f)
os.replace(tmp, os.path.join(base, "statusline.json"))
rl = d.get("rate_limits") or {}
pct = {k: v.get("used_percentage") for k, v in rl.items() if isinstance(v, dict)}
hist = os.path.join(base, "history.jsonl")
last = None
try:
    with open(hist) as f:
        last = json.loads(f.readlines()[-1]).get("pct")
except Exception:
    pass
if pct and pct != last:
    with open(hist, "a") as f:
        f.write(json.dumps({"t": d["captured_at"], "pct": pct, "cost": (d.get("cost") or {}).get("total_cost_usd")}) + "\n")
parts = [(d.get("model") or {}).get("display_name", "")]
names = {"seven_day": "week", "five_hour": "5h"}
parts += [f"{names.get(k, k)} {v:.0f}%" for k, v in pct.items() if v is not None]
print(" · ".join(p for p in parts if p))
' 2>/dev/null || echo "Claude"
