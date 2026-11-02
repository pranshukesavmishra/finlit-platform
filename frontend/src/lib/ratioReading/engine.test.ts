// @vitest-environment node
// Every reading for the 7 saved stocks must stay word for word as in expected.txt, so a rule change never alters the wording by accident.
// After an intended change run:  UPDATE_RATIO_READING=1 npx vitest run src/lib/ratioReading
import { readFileSync, writeFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { readAll } from "./engine";

const here = (f: string) => new URL(f, import.meta.url);
const { meta, stocks } = JSON.parse(readFileSync(here("./fixtures.json"), "utf8")) as { meta: any; stocks: Record<string, { kind: string; periods: string[]; rows: any }> };
const lines: string[] = [];
for (const [symbol, s] of Object.entries(stocks)) {
  lines.push(`### ${symbol} (${s.kind})`);
  for (const [key, r] of Object.entries(readAll(s.periods, s.rows, meta, { kind: s.kind }) as Record<string, any>)) lines.push(`${key} [${r.label}] ${r.l1} || ${r.l2}${r.link ? ` [link:${r.link}]` : ""}`);
}
const text = lines.join("\n") + "\n";

describe("ratio readings", () => {
  it("match the saved wording for the saved stocks", () => {
    if (process.env.UPDATE_RATIO_READING) writeFileSync(here("./expected.txt"), text);
    expect(text).toBe(readFileSync(here("./expected.txt"), "utf8"));
  });
  it("never use a recommendation word", () => {
    expect(text).not.toMatch(/\b(buy|sell|accumulate|reduce|avoid|target|best|undervalued|overvalued)\b/i);
  });
  it("is plain text only", () => { expect(text).not.toMatch(/<[a-z]/i); });
});
