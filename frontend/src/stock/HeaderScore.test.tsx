import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { CompanyFacts, FundamentalDots, ScoreBadge } from "./HeaderScore";
import { badgeView } from "../lib/scoreBands";
import type { PillarSummary, Profile } from "../lib/api";

const pl = (key: string, label: string, score: number | null, bl: string) => ({ key, label, score, band: { key: "mixed", label: bl }, coverage: 1 }) as PillarSummary;
const P = [pl("quality", "Quality", 76, "Healthy"), pl("growth", "Growth", 44, "Watch"), pl("profitability", "Profitability", 51, "Mixed"), pl("balance", "Balance sheet", 75, "Healthy"), pl("technical", "Technical", null, "")];
const profile = { symbol: "RELIANCE", industry: "Petroleum Products", subIndustry: "Refineries & Marketing", sector: "Energy", marketCapCr: 1602252.58 } as Profile;

describe("header", () => {
  it("draws one coloured dot per pillar with tooltip and aria-label, and a legend", () => {
    const h = renderToStaticMarkup(<FundamentalDots pillars={P} />);
    expect(h).toContain('title="Quality 76: green, healthy"');
    expect(h).toContain('aria-label="Growth 44: red, watch"');
    expect(h).toContain("Profitability 51: orange, mixed");
    expect(h).toContain("Technical: grey, not enough data");
    expect(h).toContain("What do the dots mean?");
    expect(h).toContain("70 or more"); expect(h).toContain("50 to 69"); expect(h).toContain("under 50");
  });
  it("labels industry and market cap", () => {
    const h = renderToStaticMarkup(<CompanyFacts p={profile} />);
    expect(h).toContain("Industry"); expect(h).toContain("Petroleum Products · Refineries &amp; Marketing");
    expect(h).toContain("Market cap"); expect(h).toContain("₹16,02,253 Cr · Large cap");
  });
  it("Silver badge is the basic score; Gold is Prism or 'not rated yet' with a link", () => {
    const wrap = (v: ReturnType<typeof badgeView>) => renderToStaticMarkup(<MemoryRouter><ScoreBadge view={v} symbol="RELIANCE" /></MemoryRouter>);
    const s = wrap(badgeView("silver", false, { overall: 51, word: "Mixed" }, { kind: "none" }));
    expect(s).toContain("FinLit score"); expect(s).toContain("band-mid"); expect(s).not.toContain("Prism");
    const g = wrap(badgeView("gold", false, { overall: 51, word: "Mixed" }, { kind: "report", final: 74.2, word: "Healthy", status: "RATED" }));
    expect(g).toContain("FinLit Prism"); expect(g).toContain("74.2"); expect(g).toContain("band-hi"); expect(g).not.toContain("FinLit score");
    const n = wrap(badgeView("gold", false, { overall: 51, word: "Mixed" }, { kind: "none" }));
    expect(n).toContain("Prism: not rated yet"); expect(n).toContain('href="/prism/RELIANCE"');
    expect(wrap(badgeView("basic", false, { overall: 51, word: "Mixed" }, { kind: "none" }))).toBe("");
  });
});
