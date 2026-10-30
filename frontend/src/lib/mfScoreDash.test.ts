import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { bandShares, cardScoreView, medianLine, scoreSortHref } from "./mfScoreDash";
import { etfMeasures, type CategoryScores, type FundScore } from "./mfScore";
import { CARDS } from "./mfCategories";
import { ScoreBody } from "../mf/ScoreCard";
import { ScoreCell } from "../mf/ScoreCell";

const BANNED = /\b(buy|sell|hold|recommended|recommend|best[- ]to[- ]buy|should|invest in|advice)\b/i;
const OPEN = { canSee: true, loading: false, failed: false };
const data = (items: CategoryScores["items"], runDate: string | null = "2026-10-29"): CategoryScores => ({ locked: false, runDate, items, disclaimer: "", method: "" });

describe("category card score view", () => {
  it("gives the median, the count, the band and the shares", () => {
    const v = cardScoreView("large-cap", data({ "large-cap": { median: 62.4, n: 41, green: 12, orange: 20, red: 9 } }), OPEN);
    expect(v.kind).toBe("scored");
    if (v.kind !== "scored") return;
    expect(v.median).toBe("62.4"); expect(v.band).toBe("mid"); expect(v.n).toBe(41);
    expect(v.line).toBe("median 62.4 of 41 scored funds");
    expect(v.shares).toEqual({ green: 29, orange: 49, red: 22 });
    expect(v.shares.green + v.shares.orange + v.shares.red).toBe(100);
  });
  it("colours the median by the site rule: 70 green, 50 orange, under 50 red", () => {
    const band = (m: number) => { const v = cardScoreView("k", data({ k: { median: m, n: 3, green: 1, orange: 1, red: 1 } }), OPEN); return v.kind === "scored" ? v.band : null; };
    expect([band(70), band(69.9), band(50), band(49.9)]).toEqual(["hi", "mid", "mid", "lo"]);
  });
  it("says Not scored yet when the score job has not run, and never invents a number for a category with no scored fund", () => {
    expect(cardScoreView("large-cap", data({}, null), OPEN).kind).toBe("notRun");
    expect(cardScoreView("small-cap", data({ "large-cap": { median: 60, n: 3, green: 0, orange: 3, red: 0 } }), OPEN).kind).toBe("none");
    expect(cardScoreView("x", undefined, { canSee: true, loading: true, failed: false }).kind).toBe("loading");
    expect(cardScoreView("x", undefined, { canSee: true, loading: false, failed: true }).kind).toBe("unavailable");
  });
  it("is locked, with no values at all, below Gold or when the server says locked", () => {
    expect(cardScoreView("x", undefined, { canSee: false, loading: false, failed: false })).toEqual({ kind: "locked" });
    expect(cardScoreView("x", { ...data({}), locked: true }, OPEN)).toEqual({ kind: "locked" });
    // even if numbers were somehow present, a locked answer shows none
    expect(cardScoreView("x", data({ x: { median: 80, n: 5, green: 5, orange: 0, red: 0 } }), { canSee: false, loading: false, failed: false })).toEqual({ kind: "locked" });
  });
  it("band shares always add to 100 and keep zeros at zero", () => {
    for (const c of [{ green: 1, orange: 1, red: 1 }, { green: 7, orange: 0, red: 3 }, { green: 0, orange: 0, red: 5 }, { green: 33, orange: 33, red: 34 }, { green: 1, orange: 0, red: 0 }]) {
      const s = bandShares(c); expect(s.green + s.orange + s.red).toBe(100);
      for (const k of ["green", "orange", "red"] as const) if (c[k] === 0) expect(s[k]).toBe(0);
    }
    expect(bandShares({ green: 0, orange: 0, red: 0 })).toEqual({ green: 0, orange: 0, red: 0 });
    expect(bandShares({ green: 1, orange: 1, red: 1 })).toEqual({ green: 34, orange: 33, red: 33 });
  });
  it("uses the singular for one fund", () => { expect(medianLine(55, 1)).toBe("median 55.0 of 1 scored fund"); });
  it("links every card to the list ordered by score inside that category", () => {
    for (const c of CARDS) {
      const u = new URL(scoreSortHref(c), "http://x");
      expect(u.pathname).toBe("/funds"); expect(u.searchParams.get("tab")).toBe(c.tab); expect(u.searchParams.get("cats")).toBe(c.key);
      expect(u.searchParams.get("sort")).toBe("score"); expect(u.searchParams.get("dir")).toBe("desc");
    }
  });
});

const metric = (id: string, state: string, over: object = {}) => ({ id, label: id, pillar: "quality", state, value: null, own: null, peer: null, peerN: null, points: null, weight: 20, groupValue: 50, why: null, ...over });
const base = (over: Partial<FundScore> = {}): FundScore => ({
  locked: false, kind: "etf", group: "OT-PASSIVE", groupName: "Others: Index funds and ETFs", status: "RATED", final: 71.2, label: "Healthy", pillars: [
    { key: "performance", name: "Performance", weight: 20, score: 66 }, { key: "risk", name: "Risk", weight: 15, score: 70 }, { key: "cost", name: "Cost", weight: 40, score: 80 }, { key: "quality", name: "Quality", weight: 25, score: 60 }],
  reasons: { strengths: [], watchouts: [], gaps: [], notApplicable: [], substitutions: [] }, metrics: [], disclaimer: "", method: "/methodology/mf-score", model: "1.1", ...over,
} as FundScore);
const html = (s: FundScore) => renderToStaticMarkup(createElement(MemoryRouter, null, createElement(ScoreBody, { s })));

describe("ETF measures", () => {
  it("reads liquidity and premium from the stored metrics, with no number of its own", () => {
    const s = base({ metrics: [metric("ETF_LIQUIDITY", "A", { own: 12.5, points: 80 }), metric("ETF_PREMIUM", "A", { own: -0.12, points: 90 })] as never });
    const m = etfMeasures(s);
    expect(m.map((x) => x.id)).toEqual(["ETF_LIQUIDITY", "ETF_PREMIUM"]);
    expect(m[0].text).toBe("It traded about ₹13 crore a day on the exchange."); expect(m[0].points).toBe(80);
    expect(m[1].text).toBe("Its exchange price was 0.12% below its NAV on the NAV date.");
    expect(m.every((x) => x.tone === "neutral")).toBe(true);
  });
  it("uses the listed reason's own words and tone when the measure is one of the reasons", () => {
    const line = { id: "ETF_PREMIUM", label: "Price against NAV", text: "Its exchange price was 0.80% away from its NAV on the NAV date.", points: 20, groupValue: 60, effect: -4, state: "A" };
    const s = base({ metrics: [metric("ETF_PREMIUM", "A", { own: 0.8, points: 20 })] as never, reasons: { strengths: [], watchouts: [line], gaps: [], notApplicable: [], substitutions: [] } });
    expect(etfMeasures(s)).toEqual([{ id: "ETF_PREMIUM", label: "ETF_PREMIUM", tone: "watch", points: 20, text: line.text }]);
  });
  it("says why a measure is missing and leaves out one that does not apply", () => {
    const s = base({ metrics: [metric("ETF_PREMIUM", "F", { why: "no_trade_on_nav_date" }), metric("ETF_LIQUIDITY", "N")] as never,
      reasons: { strengths: [], watchouts: [], gaps: [{ id: "ETF_PREMIUM", label: "Price against NAV", why: "no_trade_on_nav_date", text: "the ETF did not trade on the NAV date, so a premium cannot be measured" }], notApplicable: [], substitutions: [] } });
    const m = etfMeasures(s);
    expect(m).toHaveLength(1);
    expect(m[0]).toMatchObject({ id: "ETF_PREMIUM", tone: "gap", points: null });
    expect(m[0].text).toContain("the ETF did not trade on the NAV date");
  });
  it("shows nothing for a fund that is not rated", () => { expect(etfMeasures(base({ final: null, status: "NOT RATED" }))).toEqual([]); });
});

describe("the score body in the ETF card states", () => {
  const rated = base({ metrics: [metric("ETF_LIQUIDITY", "A", { own: 40, points: 100 }), metric("ETF_PREMIUM", "A", { own: 0.05, points: 95 })] as never,
    reasons: { strengths: [{ id: "ETF_LIQUIDITY", label: "How easily it trades", text: "It trades about ₹40 crore a day on the exchange.", points: 100, groupValue: 60, effect: 8, state: "A" }], watchouts: [], gaps: [], notApplicable: [], substitutions: [] } });
  it("rated: number, label, pillars, the ETF measures and the tag in the lists", () => {
    const h = html(rated);
    expect(h).toContain("71.2"); expect(h).toContain("Healthy"); expect(h).toContain(">Rated<"); expect(h).toContain("How this ETF trades"); expect(h).toContain("ETF measure");
    expect(h).toContain("Describes the fund&#x27;s health from its past NAVs, costs and holdings; not a recommendation. Information only, not investment advice.");
  });
  it("provisional: says so and holds the label", () => {
    const h = html(base({ ...rated, status: "PROVISIONAL", reason: "Short history", confidence: 0.5 }));
    expect(h).toContain("Provisional"); expect(h).toContain("Short history");
  });
  it("not rated: the reason, no number, no pillars, no ETF measures", () => {
    const h = html(base({ final: null, label: null, status: "NOT RATED", reason: "Less than 12 months of price history.", pillars: [], metrics: [] }));
    expect(h).toContain("Not rated"); expect(h).toContain("Less than 12 months of price history."); expect(h).not.toContain("How this ETF trades"); expect(h).not.toContain("out of 100");
  });
  it("not scored yet: says why, never a made-up value", () => {
    const h = html(base({ final: null, label: null, status: "NOT SCORED", reason: "Not scored: this exchange-traded fund has no exchange price history loaded yet.", pillars: [], metrics: [] }));
    expect(h).toContain("Not scored"); expect(h).toContain("no exchange price history");
  });
  it("a fund page (not an ETF) has no ETF block", () => { expect(html({ ...rated, kind: "mf" })).not.toContain("How this ETF trades"); });
});

describe("score cell", () => {
  const cell = (p: Parameters<typeof ScoreCell>[0]) => renderToStaticMarkup(createElement(ScoreCell, p));
  it("locked shows a lock and no value", () => {
    const h = cell({ item: { code: null, symbol: "X", plan: "ETF", group: null, final: 77, label: "Healthy", status: "RATED", reason: null, pillars: null, rank: null, rankOf: null, flags: [], confidence: null }, locked: true, why: "" });
    expect(h).toContain("Locked: Gold plan"); expect(h).not.toContain("77");
  });
  it("shows the server's reason where there is no score", () => {
    expect(cell({ item: { code: null, symbol: "X", plan: "ETF", group: null, final: null, label: null, status: null, reason: "Not scored: no exchange price history.", pillars: null, rank: null, rankOf: null, flags: [], confidence: null }, locked: false, why: "Not scored yet." })).toContain("Not scored: no exchange price history.");
  });
});

describe("wording of the new files", () => {
  it("has no advice words in any new fixed text", () => {
    for (const f of ["./mfScoreDash.ts", "../mf/ScoreCell.tsx", "../mf/Dashboard.tsx", "../etf/List.tsx", "../mf/ScoreCard.tsx"]) {
      const src = readFileSync(resolve(__dirname, f), "utf8");
      const strings = (src.match(/"[^"\n]{12,}"|`[^`\n]{12,}`/g) || []).filter((s) => !/^["`](\.\.|@|\/|\w+[-:])/.test(s) && !/className/.test(s));
      for (const s of strings) expect(s.replace(/not a recommendation|not investment advice/gi, ""), f).not.toMatch(BANNED);
    }
  });
});
