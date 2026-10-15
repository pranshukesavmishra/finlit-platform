"""Generate platform files from design/tokens.json.

    python design/build_tokens.py

Writes:
  design/dist/tokens.css   CSS variables for the website ([data-theme="dark"|"light"], dark by default,
                           and prefers-color-scheme for first visits)
  design/dist/tokens.ts    typed object for React (web) and React Native (mobile app)
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parent
TOKENS = json.loads((ROOT / "tokens.json").read_text())
DIST = ROOT / "dist"


def css_block(selector: str, values: dict) -> str:
    lines = [f"  --{k}: {v};" for k, v in values.items()]
    return f"{selector} {{\n" + "\n".join(lines) + "\n}\n"


def build_css() -> str:
    t = TOKENS
    shared = {f"font-{k}": v for k, v in t["font"].items()}
    shared.update({f"space-{k}": f"{v}px" for k, v in t["space"].items()})
    shared.update({f"radius-{k}": f"{v}px" for k, v in t["radius"].items()})
    shared.update({f"motion-{k}": v for k, v in t["motion"].items()})
    for name, spec in t["type"].items():
        shared[f"type-{name}-size"] = f"{spec['size']}px"
        shared[f"type-{name}-line"] = f"{spec['line']}px"
        shared[f"type-{name}-weight"] = spec["weight"]
    out = ["/* Generated from design/tokens.json. Do not edit by hand. */\n", css_block(":root", shared)]
    out.append(css_block(':root, [data-theme="dark"]', t["color"]["dark"]))
    out.append(css_block('[data-theme="light"]', t["color"]["light"]))
    out.append("@media (prefers-color-scheme: light) {\n" +
               css_block('  :root:not([data-theme])', t["color"]["light"]).replace("\n  --", "\n    --") + "}\n")
    return "\n".join(out)


def build_ts() -> str:
    body = json.dumps({k: v for k, v in TOKENS.items() if not k.startswith("$")}, indent=2)
    return ("// Generated from design/tokens.json. Do not edit by hand.\n"
            "// Shared by the website and the React Native app.\n"
            f"export const tokens = {body} as const;\n\n"
            "export type ThemeName = keyof typeof tokens.color;\n"
            "export type ColorToken = keyof typeof tokens.color.dark;\n"
            "export const color = (theme: ThemeName, token: ColorToken) => tokens.color[theme][token];\n")


def main():
    DIST.mkdir(exist_ok=True)
    dark, light = TOKENS["color"]["dark"], TOKENS["color"]["light"]
    missing = set(dark) ^ set(light)
    if missing:
        raise SystemExit(f"dark and light themes must define the same tokens; mismatch: {sorted(missing)}")
    (DIST / "tokens.css").write_text(build_css())
    (DIST / "tokens.ts").write_text(build_ts())
    print(f"wrote {DIST / 'tokens.css'} and {DIST / 'tokens.ts'} ({len(dark)} colour tokens per theme)")


if __name__ == "__main__":
    main()
