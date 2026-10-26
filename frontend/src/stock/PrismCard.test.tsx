import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// The card is rendered on the server side of React: the stored report is fetched first (with a fake fetch) into the query cache,
// then the half is drawn from it. The plan is stubbed so the test does not load the whole stock page.
const plan = vi.hoisted(() => ({ gold: true }));
vi.mock("../lib/premium", () => ({ useGold: () => plan.gold }));
vi.mock("../lib/ui", () => ({
  TIER: { basic: { n: "Basic", ic: "sprout", tc: "--t-basic" }, silver: { n: "Silver", ic: "medal", tc: "--t-silver" }, gold: { n: "Gold", ic: "crown", tc: "--t-gold" } },
  useUI: () => ({ has: (t: string) => t === "basic" || plan.gold, upgrade: () => undefined, plan: plan.gold ? "gold" : "basic" }),
}));

import { OpenAccess } from "../components/Gate";
import { loadPrismLatest, prismSummary, type PrismLatest } from "./PrismCard";
import { PrismCompare, PrismMethod } from "./PrismCompare";
import { PRISM_NOTE, PRISM_POINTS } from "./prismWords";

const REPORT: PrismLatest = {
  id: "a".repeat(32), createdAt: "2026-10-20T09:00:00Z", completedAt: "2026-10-20T09:01:00Z", statementType: "consolidated", company: { symbol: "TCS", name: "Tata Consultancy Services" },
  rating: { final: 71.26, label: "HEALTHY", status: "PROVISIONAL", parts: { fundamental: 78.4, valuation: 52, quality: 81, risk: null }, confidence: 0.764, modelVersion: "3.6.10" },
  review: { parts: [
    { key: "fundamental", name: "Fundamentals", pros: [{ metric: "PROFIT_CAGR", label: "Profit growth over years", valueText: "14%", summary: "Profit has compounded steadily." }, { metric: "A", label: "Second pro", valueText: "", summary: "s" }, { metric: "B", label: "Third pro", valueText: "", summary: "s" }], cons: [{ metric: "MARGIN_CHANGE", label: "Margin change", valueText: "-2 pp", summary: "Margins slipped." }] },
    { key: "valuation", name: "Valuation", pros: [], cons: [{ metric: "PE_REL", label: "P/E against industry", valueText: "1.4x", summary: "Priced above its industry." }] },
  ] },
};

const fetchMock = vi.fn();
const answer = (status: number, body: unknown) => fetchMock.mockResolvedValue(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
beforeEach(() => { fetchMock.mockReset(); vi.stubGlobal("fetch", fetchMock); plan.gold = true; });
afterEach(() => { vi.unstubAllGlobals(); });

async function render(symbol = "TCS", open = false) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  if (plan.gold || open) await qc.prefetchQuery({ queryKey: ["prism-latest", symbol, "consolidated"], queryFn: () => loadPrismLatest(symbol, "consolidated") });
  return renderToStaticMarkup(
    <QueryClientProvider client={qc}><MemoryRouter><OpenAccess.Provider value={open}>
      <PrismCompare symbol={symbol} name="Tata Consultancy Services" statement="consolidated" />
    </OpenAccess.Provider></MemoryRouter></QueryClientProvider>,
  );
}
const text = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/&#x27;/g, "'").replace(/&amp;/g, "&").replace(/\s+/g, " ");

describe("FinLit Prism card", () => {
  it("shows a Gold member the stored rating: label, score, status in words, four parts, coverage, date and the report link", async () => {
    answer(200, REPORT);
    const html = await render();
    expect(String(fetchMock.mock.calls[0][0])).toBe("/api/prism/reports/latest?symbol=TCS&statement=consolidated");
    const t = text(html);
    expect(t).toContain("Healthy");
    expect(t).toContain("71.3");
    expect(t).toContain("Provisional rating");
    for (const part of ["Fundamentals", "Valuation", "Quality", "Risk"]) expect(t).toContain(part);
    expect(t).toContain("78");
    expect(t).toContain("No data");   // the missing Risk part says so instead of showing zero
    expect(t).toContain("76% of inputs available");
    expect(t).toContain("20 Oct 2026");
    expect(t).toContain("Profit growth over years");   // the top two pros and cons
    expect(t).toContain("Second pro");
    expect(t).not.toContain("Third pro");
    expect(t).toContain("Priced above its industry.");
    expect(t).toContain("Recalculate");
    expect(t).toContain("Technical view: recalculate to add");   // an older stored report: a quiet line, no invented number
    expect(t).not.toContain("coming soon");
    expect(html.match(/class="dk-tile"/g)).toHaveLength(4);
    expect(html).toContain('href="/prism/TCS"');
    expect(t).toContain("Open the full Prism report");
    expect(t).toContain(PRISM_NOTE);   // the compliance line
    expect(html).toContain(`aria-label="${prismSummary(REPORT.rating)}"`);
    expect(prismSummary(REPORT.rating)).toBe("FinLit Prism rating: Healthy, 71.3 out of 100, provisional rating. 76% of inputs available.");
  });

  it("draws a technical part by itself the moment the model sends one", async () => {
    answer(200, { ...REPORT, rating: { ...REPORT.rating, parts: { ...REPORT.rating.parts, technical: 44 }, partWeights: { fundamental: 0.3, valuation: 0.25, quality: 0.2, risk: 0.1, technical: 0.15 } } });
    const html = await render();
    const t = text(html);
    expect(t).toContain("Technical");
    expect(t).toContain("15%");
    expect(html).toContain('aria-label="Technical: 44 out of 100, weak. 15% of the score"');
    expect(html.match(/class="dk-tile"/g)).toHaveLength(5);   // a normal fifth tile, not a separate box
    expect(t).not.toContain("coming soon");
  });

  it("says Not rated, with no score, when the model could not rate the company", async () => {
    answer(200, { ...REPORT, rating: { ...REPORT.rating, final: null, label: "NOT RATED", status: "NOT RATED", confidence: 0.4 } });
    const t = text(await render());
    expect(t).toContain("Not rated");
    expect(t).not.toContain("out of 100");
    expect(t).toContain("40% of inputs available");
  });

  it("shows no category score for a company that is not rated (the parts exist in the data but are withheld)", async () => {
    answer(200, { ...REPORT, rating: { ...REPORT.rating, final: null, label: "NOT RATED", status: "NOT RATED", confidence: 0.4 } });
    const html = await render();
    expect(html).not.toMatch(/aria-label="[^"]*\d+ out of 100/);
    expect(html).toContain("Fundamentals: no data");
  });

  it("offers a Gold member the Prism page when no report is stored yet", async () => {
    answer(404, { detail: { status: "none" } });
    const html = await render();
    const t = text(html);
    expect(t).toContain("No Prism rating for Tata Consultancy Services yet");
    expect(t).toContain("Generate the Prism rating");
    expect(html).toContain('href="/prism/TCS"');
    expect(t).not.toContain("Open the full Prism report");
    expect(t).not.toContain("Recalculate");
  });

  it("shows other plans the Gold unlock card with three plain points, without asking the server", async () => {
    plan.gold = false;
    const html = await render();
    expect(fetchMock).not.toHaveBeenCalled();
    const t = text(html);
    expect(html).toContain("gate is-locked");
    expect(t).toContain("Unlock FinLit Prism");
    for (const p of PRISM_POINTS) expect(t).toContain(p);
    expect(t).toContain("Example");   // the numbers behind the lock are marked as made up
  });

  it("asks the server on a free example company, for every plan", async () => {
    plan.gold = false;
    answer(200, REPORT);
    const html = await render("TCS", true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(html).not.toContain("is-locked");
    expect(text(html)).toContain("Open the full Prism report");
  });

  it("locks the card when the server refuses the plan", async () => {
    plan.gold = false;
    answer(403, { detail: { status: "plan_required", detail: "FinLit Prism is part of Gold.", plan: "gold" } });
    const html = await render("TCS", true);
    expect(html).toContain("gate is-locked");
  });

  it("hides itself quietly on any other failure, so the page carries on", async () => {
    for (const [status, body] of [[500, { detail: "boom" }], [503, { detail: { status: "unavailable" } }], [404, { detail: "Not Found" }], [200, { nothing: true }]] as const) {
      answer(status, body);
      expect(await render()).toBe("");
    }
    fetchMock.mockRejectedValue(new TypeError("network down"));
    expect(await render()).toBe("");
  });

  it("shows the Prism pros and cons by part in the Pros and cons section, only when a report exists", async () => {
    const qc = new QueryClient();
    const draw = () => renderToStaticMarkup(<QueryClientProvider client={qc}><MemoryRouter><PrismMethod symbol="TCS" statement="consolidated" /></MemoryRouter></QueryClientProvider>);
    expect(draw()).toBe("");
    answer(200, REPORT);
    await qc.prefetchQuery({ queryKey: ["prism-latest", "TCS", "consolidated"], queryFn: () => loadPrismLatest("TCS", "consolidated") });
    const t = text(draw());
    expect(t).toContain("pros and cons by part");
    expect(t).toContain("Margins slipped.");
    expect(t).toContain("Third pro");
  });

  it("hides itself rather than locking a Gold member the server does not recognise", async () => {
    answer(403, { detail: { status: "plan_required" } });
    expect(await render()).toBe("");
  });
});

describe("FinLit Prism wording", () => {
  const BANNED = /\b(buy|buying|sell|selling|avoid|target)\b/i;
  it("never says buy, sell, avoid or target in the card, the hub card, the plans copy or the glossary entries", async () => {
    const files = ["./PrismCard.tsx", "./PrismCompare.tsx", "./prismWords.ts"].map((f) => readFileSync(new URL(f, import.meta.url), "utf8"));
    for (const f of files) for (const s of f.match(/"[^"\n]{12,}"|>[^<>{}\n]{12,}</g) ?? []) expect(s, s).not.toMatch(BANNED);
    const hub = readFileSync(new URL("../pages/Premium.tsx", import.meta.url), "utf8");
    const card = hub.slice(hub.indexOf("function PrismHubCard"), hub.indexOf("/** Locked view"));
    expect(card.length).toBeGreaterThan(200);
    expect(card).not.toMatch(BANNED);
    const glossary = JSON.parse(readFileSync(new URL("../content/glossary.json", import.meta.url), "utf8")) as { terms: { id: string; meaning: string; why: string; how: string; finlit: string }[] };
    const ours = glossary.terms.filter((t) => ["finlit-prism", "coverage-prism", "provisional-rating"].includes(t.id));
    expect(ours).toHaveLength(3);
    for (const t of ours) expect(`${t.meaning} ${t.why} ${t.how} ${t.finlit}`).not.toMatch(BANNED);
    // and what the reader actually sees, in every state
    for (const [status, body] of [[200, REPORT], [404, { detail: { status: "none" } }]] as const) { answer(status, body); expect(text(await render())).not.toMatch(BANNED); }
    plan.gold = false; expect(text(await render())).not.toMatch(BANNED);
  });
});
