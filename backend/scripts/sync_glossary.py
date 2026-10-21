"""Writes the website copy of the glossary (frontend/src/content/glossary.json) and refreshes the demo fixture's glossary map
from backend/finlit/normalize/glossary_data.json, the single source. Run after editing the data file."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
src = json.loads((ROOT / "backend/finlit/normalize/glossary_data.json").read_text(encoding="utf-8"))
web = {"version": src["version"], "source": src["source"], "topics": src["topics"], "terms": src["terms"]}
(ROOT / "frontend/src/content/glossary.json").write_text(json.dumps(web, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
fx = ROOT / "frontend/public/demo/RELIANCE/ratios.json"
if fx.exists():
    import sys
    sys.path.insert(0, str(ROOT / "backend"))
    from finlit.normalize.glossary import describe
    d = json.loads(fx.read_text(encoding="utf-8"))
    d["glossary"] = {k: describe(k) for k in d["latest"]}
    fx.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
print("synced", len(web["terms"]), "terms")
