#!/usr/bin/env python3
"""Move every font size in the FinLit source onto the type scale: 11 12 13 14 16 18 20 24 28 32 40.

    python fontsize_codemod.py src                  # dry run: lists every change, writes nothing
    python fontsize_codemod.py src --write          # applies the changes
    python fontsize_codemod.py src --write --tokens # CSS gets var(--fs-13) instead of 13px (needs tokens.css)

It rewrites, in .css .scss .sass .less .js .jsx .ts .tsx .vue .svelte .html files:
  font-size: 12.5px                 (CSS, styled-components and inline style strings)
  font: 600 12.5px/1.4 Inter        (the size inside the font shorthand)
  fontSize: 12.5 / fontSize: '12.5px'           (React style objects)
  fontSize="12.5" / fontSize={12.5} / font-size="12.5"   (SVG text in JSX and HTML)
  text-[12.5px]                     (Tailwind arbitrary sizes)
It leaves 0px, 44px and larger, em / rem / % / pt / clamp() values alone, and lists the relative and
computed ones (0.9em, calc(), var(), fontSize: size * 0.8) for a person to check. Running it twice changes nothing.
Skips node_modules, dist, build, .git and other generated folders. Python 3.8+, no dependencies.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

SCALE = [11, 12, 13, 14, 16, 18, 20, 24, 28, 32, 40]
EXTS = {".css", ".scss", ".sass", ".less", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte", ".html"}
SKIP_DIRS = {"node_modules", "dist", "build", ".git", ".next", ".nuxt", "coverage", "vendor", "out", ".cache",
             "__pycache__", ".venv", "venv"}
NUM = r"(\d+(?:\.\d+)?|\.\d+)"


def snap(px: float):
    """New size for an old px size, or None to leave it alone."""
    if px < 6 or px >= 44:
        return None
    for limit, to in ((11, 11), (12, 12), (13, 13), (14.5, 14), (17, 16), (19, 18), (22, 20), (26, 24), (29, 28),
                      (37, 32)):
        if px <= limit:
            return to
    return 40


def fmt(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else str(x)


# (name, pattern, group holding the number, kind) — kind decides how the replacement is written
RULES = [
    ("css font-size", re.compile(r"(font-size\s*:\s*)" + NUM + r"px\b", re.I), "css"),
    ("css font shorthand", re.compile(r"(\bfont\s*:\s*(?:[^;{}\n]*?\s)?)" + NUM + r"px(?=\s*/|\s+['\"\w-])", re.I), "px"),
    ("react fontSize", re.compile(r"(\bfontSize\s*:\s*)(['\"]?)" + NUM + r"(px)?\2(?=\s*[,}\n)])"), "react"),
    ("jsx fontSize attr", re.compile(r"(\bfontSize=)(['\"])" + NUM + r"(px)?\2"), "attr"),
    ("jsx fontSize={n}", re.compile(r"(\bfontSize=\{)" + NUM + r"(\})"), "brace"),
    ("svg font-size attr", re.compile(r"(\bfont-size=)(['\"])" + NUM + r"(px)?\2"), "attr"),
    ("tailwind text-[px]", re.compile(r"(\btext-\[)" + NUM + r"px(\])"), "tw"),
]
DYNAMIC = re.compile(r"\bfontSize\s*[:=]\s*\{?\s*(?!['\"]?\d)(?!['\"]?var\()(?!['\"]?inherit)[A-Za-z_$(`]")
# relative or computed sizes: not rewritten, listed so a person can check the result stays 11px or more
REVIEW = re.compile(r"font-size\s*:\s*(?:\.?\d[\d.]*(?:em|rem|%)|calc\(|var\(--(?!fs-))"
                    r"|\bfontSize\s*:\s*['\"]\.?\d[\d.]*(?:em|rem|%)", re.I)


def rewrite_line(line: str, tokens: bool, counts: Counter):
    changes = []

    def sub_for(kind):
        def repl(m):
            g = m.groups()
            if kind == "css":
                old = float(g[1])
                to = snap(old)
                if to is None or to == old:
                    return m.group(0)
                changes.append((fmt(old), to))
                return g[0] + (f"var(--fs-{to})" if tokens else f"{to}px")
            if kind == "px":
                old = float(g[1])
                to = snap(old)
                if to is None or to == old:
                    return m.group(0)
                changes.append((fmt(old), to))
                return g[0] + f"{to}px"
            if kind == "react":
                prefix, quote, num, unit = g
                old = float(num)
                to = snap(old)
                if to is None or to == old:
                    return m.group(0)
                changes.append((fmt(old), to))
                return f"{prefix}{quote}{to}{unit or ''}{quote}"
            if kind == "attr":
                prefix, quote, num, unit = g
                old = float(num)
                to = snap(old)
                if to is None or to == old:
                    return m.group(0)
                changes.append((fmt(old), to))
                return f"{prefix}{quote}{to}{unit or ''}{quote}"
            if kind == "brace":
                prefix, num, close = g
                old = float(num)
                to = snap(old)
                if to is None or to == old:
                    return m.group(0)
                changes.append((fmt(old), to))
                return f"{prefix}{to}{close}"
            if kind == "tw":
                prefix, num, close = g
                old = float(num)
                to = snap(old)
                if to is None or to == old:
                    return m.group(0)
                changes.append((fmt(old), to))
                return f"{prefix}{to}px{close}"
            return m.group(0)
        return repl

    new = line
    for _name, rx, kind in RULES:
        new = rx.sub(sub_for(kind), new)
    for old, to in changes:
        counts[(old, to)] += 1
    return new, changes


def files_under(paths):
    for p in paths:
        p = Path(p)
        if p.is_file():
            if p.suffix in EXTS:
                yield p
            continue
        for f in sorted(p.rglob("*")):
            if f.is_file() and f.suffix in EXTS and not any(part in SKIP_DIRS for part in f.parts):
                if f.name.endswith((".min.js", ".min.css")) or ".map" in f.suffixes:
                    continue
                yield f


def process(paths, write=False, tokens=False, out=sys.stdout):
    counts: Counter = Counter()
    touched, dynamic = 0, []
    for f in files_under(paths):
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        is_css = f.suffix in {".css", ".scss", ".sass", ".less"}
        lines = text.splitlines(keepends=True)
        out_lines, file_changes = [], []
        for n, line in enumerate(lines, 1):
            new, ch = rewrite_line(line, tokens and is_css, counts)
            if ch:
                file_changes.append((n, ch))
            if DYNAMIC.search(line) or REVIEW.search(line):
                dynamic.append(f"{f}:{n}: {line.strip()[:110]}")
            out_lines.append(new)
        if file_changes:
            touched += 1
            print(f"{f}", file=out)
            for n, ch in file_changes:
                print(f"  line {n}: " + ", ".join(f"{a}px -> {b}px" for a, b in ch), file=out)
            if write:
                f.write_text("".join(out_lines), encoding="utf-8")
    total = sum(counts.values())
    print(f"\n{total} font sizes in {touched} files {'changed' if write else 'would change'}", file=out)
    for (old, to), n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {old:>6}px -> {to}px   x{n}", file=out)
    if dynamic:
        print(f"\nRelative or computed font sizes, check these by hand ({len(dynamic)}): the result should be 11px or more", file=out)
        for d in dynamic[:200]:
            print("  " + d, file=out)
    return counts, dynamic


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*", default=["."], help="source folders or files (default: current folder)")
    ap.add_argument("--write", action="store_true", help="apply the changes (default: dry run)")
    ap.add_argument("--tokens", action="store_true", help="in CSS files write var(--fs-N) instead of Npx")
    a = ap.parse_args(argv)
    process(a.paths, write=a.write, tokens=a.tokens)
    if not a.write:
        print("\nDry run: nothing written. Add --write to apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
