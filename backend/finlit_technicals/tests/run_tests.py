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



class MonkeyPatch:
    """The part of pytest's monkeypatch fixture the tests use (setattr, setenv, delenv), undone after each test."""

    def __init__(self):
        self._undo = []

    def setattr(self, obj, name, value):
        self._undo.append(lambda o=obj, n=name, v=getattr(obj, name): setattr(o, n, v))
        setattr(obj, name, value)

    def setenv(self, name, value):
        import os
        self._undo.append(lambda n=name, v=os.environ.get(name): os.environ.pop(n, None) if v is None else os.environ.__setitem__(n, v))
        os.environ[name] = str(value)

    def delenv(self, name, raising=True):
        import os
        if name in os.environ:
            self._undo.append(lambda n=name, v=os.environ[name]: os.environ.__setitem__(n, v))
            del os.environ[name]

    def undo(self):
        while self._undo:
            self._undo.pop()()


ok = fail = 0
for mod in (test_core, test_api, test_sectors, test_fetch_merge, test_nse_memory, test_staged_equals_single_run):
    for name, fn in sorted(vars(mod).items()):
        if not name.startswith("test_") or not callable(fn):
            continue
        with tempfile.TemporaryDirectory() as d:
            params = inspect.signature(fn).parameters
            kwargs = {"tmp_path": Path(d)} if "tmp_path" in params else {}
            mp = MonkeyPatch()
            if "monkeypatch" in params:
                kwargs["monkeypatch"] = mp
            try:
                fn(**kwargs)
                ok += 1
                print(f"PASS {mod.__name__}.{name}")
            except Exception:
                fail += 1
                print(f"FAIL {mod.__name__}.{name}")
                traceback.print_exc()
            finally:
                mp.undo()
print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
