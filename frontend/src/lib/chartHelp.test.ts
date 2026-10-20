import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { CHART_HELP } from "./chartHelp";

const SRC = join(__dirname, "..");
const files = (dir: string): string[] => readdirSync(dir).flatMap((f) => {
  const p = join(dir, f);
  return statSync(p).isDirectory() ? files(p) : /\.tsx$/.test(f) ? [p] : [];
});
const sources = files(SRC).filter((f) => !/ChartHelp\.tsx$/.test(f)).map((f) => ({ f, text: readFileSync(f, "utf8") }));

describe("chart help registry", () => {
  it("has a real explanation for every entry", () => {
    for (const [id, e] of Object.entries(CHART_HELP)) {
      for (const k of ["title", "what", "read", "why"] as const) expect(e[k].trim().length, `${id}.${k}`).toBeGreaterThan(k === "title" ? 3 : 10);
      if (e.x !== undefined) expect(e.x.trim().length, `${id}.x`).toBeGreaterThan(5);
      if (e.y !== undefined) expect(e.y.trim().length, `${id}.y`).toBeGreaterThan(5);
    }
  });

  it("covers every id used with <ChartHelp id=\"...\"> or help=\"...\"", () => {
    const used = new Set<string>();
    for (const { text } of sources) for (const m of text.matchAll(/(?:<ChartHelp id|\bhelp)="([a-z0-9-]+)"/g)) used.add(m[1]);
    expect(used.size).toBeGreaterThan(40);
    for (const id of used) expect(CHART_HELP[id], `missing registry entry: ${id}`).toBeDefined();
  });

  it("covers the dynamic ids (trend cards, dashboard widgets, screener tabs)", () => {
    const s4 = sources.find((x) => x.f.endsWith("Sections4.tsx"))!.text;
    const cardIds = [...s4.matchAll(/(?:mk\(|annual\(|\{ id: )"([a-z_]+)"/g)].map((m) => m[1]);
    // mk("Revenue", "revenue", ...) takes the id from its second argument
    const mkIds = [...s4.matchAll(/mk\("[^"]+", "([a-z_]+)"/g)].map((m) => m[1]);
    const ids = new Set([...cardIds.filter((x) => !/^[A-Z]/.test(x)), ...mkIds]);
    expect(ids.size).toBeGreaterThanOrEqual(17);
    for (const id of ids) expect(CHART_HELP["trend-" + id], `trend-${id}`).toBeDefined();
    const dash = sources.find((x) => x.f.endsWith("Dashboard.tsx"))!.text;
    for (const m of dash.matchAll(/(\w+): "(dash-[a-z]+)"/g)) expect(CHART_HELP[m[2]], m[2]).toBeDefined();
    for (const id of ["screener-range", "screener-avg"]) expect(CHART_HELP[id]).toBeDefined();
  });

  it("keeps each field short and free of buy or sell advice", () => {
    for (const [id, e] of Object.entries(CHART_HELP)) {
      for (const [k, v] of Object.entries(e)) {
        expect((v as string).split(/[.!?](?:\s|$)/).filter(Boolean).length, `${id}.${k} sentence count`).toBeLessThanOrEqual(4);
        expect(v, `${id}.${k}`).not.toMatch(/\b(you should (buy|sell)|buy now|sell now|guaranteed)\b/i);
      }
    }
  });
});
