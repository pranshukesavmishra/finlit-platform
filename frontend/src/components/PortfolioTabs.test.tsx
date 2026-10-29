import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { StaticRouter } from "react-router";
import fx from "../lib/__fixtures__/portfolioOverview.json";
import { PortfolioTable, SummaryTiles, TabStrip } from "./PortfolioTabs";
import { isReady, type Line, type Model, type Overview, type Period, type Tab } from "../lib/portfolioOverview";

const silver = fx.silver as unknown as Overview, gold = fx.gold as unknown as Overview;
const lines = (o: Overview): Line[] => o.holdings.map((h) => ({ symbol: h.symbol, name: isReady(h) ? h.name : null, ov: h }));
const noop = () => {};
const table = (o: Overview, model: Model, tab: Tab, period: Period = "year", state: "loading" | "ready" | "error" = "ready", ls = lines(o)) =>
  renderToStaticMarkup(<StaticRouter location="/portfolio"><PortfolioTable lines={ls} model={model} tab={tab} period={period} limit={o.plan === "gold" ? 500 : 30} state={state} onPeriod={noop} onExport={noop}
    actions={(s) => <button>Remove {s}</button>} /></StaticRouter>);
const text = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");

describe("tab strip", () => {
  it("is an accessible tablist with the selected tab tabbable", () => {
    const html = renderToStaticMarkup(<TabStrip tab="ratios" onTab={noop} />);
    expect(html).toContain('role="tablist"');
    expect((html.match(/role="tab"/g) || []).length).toBe(3);
    expect(html).toMatch(/id="pf-tab-ratios"[^>]*aria-selected="true"[^>]*aria-controls="pf-panel"[^>]*tabindex="0"/);
    expect(html).toMatch(/id="pf-tab-overview"[^>]*aria-selected="false"[^>]*tabindex="-1"/);
    expect(text(html)).toContain("Overview Ratios Financials");
  });
});

describe("Overview tab", () => {
  it("Silver: FinLit score with its word and the five pillars; nothing of Prism", () => {
    const t = text(table(silver, "finlit", "overview"));
    expect(t).toContain("FinLit score"); ["Quality", "Growth", "Profit.", "Balance", "Technical"].forEach((x) => expect(t).toContain(x));
    expect(t).toContain("Reliance Industries Ltd"); expect(t).toContain("₹1,184.00"); expect(t).toContain("₹16,02,253 Cr"); expect(t).toContain("Large cap"); expect(t).toContain("Strong");
    expect(t).not.toMatch(/Prism|Fundamentals|Valuation|Risk|Rate now/);
    expect(t).toContain("Portfolio average"); expect(t).toContain("Preparing… Its report is being prepared"); expect(t).toContain("FinLit does not list a company");
  });
  it("Gold: Prism score and word, the four parts, two technical views with words and signed scores; no FinLit pillars", () => {
    const html = table(gold, "prism", "overview"), t = text(html);
    expect(t).toContain("Prism score"); ["Fundamentals", "Valuation", "Quality", "Risk", "Short term", "Long term"].forEach((x) => expect(t).toContain(x));
    expect(t).not.toMatch(/Growth|Profit\.|Balance|Technical|FinLit score/);
    expect(t).toContain("Healthy"); expect(t).toContain("Positive"); expect(t).toContain("Strongly positive"); expect(t).toContain("Negative"); expect(t).toContain("+34"); expect(t).toContain("−22");
    expect(html).toContain("ssp pzs-n hi"); expect(html).toContain("ssp pzs-n lo");                       // the shared colour bands
    expect(t).toContain("Provisional");
    expect(html).toContain('href="/prism/SAMPLEPHARMA"'); expect(t).toContain("Not rated yet"); expect(t).toContain("Rate now");     // a company with no stored rating
    expect(t).toMatch(/Not rated/);
  });
  it("lists every share with a link to its page, the size word and the remove button", () => {
    const html = table(silver, "finlit", "overview");
    expect(html).toContain('href="/stocks/RELIANCE"'); expect(html).toContain("Remove SAMPLEIT"); expect(html).toContain("Mid cap");
  });
  it("has the filter chips, search box and Export CSV", () => {
    const t = text(table(silver, "finlit", "overview"));
    expect(t).toContain("Green"); expect(t).toContain("Orange"); expect(t).toContain("Red"); expect(t).toContain("Not scored"); expect(t).toContain("Export CSV");
  });
});

describe("Ratios tab", () => {
  it("shows the stock page's figures with their reasons when blank", () => {
    const html = table(silver, "finlit", "ratios"), t = text(html);
    ["Dividend yield (%)", "P/E", "ROE (%)", "Debt to equity (x)", "P/BV (x)"].forEach((x) => expect(t).toContain(x));
    expect(t).toContain("41.36"); expect(t).toContain("6.93"); expect(t).toContain("0.41"); expect(t).toContain("2.86"); expect(t).toContain("0.51");
    expect(html).toContain("Not applicable to banks and lenders"); expect(html).toContain("Loss-making");
    expect(html).toContain("As of 28 Sep 2026");                                         // the period is the hover text
    expect(t).not.toMatch(/Industry P\/E:/);
  });
  it("Gold keeps its model's score column", () => {
    const t = text(table(gold, "prism", "ratios"));
    expect(t).toContain("Prism score"); expect(t).not.toContain("FinLit score");
  });
});

describe("Financials tab", () => {
  it("latest year: year end, basis, statements, tax ratio; banks say operating profit is not applicable", () => {
    const html = table(silver, "finlit", "financials"), t = text(html);
    ["Year end", "Statement", "Net sales / revenue", "Other income", "Operating profit", "Interest paid", "Tax ratio", "Net profit", "EPS"].forEach((x) => expect(t).toContain(x));
    expect(t).toContain("Mar-26"); expect(t).toContain("5,24,105"); expect(t).toContain("43,851"); expect(t).toContain("32.40"); expect(t).toContain("18.9");
    expect(html).toContain("Not applicable to banks and lenders: their interest is their business");
    expect(t).toContain("Latest year"); expect(t).toContain("Latest quarter");
  });
  it("latest quarter", () => {
    const t = text(table(silver, "finlit", "financials", "quarter"));
    expect(t).toContain("Quarter end"); expect(t).toContain("Jun-26"); expect(t).toContain("13,272");
  });
});

describe("states", () => {
  it("empty list, loading and error", () => {
    expect(text(table(silver, "finlit", "overview", "year", "ready", []))).toContain("No shares yet");
    const loading = table(silver, "finlit", "overview", "year", "loading", silver.holdings.map((h) => ({ symbol: h.symbol, name: null })));
    expect(text(loading)).toContain("Loading the scores"); expect(text(loading)).toContain("Preparing…");
    expect(table(silver, "finlit", "ratios", "year", "error", [])).toContain('role="alert"');
  });
});

describe("summary tiles", () => {
  it("shares, average score, colour mix and sectors", () => {
    const t = text(renderToStaticMarkup(<SummaryTiles lines={lines(silver)} model="finlit" limit={30} />));
    expect(t).toContain("Shares"); expect(t).toContain("7"); expect(t).toContain("1 being prepared"); expect(t).toContain("Average FinLit score"); expect(t).toContain("59"); expect(t).toContain("average of 5 scored shares");
    expect(t).toContain("green 70+"); expect(t).toContain("Sectors");
    expect(text(renderToStaticMarkup(<SummaryTiles lines={lines(gold)} model="prism" limit={500} />))).toContain("Average Prism score");
  });
});

describe("compliance", () => {
  it("no buy, sell or hold wording on any tab for any plan", () => {
    const all = [table(silver, "finlit", "overview"), table(silver, "finlit", "ratios"), table(silver, "finlit", "financials"), table(gold, "prism", "overview"), table(gold, "prism", "ratios"), table(gold, "prism", "financials", "quarter"),
      renderToStaticMarkup(<SummaryTiles lines={lines(gold)} model="prism" limit={500} />)].map(text).join(" ");
    expect(all).not.toMatch(/\b(buy|sell|hold|reduce|avoid|accumulate|target)\b/i);
    expect(all).toContain("Information only, not investment advice");
  });
});
