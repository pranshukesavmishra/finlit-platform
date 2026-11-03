// The owner asked for "FinLit score" to be called "FinLit IQ" everywhere (Nov 2026), including "FinLit research score" and "FinLit overall score". The FinLit Mutual Fund Health Score is a different
// product and keeps its name. Ids, routes and data keys (finlit_score, ...) keep their spelling so links and saved data do not break.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = new URL("..", import.meta.url).pathname;
const files = (dir: string): string[] => readdirSync(dir).flatMap((n) => { const p = join(dir, n); return statSync(p).isDirectory() ? (n === "__fixtures__" ? [] : files(p)) : /\.(tsx?|json)$/.test(n) ? [p] : []; });
const OLD = /FinLit(?:['’]s)? (?:research |overall |model |company )?scores?\b(?!-)/gi;

describe("'FinLit score' is 'FinLit IQ' everywhere a person can read it", () => {
  it("no source text names it the old way", () => {
    const hits: string[] = [];
    for (const f of files(ROOT).filter((x) => !x.endsWith("noFinlitScoreWord.test.ts"))) {
      const src = readFileSync(f, "utf8").split("\n").filter((l) => !/^\s*(\/\/|\/\*|\*)/.test(l)).join("\n");
      for (const m of src.matchAll(OLD)) {
        const around = src.slice(Math.max(0, (m.index ?? 0) - 12), (m.index ?? 0) + m[0].length + 14);
        if (/FinLit models? scores?/i.test(m[0]) && /how the FinLit model scores/i.test(around)) continue;     // "how the FinLit model scores them": a verb, not the name
        hits.push(`${f.replace(ROOT, "")}: ${around.replace(/\s+/g, " ")}`);
      }
    }
    expect(hits).toEqual([]);
  });
});
