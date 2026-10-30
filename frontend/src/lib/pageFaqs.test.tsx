// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import { render, screen, fireEvent, cleanup } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { PAGE_FAQS } from "../content/pageFaqs";
import { faqForPath, matchScore } from "./pageFaqs";
import { PageFaqs } from "../components/PageFaqs";
import { FaqsPage } from "../pages/Faqs";

const src = (p: string) => resolve(__dirname, "..", p);
const json = JSON.parse(readFileSync(resolve(__dirname, "../../../scripts/data/page-faqs.json"), "utf8")) as (typeof PAGE_FAQS[number] & { declared: number })[];

describe("page FAQ data (built from the PDF by scripts/build-page-faqs.py)", () => {
  it("has 32 pages and 228 questions, as the PDF header says", () => {
    expect(PAGE_FAQS).toHaveLength(32);
    expect(PAGE_FAQS.reduce((n, f) => n + f.items.length, 0)).toBe(228);
  });
  it("every page has the number of questions its 'N questions' line declares", () => {
    expect(json).toHaveLength(32);
    for (const p of json) expect(p.items.length, p.title).toBe(p.declared);
  });
  it("the TS file is the JSON without the bookkeeping field", () => {
    expect(PAGE_FAQS).toEqual(json.map(({ declared: _d, ...rest }) => rest));
  });
  it("ids are unique, questions end with '?', nothing is empty", () => {
    expect(new Set(PAGE_FAQS.map((f) => f.id)).size).toBe(32);
    for (const f of PAGE_FAQS) for (const it of f.items) { expect(it.q.endsWith("?"), it.q).toBe(true); expect(it.a.length).toBeGreaterThan(5); expect(it.a).not.toMatch(/\s{2}|\n/); }
  });
  it("keeps verbatim text: typographic quotes, rupee signs, multi-line joins, plans, routes", () => {
    const dash = PAGE_FAQS.find((f) => f.id === "dashboard")!;
    expect(dash.items[2].q).toBe("What is the difference between “Market” and “My stocks” on a widget?");
    expect(dash.items[5].a).toBe("Sectors are grouped from the exchange's industry list. Each block is sized by the sector's total market value and coloured by its cap-weighted move today. Companies below ₹100 crore are left out.");
    expect(dash.items[6].a).toContain("A flag is a reason to look closer, not a reason to buy or sell.");
    const score = PAGE_FAQS.find((f) => f.id === "basic-score-screener")!;
    expect(score.plan).toBe("Silver (full table)");
    expect(PAGE_FAQS.find((f) => f.id === "company-report")!.routes).toEqual(["/research", "/stocks/:symbol"]);
    expect(PAGE_FAQS.find((f) => f.id === "sip-calculator")!.plan).toBe("Free, no sign-in");
  });
});

describe("route matching", () => {
  it("every PDF route exists in App.tsx (parameter names may differ)", () => {
    const app = readFileSync(src("App.tsx"), "utf8");
    const real = [...app.matchAll(/<Route path="([^"*]+)"/g)].map((m) => "/" + m[1]);
    for (const f of PAGE_FAQS) for (const r of f.routes) expect(real.some((p) => matchScore(p, r.replace(/:\w+/g, "x")) >= 0 && matchScore(r, p.replace(/:\w+/g, "x")) >= 0), `${f.title} ${r}`).toBe(true);
  });
  it("maps plain, parameter, trailing-slash, query and case variants", () => {
    expect(faqForPath("/dashboard")?.id).toBe("dashboard");
    expect(faqForPath("/dashboard/")?.id).toBe("dashboard");
    expect(faqForPath("/screener?q=roe&x=1#top")?.id).toBe("stock-screener");
    expect(faqForPath("/Score-Screener")?.id).toBe("basic-score-screener");
    expect(faqForPath("/stocks/TCS")?.id).toBe("company-report");
    expect(faqForPath("/research")?.id).toBe("company-report");
    expect(faqForPath("/prism/INFY")?.id).toBe("finlit-prism");
    expect(faqForPath("/graphs/advanced/valuation")?.id).toBe("correlation-charts");
    expect(faqForPath("/graphs")?.id).toBe("chart-builder");
    expect(faqForPath("/premium/report/TCS")?.id).toBe("premium-reports");
    expect(faqForPath("/funds/insights")?.id).toBe("fund-industry-trends");
    expect(faqForPath("/funds")?.id).toBe("mutual-funds");
  });
  it("returns null where there is no set", () => {
    for (const p of ["/", "/glossary", "/blog", "/blog/x", "/account", "/account/plan", "/login", "/plans", "/funds/123", "/stocks", "/stocks/TCS/extra", "/nope"]) expect(faqForPath(p), p).toBeNull();
  });
  it("every set is reachable from its first route", () => {
    for (const f of PAGE_FAQS) expect(faqForPath(f.routes[0].replace(/:\w+/g, "abc"))?.id).toBe(f.id);
  });
});

describe("<PageFaqs />", () => {
  const at = (p: string) => render(<MemoryRouter initialEntries={[p]}><PageFaqs /></MemoryRouter>);
  it("renders nothing on a page without a set", () => { const { container } = at("/glossary"); expect(container.innerHTML).toBe(""); cleanup(); });
  it("shows title, count, plan, note and the All FAQs link", () => {
    at("/prism/TCS");
    expect(screen.getByRole("heading", { level: 2 }).textContent).toContain("FinLit Prism");
    expect(screen.getByText("8 questions")).toBeTruthy();
    expect(screen.getByText("Plan: Gold")).toBeTruthy();
    expect(screen.getByText("Information only, not investment advice.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "All FAQs" }).getAttribute("href")).toBe("/faq");
    expect(document.getElementById("faq")).not.toBeNull();
    cleanup();
  });
  it("accordion: collapsed by default, toggles, wires aria-expanded/aria-controls/labelledby, several can be open", () => {
    at("/dashboard");
    const btns = screen.getAllByRole("button");
    expect(btns).toHaveLength(9);
    for (const b of btns) { expect(b.getAttribute("aria-expanded")).toBe("false"); expect(document.getElementById(b.getAttribute("aria-controls")!)).not.toBeNull(); }
    fireEvent.click(btns[0]); fireEvent.click(btns[1]);
    expect(btns[0].getAttribute("aria-expanded")).toBe("true"); expect(btns[1].getAttribute("aria-expanded")).toBe("true");
    const panel = document.getElementById(btns[0].getAttribute("aria-controls")!)!;
    expect(panel.getAttribute("role")).toBe("region"); expect(panel.getAttribute("aria-labelledby")).toBe(btns[0].id);
    expect(panel.textContent).toBe(PAGE_FAQS[0].items[0].a);
    fireEvent.click(btns[0]); expect(btns[0].getAttribute("aria-expanded")).toBe("false");
    cleanup();
  });
  it("the All FAQs hub lists every set grouped by section", () => {
    render(<MemoryRouter><FaqsPage /></MemoryRouter>);
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(32);
    expect(screen.getAllByRole("button")).toHaveLength(228);
    expect(screen.getByRole("heading", { level: 2, name: "Gold dashboards" })).toBeTruthy();
    cleanup();
  });
});

describe("old FAQs are gone", () => {
  it("content/faq.ts is deleted and nothing imports it", () => {
    expect(existsSync(src("content/faq.ts"))).toBe(false);
    for (const f of ["App.tsx", "pages/Home.tsx", "pages/Macro.tsx", "components/Layout.tsx", "components/Assistant.tsx"]) expect(readFileSync(src(f), "utf8"), f).not.toMatch(/content\/faq["']|FAQ_GROUPS|const FAQ\b/);
  });
});

describe("compliance scan of the FAQ text", () => {
  // advice wording that is NOT negated in the same sentence
  const ADVICE = [/\byou should (buy|sell|invest|hold|exit|add)\b/i, /\b(we|i) recommend\b/i, /\b(buy|sell) (now|this stock)\b/i, /\bguarantee[ds]?\b/i, /\b(will|going to) (rise|double|fall|crash|outperform)\b/i, /\bsure[- ]shot\b/i, /\bmust[- ](buy|sell|have)\b/i, /\bbest (stock|fund|pick)s?\b/i, /\bassured returns?\b/i];
  const NEG = /\b(not|no|never|nor|cannot|can't|does not|doesn't|isn't|is not|without)\b|n't\b/i;
  it("has no un-negated advice phrases", () => {
    const hits: string[] = [];
    for (const f of PAGE_FAQS) for (const it of f.items) for (const s of (it.q + " " + it.a).split(/(?<=[.?!])\s+/)) for (const re of ADVICE) if (re.test(s) && !NEG.test(s)) hits.push(`${f.id}: ${s}`);
    expect(hits).toEqual([]);
  });
});
