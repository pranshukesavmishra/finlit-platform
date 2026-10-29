import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import fx from "./__fixtures__/prismTechnical.json";
import built from "./__fixtures__/prismTechnicalBuilt.json";
import report from "./__fixtures__/prismReport.json";
import { Technical, TechPointer } from "../components/prism/pzr/Technical";
import { PrismTechRow } from "../stock/PrismTechRow";
import { TrendMap, alignmentSentence, fmtPoints, fmtSignal } from "../components/prism/pzr/TechBreakdown";
import type { PrismReport } from "./prism";
import type { PrismLatest } from "../stock/PrismCard";
import {
  ALIGN_NA, BANDS, FORBIDDEN, HOW, MODEL_VERDICT_TONE, RATING_WORD, TECH_NOTE, allShownText, factorGroup, filterTechFactors, fmtScore, parseTechnical, ratingWord, safeText, scalePos, scoreBand, trendAlignment, trendBand,
  verdictView,
} from "./prismTechnical";

const A = Object.fromEntries(Object.entries(fx).map(([k, v]) => [k, parseTechnical(v)!])) as Record<"ready" | "incomplete" | "capped" | "mixed", NonNullable<ReturnType<typeof parseTechnical>>>;
const withTech = (a: unknown) => ({ ...(report as unknown as PrismReport), technicalAssessment: a }) as PrismReport;
const OLD = report as unknown as PrismReport;
const strip = (h: string) => h.replace(/<[^>]+>/g, " ").replace(/&#x27;/g, "'").replace(/&amp;/g, "&").replace(/\s+/g, " ");
const horizon = (score: number | null, rating: string | null) => ({ score, rating, status: "ready" as const, horizon: null, availableCount: 1, requiredCount: 1, stageCapped: false, uncappedScore: null, divisor: null, factors: [] });

describe("rating words: the model's advice words never reach the screen", () => {
  it("maps every upstream rating", () => {
    expect(Object.keys(RATING_WORD).sort()).toEqual(["buy", "hold", "reduce", "sell", "strong buy", "unavailable"]);
    expect(ratingWord("Strong Buy", 60).word).toBe("Strongly positive");
    expect(ratingWord("Buy", 30).word).toBe("Positive");
    expect(ratingWord("Hold", 0).word).toBe("Neutral");
    expect(ratingWord("Reduce", -30).word).toBe("Negative");
    expect(ratingWord("Sell", -60).word).toBe("Strongly negative");
    expect(ratingWord("Unavailable", null).word).toBe("Not available");
    for (const r of Object.keys(RATING_WORD)) expect(ratingWord(r, 10).word).not.toMatch(FORBIDDEN);
  });
  it("uses the full-precision score when the rating word is unknown, and never shows an unknown word", () => {
    expect(ratingWord("Accumulate", 19.999999).word).toBe("Neutral");
    expect(ratingWord("???", 20).word).toBe("Positive");
    expect(ratingWord("Buy", null).word).toBe("Not available");
  });
  it("band boundaries follow the model: >=50, >=20, >-20, >-50, and exactly -50 is the lowest", () => {
    const b = (s: number) => scoreBand(s);
    expect([b(50), b(49.99), b(20), b(19.99), b(-19.99), b(-20), b(-49.99), b(-50), b(-50.01)]).toEqual(["strongpos", "pos", "pos", "neutral", "neutral", "neg", "neg", "strongneg", "strongneg"]);
  });
});

describe("trend alignment: all nine combinations (finlit_technicals v1.1, stlt.ALIGNMENT)", () => {
  // short-term band x long-term band; the labels are the team's, the tone is the model's own nine-cell verdict (BUY ... SELL, never shown)
  const MATRIX: [number, number, string, string, "pos" | "mixed" | "neg"][] = [
    [20, 20, "Strong on both timeframes", "STRONG BUY", "pos"], [20, 0, "Short-term strength, no long-term trend", "BUY", "pos"],
    [20, -20, "Short-term bounce within a long-term downtrend", "BOUNCE ONLY, DON'T INVEST", "mixed"],
    [0, 20, "Long-term uptrend, short-term pause", "ACCUMULATE ON DIPS", "pos"], [0, 0, "No clear trend", "HOLD", "mixed"],
    [0, -20, "Long-term downtrend, short-term flat", "REDUCE", "neg"],
    [-20, 20, "Short-term pullback within a long-term uptrend", "BUY THE DIP, WAIT FOR ST TURN", "pos"], [-20, 0, "Short-term weakness, no long-term trend", "REDUCE", "neg"],
    [-20, -20, "Weak on both timeframes", "SELL / AVOID", "neg"],
  ];
  it.each(MATRIX)("short %s, long %s: %s", (st, lt, label, model, expected) => {
    const v = verdictView({ shortTerm: horizon(st, null), longTerm: horizon(lt, null) });
    expect(v.word).toBe(label);
    expect(v.tone).toBe(expected);
    expect(MODEL_VERDICT_TONE[model]).toBe(expected);       // same nine cells and same tone as the model's own verdict
    expect(`${v.word} ${v.detail}`).not.toMatch(FORBIDDEN);
    const al = trendAlignment(st, lt)!;
    expect(al.cells).toHaveLength(9); expect(al.cells.filter((c) => c.current)).toHaveLength(1); expect(al.cells.find((c) => c.current)!.label).toBe(label);
    expect(new Set(al.cells.map((c) => c.label)).size).toBe(9);
  });
  it("the band rule: +20 or more positive, -20 or less negative", () => {
    expect([20, 19.99, -19.99, -20, 0].map((x) => trendBand(x))).toEqual(["positive", "neutral", "neutral", "negative", "neutral"]);
    expect([null, undefined, NaN].map((x) => trendBand(x))).toEqual([null, null, null]);
    expect(trendAlignment(35.3, 39.3)?.label).toBe("Strong on both timeframes");
    expect(trendAlignment(-30, 25)?.code).toBe("st_negative_lt_positive");
  });
  it("needs both scores, says so, and never shows a verdict word of the model", () => {
    const one = verdictView({ shortTerm: horizon(30, "Buy"), longTerm: horizon(null, null) });
    expect(one.word).toBe(ALIGN_NA); expect(one.tone).toBe("na");
    expect(trendAlignment(30, null)).toBeNull();
  });
  it("shows the working: both scores, both bands and the label", () => {
    expect(alignmentSentence({ shortTerm: horizon(39.3, null), longTerm: horizon(35.3, null) })).toBe("Short-term +39 (Positive) × long-term +35 (Positive) = Strong on both timeframes.");
  });
});

describe("score display", () => {
  it("rounds for display only and never shows a number from the wrong band", () => {
    expect(fmtScore(34.4)).toBe("+34");
    expect(fmtScore(-34.6)).toBe("−35");
    expect(fmtScore(0)).toBe("0");
    expect(fmtScore(-0.2)).toBe("0");
    expect(fmtScore(19)).toBe("+19");
    expect(fmtScore(19.96)).toBe("+19.96");   // +20 would read as Positive; the true score is Neutral
    expect(fmtScore(-19.6)).toBe("−19.6");
    expect(fmtScore(-49.7)).toBe("−49.7");
    expect(fmtScore(-50)).toBe("−50");
    expect(fmtScore(null)).toBe("—");
    expect(scalePos(-100)).toBe(0); expect(scalePos(0)).toBe(50); expect(scalePos(100)).toBe(100); expect(scalePos(250)).toBe(100);
  });
});

describe("parser", () => {
  it("returns null for reports without the field and for non-assessments, and never throws", () => {
    for (const v of [undefined, null, 0, "x", [], {}, { shortTerm: 5 }, { status: "ready" }]) expect(parseTechnical(v)).toBeNull();
    const garbage = [{ shortTerm: {}, longTerm: {} }, { shortTerm: { score: "9", factors: "no" }, longTerm: { factors: [null, 3, { key: 1 }, { key: "a", label: "A", signal: 7, status: "available" }] }, observations: 5, benchmarkSources: [1] }];
    for (const g of garbage) { const a = parseTechnical(g)!; expect(a.status).toBe("incomplete"); expect(a.shortTerm.score).toBeNull(); }
    expect(parseTechnical(garbage[1])!.longTerm.factors[0].status).toBe("unavailable");   // out-of-range signal is no signal
  });
  it("keeps the model's numbers exactly and drops weights and hashes", () => {
    const a = A.ready;
    expect((fx.ready as { shortTerm: { score: number } }).shortTerm.score).toBe(a.shortTerm.score);
    expect(JSON.stringify(a)).not.toMatch(/inputHash|sourceCodeSha256/i);
    expect(JSON.stringify(fx)).not.toMatch(/"weight"|inputHash|sourceCodeSha256/);   // the older fixtures: reports stored before the breakdown existed
    expect(JSON.stringify(built)).not.toMatch(/inputHash|sourceCodeSha256/);          // and the new ones carry weights and points but never a hash
    expect(A.capped.longTerm.stageCapped).toBe(true);
    expect(A.capped.longTerm.score).toBe(19);
    expect(A.incomplete.status).toBe("incomplete"); expect(A.incomplete.longTerm.score).toBeNull(); expect(A.incomplete.shortTerm.score).not.toBeNull();
    expect(A.ready.benchmarkSources.map((s) => s.name)).toContain("Nifty 500");
    expect(A.ready.observations.stage).toBe(2);
  });
  it("groups signals by what they say", () => {
    const rows = A.mixed.shortTerm.factors;
    const n = (g: Parameters<typeof filterTechFactors>[1]) => filterTechFactors(rows, g).length;
    expect(n("all")).toBe(n("supporting") + n("adverse") + n("neutral") + n("unavailable"));
    expect(rows.filter((f) => f.status === "disabled").every((f) => factorGroup(f) === null)).toBe(true);
  });
});

describe("compliance scan of everything the model sends", () => {
  const raw = (a: unknown): string[] => { const out: string[] = []; const walk = (v: unknown) => { if (typeof v === "string") out.push(v); else if (v && typeof v === "object") Object.values(v).forEach(walk); }; walk(a); return out; };
  it("finds the model's advice words only where we already rewrite them, and rewrites them", () => {
    const found = new Set(raw(fx).filter((s) => FORBIDDEN.test(s)).filter((s) => !["Strong Buy", "Buy", "Hold", "Reduce", "Sell", "STRONG BUY", "BUY", "HOLD", "REDUCE", "SELL / AVOID", "BUY THE DIP, WAIT FOR ST TURN", "ACCUMULATE ON DIPS", "BOUNCE ONLY, DON'T INVEST"].includes(s)));
    expect([...found]).toEqual(["Buying and selling volume"]);   // the model's own label for OBV
    expect(safeText("Buying and selling volume")).toBe("Volume flow (on-balance volume)");
  });
  it("rewrites every forbidden word and is idempotent", () => {
    const samples = ["Buy now", "selling pressure", "Hold above EMA", "holds support", "reduces risk", "avoid gaps", "target level", "stop-loss", "Exit", "accumulation phase", "entry point", "buyers and sellers", "Reduction", "BUYBACK"];
    for (const s of samples) { const r = safeText(s); expect(r).not.toMatch(FORBIDDEN); expect(safeText(r)).toBe(r); }
    expect(safeText("Hold above EMA 20")).toBe("Stay above EMA 20");
    expect(safeText("threshold and shareholder")).toBe("threshold and shareholder");
    expect(safeText(null)).toBe("");
  });
  it.each(Object.keys(fx))("fixture %s: no shown string contains an advice word", (k) => {
    for (const s of allShownText(A[k as keyof typeof A])) expect(s, s).not.toMatch(FORBIDDEN);
  });
});

describe("report page section", () => {
  const html = (a: unknown) => renderToStaticMarkup(<Technical report={withTech(a)} onRecalculate={() => undefined} />);
  it.each(Object.keys(fx))("%s: renders, states its conclusions, and contains no advice word anywhere (text or aria-label)", (k) => {
    const h = html((fx as Record<string, unknown>)[k]);
    expect(h).not.toMatch(FORBIDDEN);
    const t = strip(h);
    expect(t).toContain("Technical view");
    expect(t).toContain("does not predict prices");
    expect(t).toContain("not a recommendation");
    expect(t).toContain("Where this comes from");
    expect(t).toContain("23 Oct 2026");
    expect(t).toContain("FinEdge");
    expect(h).not.toMatch(/inputHash|sourceCodeSha256/i);
  });
  it("ready: both scores, words, signals, observations and sources", () => {
    const h = html(fx.ready), t = strip(h);
    expect(t).toContain("+64");   // 63.54 rounded for display
    expect(t).toContain("+65");
    expect(t).toContain("Strongly positive");
    expect(t).toContain("Strong on both timeframes");
    expect(t).toContain("Short-term +64 (Positive) × long-term +65 (Positive) = Strong on both timeframes.");
    expect(h).toContain('aria-label="Short term: +64 on a scale from minus 100 to plus 100, strongly positive. 14 of 14 signals available."');
    expect(t).toContain("Volume flow (on-balance volume)");
    expect(t).toContain("Stage 2: advancing");
    expect(t).toContain("Nifty Midcap 100");
    expect(t).toContain("Switched off in this model: Sector relative strength");
    expect(h).toContain('aria-pressed="true"');
  });
  it("mixed: opposite horizons are both stated beside the chip", () => {
    const t = strip(html(fx.mixed));
    expect(t).toContain("−35"); expect(t).toContain("+23");
    expect(t).toContain("Short-term −35 (Negative) × long-term +23 (Positive) = Short-term pullback within a long-term uptrend.");
  });
  it("capped: says why the long-term score is limited", () => {
    const t = strip(html(fx.capped));
    expect(t).toContain("Limited by the market stage");
    expect(t).toContain("+19");
    expect(t).toContain("Neutral");
  });
  it("incomplete: withholds the score, lists missing inputs with reasons, no combined trend", () => {
    const h = html(fx.incomplete), t = strip(h);
    expect(t).toContain("Some inputs are missing");
    expect(t).toContain("Aligned stock and benchmark history is insufficient");
    expect(t).toContain(ALIGN_NA);
    expect(t).toContain("score withheld");
    expect(strip(h)).toContain("Not available score withheld");
  });
  it("older reports get a calm note and a recalculate action, and the Prism score is untouched", () => {
    const h = renderToStaticMarkup(<Technical report={OLD} onRecalculate={() => undefined} />), t = strip(h);
    expect(t).toContain("does not include the technical view");
    expect(t).toContain("Recalculate");
    expect(t).toContain("does not predict prices");
    expect(h).not.toMatch(FORBIDDEN);
    expect(renderToStaticMarkup(<TechPointer report={OLD} />)).toBe("");
    expect(strip(renderToStaticMarkup(<TechPointer report={withTech(fx.ready)} />)).replace(/ ([,.])/g, "$1")).toContain("Technical view: short term strongly positive, long term strongly positive");
  });
  it("is not a part of the score", () => {
    const r = withTech(fx.ready);
    expect(r.rating.parts).toEqual((report as unknown as PrismReport).rating.parts);
    expect(Object.keys(r.rating.parts)).not.toContain("technical");
  });
});

describe("stock page row", () => {
  const L = (a?: unknown) => ({ technicalAssessment: a }) as unknown as PrismLatest;
  it("shows both horizons with score, word and a summary label; nothing advisory", () => {
    for (const k of Object.keys(fx)) {
      const h = renderToStaticMarkup(<PrismTechRow report={L((fx as Record<string, unknown>)[k])} />);
      expect(h).not.toMatch(FORBIDDEN);
      expect(h).toContain("Technical view, separate from the Prism score");
    }
    const t = strip(renderToStaticMarkup(<PrismTechRow report={L(fx.mixed)} />));
    expect(t).toContain("−35"); expect(t).toContain("Negative"); expect(t).toContain("+23"); expect(t).toContain("Positive");
  });
  it("incomplete shows Not available for the missing horizon; older reports get one quiet line", () => {
    expect(strip(renderToStaticMarkup(<PrismTechRow report={L(fx.incomplete)} />))).toContain("Not available");
    const t = strip(renderToStaticMarkup(<PrismTechRow report={L(undefined)} onRecalculate={() => undefined} />));
    expect(t).toContain("Technical view: recalculate to add");
  });
  it("TECH_NOTE is honest", () => { expect(TECH_NOTE).toMatch(/does not predict prices/); expect(TECH_NOTE).not.toMatch(FORBIDDEN); });
});

describe("one wording file shared with the PDF", () => {
  it("is byte-identical to the site-api copy that the PDF reads", async () => {
    const { readFileSync } = await import("node:fs");
    const web = readFileSync(new URL("./technicalWording.json", import.meta.url));
    const pdf = readFileSync(new URL("../../../site-api/backend/technical_wording.json", import.meta.url));
    expect(web.equals(pdf)).toBe(true);
  });
  it("no word on the shared table is an advice word", () => {
    for (const r of Object.values(RATING_WORD)) expect(r.word).not.toMatch(FORBIDDEN);
    for (const c of trendAlignment(30, 30)!.cells) expect(c.label).not.toMatch(FORBIDDEN);
  });
  it("the band boundaries are the shared constants, at every edge", () => {
    expect(BANDS).toEqual({ strongPositive: 50, positive: 20, neutral: -20, negative: -50 });
    const at = (v: number, tone: string) => expect(scoreBand(v)).toBe(tone);
    at(BANDS.strongPositive, "strongpos"); at(BANDS.strongPositive - 1e-9, "pos");
    at(BANDS.positive, "pos"); at(BANDS.positive - 1e-9, "neutral");
    at(BANDS.neutral + 1e-9, "neutral"); at(BANDS.neutral, "neg");
    at(BANDS.negative + 1e-9, "neg"); at(BANDS.negative, "strongneg");
    at(100, "strongpos"); at(-100, "strongneg");
  });
});

describe("legend, gauge and light-theme contrast", () => {
  it("the legend is written from the same bands the rating uses", async () => {
    const { bandLegend, bandWidths } = await import("./prismTechnical");
    expect(bandLegend()).toBe("Strongly positive: +50 or more · Positive: +20 up to +50 · Neutral: above −20 up to +20 · Negative: above −50 up to −20 · Strongly negative: −50 or less.");
    expect(bandWidths()).toEqual([25, 15, 20, 15, 25]);
  });
  it("the technical card shows that legend, and no aria-label sits on a plain span, paragraph or list item", () => {
    const html = renderToStaticMarkup(<Technical report={withTech(fx.ready)} />);
    expect(strip(html)).toContain("Strongly positive: +50 or more");
    expect(html).not.toMatch(/<(span|p|li)\b[^>]*\baria-label=/);
  });
  it("`.pzt-rn small` keeps WCAG AA contrast (4.5:1) on every light surface", async () => {
    const { readFileSync } = await import("node:fs");
    const css = readFileSync(new URL("../styles/prism-technical.css", import.meta.url), "utf8");
    const base = readFileSync(new URL("../styles/finlit.css", import.meta.url), "utf8");
    expect(css).not.toMatch(/\.pzt-rn small \{[^}]*opacity/);
    const block = base.slice(base.indexOf(':root[data-theme="light"]'));
    const hex = (name: string) => new RegExp(`--${name}:\\s*(#[0-9A-Fa-f]{6})`).exec(block)![1];
    const lum = (h: string) => { const c = [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255).map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4)); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; };
    const ratio = (a: string, b: string) => { const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05); };
    for (const surface of ["bg", "s1", "s2", "s3"]) expect(ratio(hex("muted"), hex(surface))).toBeGreaterThanOrEqual(4.5);
  });
});

describe("values already mapped by the API render the same as the model's raw words", () => {
  it("rating", () => {
    for (const [raw, mapped, score] of [["Strong Buy", "Strongly positive", 60], ["Buy", "Positive", 30], ["Hold", "Neutral", 0], ["Reduce", "Negative", -30], ["Sell", "Strongly negative", -60]] as const)
      expect(ratingWord(mapped, score)).toEqual(ratingWord(raw, score));
  });
  it("the alignment on the screen is the one the API sends with the report", () => {
    for (const k of Object.keys(built) as (keyof typeof built)[]) {
      const v = built[k] as unknown as { shortTerm: { score: number }; longTerm: { score: number }; trendAlignment: { label: string; code: string; tone: string; cells: unknown[] }; verdict: { label: string; tone: string } };
      const mine = trendAlignment(v.shortTerm.score, v.longTerm.score)!;
      expect([mine.label, mine.code, mine.tone]).toEqual([v.trendAlignment.label, v.trendAlignment.code, v.trendAlignment.tone]);
      expect(v.verdict).toEqual({ label: mine.label, tone: mine.tone });
      expect(JSON.parse(JSON.stringify(mine.cells.map((c) => ({ stBand: c.stBand, ltBand: c.ltBand, code: c.code, label: c.label, tone: c.tone, current: c.current }))))).toEqual(v.trendAlignment.cells);
    }
  });
});

describe("trend alignment and the build-up on the report page", () => {
  const html = (a: unknown, rc?: () => void) => renderToStaticMarkup(<Technical report={withTech(a)} onRecalculate={rc} />);
  it.each(Object.keys(built))("%s: the alignment label, the nine-cell map with the current cell marked once, no advice word", (k) => {
    const v = (built as unknown as Record<string, { shortTerm: { score: number }; longTerm: { score: number } }>)[k];
    const h = html(v), t = strip(h), al = trendAlignment(v.shortTerm.score, v.longTerm.score)!;
    expect(t).toContain("Trend alignment"); expect(t).toContain(al.label);
    expect(t).toContain("Trend map: the short-term band down the side, the long-term band across the top");
    for (const c of al.cells) expect(t).toContain(c.label);
    expect((h.match(/aria-current="true"/g) || []).length).toBe(1);
    expect(h).not.toMatch(FORBIDDEN);
    expect(h).not.toMatch(/<(span|p|li)\b[^>]*\baria-label=/);
  });
  it("renders the trend map alone with the highlighted cell", () => {
    const h = renderToStaticMarkup(<TrendMap al={trendAlignment(-30, 25)!} />);
    expect((h.match(/pzt-mc /g) || []).length).toBe(9);
    expect(h).toMatch(/pzt-mc neg now[^>]*aria-current="true"|pzt-mc pos now[^>]*aria-current="true"/);
    expect(strip(h)).toContain("Short-term pullback within a long-term uptrend");
  });
  it("the build-up table: every row with reading, signal, weight and points; the points add up to the score", () => {
    const v = built.smallcap_stage2 as never as { shortTerm: { score: number; divisor: number; factors: { key: string; label: string; signal: number | null; weight?: number; points?: number; status: string }[] }; longTerm: { score: number; divisor: number; factors: { points?: number; status: string }[] } };
    const t = strip(html(v));
    expect(t).toContain("How these scores are built");
    expect(t).toContain("Short term: how the score is built"); expect(t).toContain("Long term: how the score is built");
    for (const c of ["Reading now", "Signal", "Weight", "Points", "Total of the points", "weights in use 96", "weights in use 92"]) expect(t).toContain(c);
    for (const f of v.shortTerm.factors.filter((x) => x.status === "available")) { expect(t).toContain(f.label.replace("&", "&")); expect(t).toContain(fmtSignal(f.signal as number)); expect(t).toContain(fmtPoints(f.points as number)); }
    const sum = (rows: { points?: number }[]) => rows.reduce((s, f) => s + (f.points ?? 0), 0);
    expect(sum(v.shortTerm.factors)).toBeCloseTo(v.shortTerm.score, 9);
    expect(sum(v.longTerm.factors)).toBeCloseTo(v.longTerm.score, 9);
    expect(v.shortTerm.divisor).toBe(96); expect(v.longTerm.divisor).toBe(92);
    expect(t).toContain("Switched off in this model");
    expect(t).toContain("How it is read");
    for (const how of [HOW.st.ema_stack, HOW.lt.stage]) expect(t).toContain(how.slice(0, 40));
  });
  it("the ADX trend factor and the stage limit are explained from the report's own numbers", () => {
    const t = strip(html(built.stage3_cap_binds));
    expect(t).toMatch(/Trend factor\. ADX is \d+\.\d, so the first three rows/);
    expect(t).toMatch(/×(1\.00|0\.75|0\.50)/);
    expect(t).toContain("Market stage."); expect(t).toContain("Stage 3: topping");
    expect(t).toMatch(/\+21\.20 became \+19/);
    const t2 = strip(html(built.smallcap_stage2));
    expect(t2).toContain("The +19 limit applies only in Stage 3 and Stage 4.");
  });
  it("a report stored before the breakdown existed still shows the alignment, says why there is no table, and offers a recalculation", () => {
    const t = strip(html(fx.ready, () => undefined));
    expect(t).toContain("Strong on both timeframes");
    expect(t).toContain("This stored report was made before the breakdown existed");
    expect(t).toContain("Recalculate to add the breakdown");
    expect(t).not.toContain("Total of the points");
    expect(strip(html(fx.ready))).not.toContain("Recalculate to add the breakdown");
  });
  it("every string of the breakdown passes the compliance scan", () => {
    for (const k of Object.keys(built)) for (const s of allShownText(parseTechnical((built as Record<string, unknown>)[k])!)) expect(s, s).not.toMatch(FORBIDDEN);
    expect(Object.values(HOW.st).concat(Object.values(HOW.lt)).filter((x) => FORBIDDEN.test(x))).toEqual([]);
  });
});

describe("the stock page row shows the alignment under both bars", () => {
  const L = (a?: unknown) => ({ technicalAssessment: a }) as unknown as PrismLatest;
  it("label, shape and a spoken summary; nothing when a score is missing", () => {
    const h = renderToStaticMarkup(<PrismTechRow report={L(built.smallcap_stage2)} />), t = strip(h);
    expect(t).toContain("Trend alignment"); expect(t).toContain("Long-term uptrend, short-term pause");
    expect(h).toContain("Trend alignment: Long-term uptrend, short-term pause.");
    expect(h).not.toMatch(FORBIDDEN);
    expect(strip(renderToStaticMarkup(<PrismTechRow report={L(fx.incomplete)} />))).not.toContain("Trend alignment");
  });
});
