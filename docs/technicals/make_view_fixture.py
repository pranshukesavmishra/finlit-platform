"""Builds frontend/src/lib/__fixtures__/prismTechnicalBuilt.json: the technical view EXACTLY as the browser now receives it for a report calculated
with the new engine (weights, points, divisor, ADX, trend alignment), from the pinned cases of the parity test.
    PYTHONPATH=backend:site-api python docs/technicals/make_view_fixture.py          (run with the research API's Python environment)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "site-api"))
sys.path.insert(0, str(ROOT / "backend"))
from backend.tests.test_technical_parity import CASES, assess  # noqa: E402  (site-api/backend/tests)
from finlit import prism  # noqa: E402

out = {name: prism.technical_view(assess(CASES[name]["params"])) for name in ("stage3_cap_binds", "smallcap_stage2", "bounce_in_downtrend", "largecap_stage4")}
path = ROOT / "frontend/src/lib/__fixtures__/prismTechnicalBuilt.json"
path.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print("wrote", path, {k: (v["shortTerm"]["score"], v["longTerm"]["score"], v["trendAlignment"]["label"]) for k, v in out.items()})
