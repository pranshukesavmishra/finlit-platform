import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

// The help pop-up renders into document.body, which the server renderer has not got.
vi.mock("../components/ChartHelp", () => ({ ChartHelp: () => null }));
import fixture from "../lib/__fixtures__/ownershipReliance.json";
import type { Ownership } from "../lib/api";
import { OwnershipBars } from "../charts/OwnershipBars";
import { OwnershipYearPicker } from "./OwnershipYearPicker";
import { OwnershipSection } from "./Sections2";

const o = fixture as unknown as Ownership;
const html = (el: React.ReactElement) => renderToStaticMarkup(<MemoryRouter>{el}</MemoryRouter>);

describe("ownership bar chart", () => {
  const out = html(<OwnershipBars o={o} selected={o.periods.length - 1} onSelect={() => undefined} />);
  it("draws the controls, the toggle legend, the text fallback and the CSV button", () => {
    for (const t of ["Quarterly", "Yearly", "1Y", "3Y", "5Y", "All", "Mix", "Change", "Download CSV", "Promoters", "Foreign institutions", "Domestic institutions", "Retail &amp; others", "Government &amp; others"]) expect(out).toContain(t);
    expect(out).toContain('role="img"'); expect(out).toContain("<table"); expect(out).toContain('aria-live="polite"');
    expect(out).toContain('aria-pressed="true"');
  });
  it("starts on the 3Y quarterly mix: 12 bars, the last one selected", () => {
    expect((out.match(/class="ob-col"/g) || []).length).toBe(12);
    expect(out).toContain('stroke="var(--gold)"');
    expect(out).toContain("Jun 2026");
  });
  it("never says buy, sell, hold or target, and keeps the compliance line", () => {
    expect(out).toContain("Information only, not advice");
    expect(out).not.toMatch(/\b(buy|sell|hold|target)\b/i);
  });
  it("says there is not enough to show a trend with one filing", () => {
    const one = { ...o, periods: ["Jun 2026"], series: { promoters: [50.48] } } as unknown as Ownership;
    expect(html(<OwnershipBars o={one} selected={0} onSelect={() => undefined} />)).toContain("Not enough filings to show a trend");
  });
});

describe("ownership year selector", () => {
  const cap = { now: "Dec 2025", then: "Dec 2024", basis: "same quarter a year earlier", isLatest: false, year: 2025, isYearLatest: true, yearLatest: "Dec 2025" };
  it("is a radiogroup of year chips with the selected one checked and the caption", () => {
    const out = html(<OwnershipYearPicker years={[2026, 2025, 2024, 2023]} selected={2025} onPick={() => undefined} cap={cap} />);
    expect(out).toContain('role="radiogroup"'); expect((out.match(/role="radio"/g) || []).length).toBe(4);
    expect(out).toContain('aria-checked="true"'); expect(out).toContain("All filings");
    expect(out).toContain("Showing the latest filing in 2025: <b>Dec 2025</b>");
    expect(out).toContain("Changes compare with the same quarter a year earlier, Dec 2024.");
  });
  it("says so when the shown filing is a quarter picked from the chart", () => {
    const out = html(<OwnershipYearPicker years={[2025]} selected={2025} onPick={() => undefined} cap={{ ...cap, now: "Sep 2025", isYearLatest: false }} />);
    expect(out).toContain("picked from the chart"); expect(out).toContain("latest filing in 2025 is Dec 2025");
  });
});

describe("ownership section", () => {
  it("puts the year selector first, then the donut and the bought and sold panel, then the chart", () => {
    const out = html(<OwnershipSection o={o} />);
    const at = (t: string) => out.indexOf(t);
    expect(at("own-yr2")).toBeGreaterThan(0);
    expect(at("own-yr2")).toBeLessThan(at("Owners today"));
    expect(at("Owners today")).toBeLessThan(at("Who bought and who sold"));
    expect(at("Who bought and who sold")).toBeLessThan(at("How the shareholding pattern changed"));
  });
});
