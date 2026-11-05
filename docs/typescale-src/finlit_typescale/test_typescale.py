"""Checks for fontsize_codemod.py and fontscale.js.   python test_typescale.py
The fontscale.js check needs Playwright with Chromium (skipped if missing)."""
import io
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fontsize_codemod as C  # noqa: E402

CSS = """.mf-fine{font-size:12.5px;color:#675f50}.mf-sort i{font-size:9px}
.hide{font-size:0px}.hero{font-size:62px}.lede{font-size:clamp(16px,1.6vw,19px)}.em{font-size:.7em}
@media (max-width:760px){table th{font-size:10.5px!important}.px{font-size:30px}}
.btn{font:600 13.5px/1.2 var(--font-sans)}.t{font: 15px Inter, sans-serif}
@media print{.p{font-size:9pt}}
h3 { font-size: 14.5px; }
"""
JSX = """const s = { fontSize: 12.5, color: 'red' };
const t = { fontSize: '10.5px' };
<text fontSize="9.5" x="2">0</text>
<text fontSize={10}>FY22</text>
<svg><text font-size="10.5">2020</text></svg>
<span className="text-[12.5px] font-semibold">x</span>
const fit = { fontSize: Math.max(8, w / 9) };
const ok = { fontSize: 'var(--fs-13)', other: 14 };
"""


def run(files: dict, **kw):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for name, text in files.items():
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(text, encoding="utf-8")
        buf = io.StringIO()
        counts, dynamic = C.process([root], out=buf, **kw)
        return {n: (root / n).read_text(encoding="utf-8") for n in files}, counts, dynamic, buf.getvalue()


def test_snap_table():
    assert [C.snap(x) for x in (9, 10.5, 11, 11.5, 12.5, 13.5, 14.5, 15, 17, 19, 21, 22, 23, 26, 28, 30, 36, 38)] == \
        [11, 11, 11, 12, 13, 14, 14, 16, 16, 18, 20, 20, 24, 24, 28, 32, 32, 40]
    assert C.snap(0) is None and C.snap(44) is None and C.snap(92) is None


def test_css_rewrite():
    out, counts, _dyn, _txt = run({"a.css": CSS}, write=True)
    css = out["a.css"]
    for want in ("font-size:13px;color", ".mf-sort i{font-size:11px}", "font-size:0px", "font-size:62px",
                 "clamp(16px,1.6vw,19px)", "font-size:.7em", "table th{font-size:11px!important}",
                 ".px{font-size:32px}", "font:600 14px/1.2 var(--font-sans)", "font: 16px Inter", "font-size:9pt",
                 "font-size: 14px;"):
        assert want in css, (want, css)
    assert sum(counts.values()) == 7


def test_dry_run_writes_nothing():
    out, counts, _d, txt = run({"a.css": CSS})
    assert out["a.css"] == CSS and sum(counts.values()) == 7 and "would change" in txt


def test_tokens_mode():
    out, *_ = run({"a.css": ".x{font-size:12.5px}.y{font:600 13.5px/1.2 Inter}"}, write=True, tokens=True)
    assert out["a.css"] == ".x{font-size:var(--fs-13)}.y{font:600 14px/1.2 Inter}"


def test_jsx_rewrite_and_dynamic_report():
    out, counts, dynamic, _ = run({"src/Chart.jsx": JSX}, write=True)
    js = out["src/Chart.jsx"]
    for want in ("fontSize: 13, color", "fontSize: '11px'", 'fontSize="11" x', "fontSize={11}",
                 'font-size="11">2020', "text-[13px] font-semibold", "fontSize: 'var(--fs-13)', other: 14"):
        assert want in js, (want, js)
    assert any("Math.max(8" in d for d in dynamic) and len(dynamic) == 1
    assert sum(counts.values()) == 6


def test_idempotent_and_skips_generated_folders():
    files = {"a.css": CSS, "node_modules/lib/x.css": ".z{font-size:9px}", "dist/app.css": ".z{font-size:9px}"}
    out, counts, *_ = run(files, write=True)
    assert out["node_modules/lib/x.css"] == ".z{font-size:9px}" and out["dist/app.css"] == ".z{font-size:9px}"
    out2, counts2, *_ = run({"a.css": out["a.css"]}, write=True)
    assert sum(counts2.values()) == 0 and out2["a.css"] == out["a.css"]


def test_fontscale_js_in_browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  (skipped: no Playwright)")
        return
    js = (HERE / "fontscale.js").read_text(encoding="utf-8")
    html = """<!doctype html><html><head><style>
      .a{font-size:12.5px} .b{font-size:9px !important} .c{font-size:0px} .d{font-size:60px}
      @media (min-width: 1px){ .e{font-size:13.5px} } .f{font-size:1.2em}
    </style></head><body><p class=a>a</p><p class=b style="font-size:20px">b</p><p class=c>c</p><p class=d>d</p>
    <p class=e>e</p><div style="font-size:10px"><p class=f>f</p></div><p class=g>g</p>
    <svg><text id=t1 font-size="10" y="20">0</text><text id=t2 font-size="9.5px" y="40">1</text><text id=t3 font-size="14" y="60">2</text></svg></body></html>"""
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.set_content(html)
        pg.add_script_tag(content=js)
        # a stylesheet that arrives later, as a code-split route would
        pg.evaluate("""() => { const s = document.createElement('style'); s.textContent = '.g{font-size:11.5px}';
                          document.head.appendChild(s); }""")
        pg.wait_for_timeout(100)
        fs = pg.evaluate("""() => Object.fromEntries([...document.querySelectorAll('p')].map(
                          e => [e.className, getComputedStyle(e).fontSize]))""")
        svg = pg.evaluate("""() => ['t1','t2','t3'].map(i => getComputedStyle(document.getElementById(i)).fontSize)""")
        b.close()
    assert svg == ["11px", "11px", "14px"], svg
    assert fs == {"a": "13px", "b": "11px", "c": "0px", "d": "60px", "e": "14px", "f": "12px", "g": "12px"}, fs


if __name__ == "__main__":
    bad = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                bad += 1
                print("FAIL", name, repr(e))
    print("all passed" if not bad else f"{bad} failed")
    sys.exit(1 if bad else 0)
