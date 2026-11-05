import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it } from "vitest";

// The one type scale (docs/TYPE-SCALE.md): every font size in the source is one of these, or an allow-listed display size.
// Fails with file:line so a new off-scale or sub-11px size is caught before it ships.
const SCALE = [11, 12, 13, 14, 16, 18, 20, 24, 28, 32, 40];
const SRC = new URL("../", import.meta.url).pathname;

// Documented exceptions. Display headings (44px and up) and clamp() heroes stay as designed; anything else needs a line here.
const DISPLAY_MIN = 44;
const ALLOW: { file: RegExp; line: RegExp; why: string }[] = [
  { file: /./, line: /(?:--fs-[a-z0-9]+|font-size)\s*:\s*(?:44|45|46|48|52|54|56|60|64|72|80|88|96|120)px/i, why: "display sizes, 44px and up" },
  { file: /styles\/theme\.css$/, line: /font-size\s*:\s*0(px)?\b/, why: "text hidden on purpose" },
  { file: /./, line: /font-size\s*:\s*(?:0|0px|inherit|initial|unset|revert)\b/i, why: "reset values" },
];

function walk(dir: string, out: string[] = []): string[] {
  for (const n of readdirSync(dir)) {
    const p = join(dir, n);
    if (statSync(p).isDirectory()) { if (n !== "content") walk(p, out); }
    else if (/\.(css|tsx?)$/.test(n) && !/\.test\.tsx?$/.test(n)) out.push(p);
  }
  return out;
}

const NUM = "(\\d+(?:\\.\\d+)?|\\.\\d+)";
const PATTERNS: { re: RegExp; px: (m: RegExpMatchArray) => number | null }[] = [
  { re: new RegExp(`font-size\\s*[:=]\\s*["']?${NUM}px\\b`, "gi"), px: (m) => +m[1] },
  { re: new RegExp(`(?<![\\w-])font\\s*:\\s*(?:[^;{}\\n]*?\\s)?${NUM}px(?=\\s*/|\\s+['"\\w-])`, "gi"), px: (m) => +m[1] },
  { re: new RegExp(`fontSize\\s*[:=]\\s*\\{?\\s*["']?${NUM}(?:px)?["']?(?=\\s*[,}\\n)/>])`, "g"), px: (m) => +m[1] },
  { re: new RegExp(`\\btext-\\[${NUM}px\\]`, "g"), px: (m) => +m[1] },
  { re: new RegExp(`--fs-[a-z0-9]+\\s*:\\s*${NUM}px`, "g"), px: (m) => +m[1] },
];
// Relative or computed sizes cannot be checked by value, so they must be listed and judged by hand.
const RELATIVE = /font-size\s*:\s*(?:\.?\d[\d.]*(?:em|rem|%)|calc\(|smaller|larger|x-small|small\b|medium\b|large\b)|fontSize\s*:\s*["']\.?\d[\d.]*(?:em|rem|%)/i;

export function findViolations(files: Record<string, string>): string[] {
  const bad: string[] = [];
  for (const [file, text] of Object.entries(files)) {
    text.split("\n").forEach((line, i) => {
      const allowed = ALLOW.some((a) => a.file.test(file) && a.line.test(line));
      const where = `${file}:${i + 1}: ${line.trim().slice(0, 100)}`;
      if (RELATIVE.test(line) && !allowed) bad.push(`relative size ${where}`);
      // fluid clamp() sizes: only fluid headings and big figures (largest value 28px or more) may stay fluid; smaller text must sit on the scale
      for (const m of line.matchAll(/(?:font-size\s*:|font\s*:[^;{}"]*?\s)clamp\(([^)]*)\)/gi)) {
        const top = [...m[1].matchAll(/(\d+(?:\.\d+)?)px/g)].map((x) => +x[1]).pop() ?? 0;
        if (top < 28) bad.push(`clamp under 28px ${where}`);
      }
      for (const { re, px } of PATTERNS) {
        for (const m of line.matchAll(re)) {
          const v = px(m);
          if (v == null || v === 0 || v >= DISPLAY_MIN || SCALE.includes(v)) continue;
          bad.push(`${v < 11 ? "under 11px" : "off scale"} ${where}`);
        }
      }
      for (const m of line.matchAll(/font-size\s*:\s*var\(--fs-(\d+)\)/g)) if (!SCALE.includes(+m[1])) bad.push(`unknown token ${where}`);
    });
  }
  return bad;
}

describe("type scale", () => {
  it("source CSS and TSX use only the 11 scale sizes (and documented display sizes)", () => {
    const files: Record<string, string> = {};
    for (const f of walk(SRC)) files[relative(SRC, f)] = readFileSync(f, "utf8");
    expect(Object.keys(files).length).toBeGreaterThan(100);
    expect(findViolations(files)).toEqual([]);
  });

  it("the checker itself flags sub-11px and off-scale sizes", () => {
    const bad = findViolations({
      "a.css": ".a{font-size:10px}\n.b{font-size:13px}\n.c{font-size:12.5px}\n.d{font-size:.8em}\n.e{font-size:var(--fs-15)}\n.f{font-size:clamp(20px,5vw,24px)}\n.g{font-size:56px}",
      "b.tsx": "const s={fontSize: 9.5}; <text fontSize=\"10\"/>; const t={fontSize:14}",
    });
    expect(bad.map((b) => b.split(" a.css")[0].split(" b.tsx")[0])).toEqual(["under 11px", "off scale", "relative size", "unknown token", "clamp under 28px", "under 11px", "under 11px"]);
    expect(bad[0]).toContain("a.css:1");
  });

  it("every scale token is defined and loaded before the app styles", () => {
    const css = readFileSync(new URL("./typescale.css", import.meta.url), "utf8");
    for (const n of SCALE) expect(css).toContain(`--fs-${n}: ${n}px`);
    const main = readFileSync(new URL("../main.tsx", import.meta.url), "utf8");
    expect(main.indexOf("styles/typescale.css")).toBeGreaterThan(-1);
    expect(main.indexOf("styles/typescale.css")).toBeLessThan(main.indexOf("styles/finlit.css"));
  });
});
