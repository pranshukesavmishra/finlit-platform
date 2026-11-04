"""Run the tests without pytest: python tests/run_tests.py   (pytest works too: python -m pytest -q tests)"""
import inspect
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # backend/, where the finlit_technicals package lives
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_api  # noqa: E402
import test_core  # noqa: E402
import test_sectors  # noqa: E402
import test_fetch_merge  # noqa: E402
import test_nse_memory  # noqa: E402
import test_staged_equals_single_run  # noqa: E402

ok = fail = 0
for mod in (test_core, test_api, test_sectors, test_fetch_merge, test_nse_memory, test_staged_equals_single_run):
    for name, fn in sorted(vars(mod).items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        with tempfile.TemporaryDirectory() as d:
            kwargs = {"tmp_path": Path(d)} if "tmp_path" in inspect.signature(fn).parameters else {}
            try:
                fn(**kwargs)
                ok += 1
                print(f"PASS {mod.__name__}.{name}")
            except Exception:
                fail += 1
                print(f"FAIL {mod.__name__}.{name}")
                traceback.print_exc()
print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
