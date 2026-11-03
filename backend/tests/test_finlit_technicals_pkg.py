"""The vendored finlit_technicals package keeps its own test suite (finlit_technicals/tests, run with its run_tests.py). This runs it as part of the backend suite."""
import subprocess
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "finlit_technicals"


def test_the_package_suite_passes():
    r = subprocess.run([sys.executable, str(PKG / "tests" / "run_tests.py")], capture_output=True, text=True, timeout=600, cwd=str(PKG.parent))
    last = r.stdout.strip().splitlines()[-1]
    assert r.returncode == 0 and last.endswith("0 failed"), r.stdout[-2000:] + r.stderr[-1000:]
    assert int(last.split()[0]) >= 47


def test_the_website_process_never_imports_numpy_or_pandas_for_the_sector_pages():
    code = "import sys; import finlit.sector_api, finlit.sector_data, finlit.sector_job; print('pandas' in sys.modules or 'numpy' in sys.modules)"
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=str(PKG.parent), env={"PYTHONPATH": str(PKG.parent), "PATH": ""})
    assert r.stdout.strip() == "False", r.stderr[-800:]
