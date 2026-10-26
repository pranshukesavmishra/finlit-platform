import json, sys, subprocess
sys.path.insert(0, "/home/user/finlit-platform/.claude/worktrees/agent-a907ea1d95b259c0c/site-api")
from backend.premium_engine import score_company
def rc(*a): return subprocess.run(["redis-cli","-n","12",*a],capture_output=True,text=True).stdout
keys=[k for k in rc("--scan","--pattern","prism:snap:*").split()]
out = []
for sym in ["RELIANCE", "HDFCBANK", "TCS"]:
    best = None
    for k in keys:
        v = json.loads(rc("get",k))
        if v["symbol"] == sym:
            best = v["snapshot"]
    if not best:
        print(sym, "no snapshot kept"); continue
    shown = best["rating"]["final"]
    res = score_company(best["inputs"], best["rating"]["group"])
    print(sym, "site/shown", shown, "engine direct", res["final"], "parts equal", res["parts"] == best["rating"]["parts"], "label", res["label"], best["rating"]["label"])
    out.append((sym, shown, res["final"]))
    assert abs(shown - res["final"]) < 1e-9 if shown is not None else res["final"] is None
# recorded reference
case = json.load(open("/home/user/finlit-platform/.claude/worktrees/agent-a907ea1d95b259c0c/site-api/backend/tests/fixtures/premium_reliance_screenshot.json"))
res = score_company(case["inputs"], "HEAVY")
print("upstream reference screenshot: expected", case["expectedScore"], "engine", round(res["final"], 1), "parts", {k: round(v, 1) for k, v in res["parts"].items()}, "expected", case["expectedParts"])
assert abs(res["final"] - case["expectedScore"]) < .05
print("OK")
