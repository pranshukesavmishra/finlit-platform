// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CompanyBriefSection } from "./CompanyBrief";
import RELIANCE from "../lib/fixtures/companyBriefReliance.json";
import { citeUrl, citedPages, shares, shortName, type Brief, type BriefReply } from "../lib/companyBrief";

const brief = RELIANCE as unknown as Brief;
const chipMap = (b: Brief) => Object.fromEntries(Object.entries(b.docs).map(([k, d]) => [k, ({ "Annual report": "AR", "Press release": "PR", "Investor presentation": "IP", "Results filing": "RES" } as Record<string, string>)[d.kind] ?? "EV"]));
const published = (over: Partial<Extract<BriefReply, { state: "published" }>> = {}): BriefReply => ({ symbol: "RELIANCE", name: "Reliance Industries Ltd", state: "published", brief: { ...brief, status: "reviewed" }, asOf: "2026-11-04", reviewedAt: "2026-11-05T05:00:00Z",
  stale: false, changes: null, checks: { date: "2026-11-04", citations: 65, passed: 65, unchecked: 0, fixed: [], method: "Each quoted string must appear on the cited PDF page." }, chips: chipMap(brief),
  disclaimer: brief.disclaimer!, compliance: "Describes the company's financial health from its filings and prices; not a recommendation. Information only, not investment advice.", ...over });

function serve(reply: unknown, status = 200) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async () => ({ ok: status < 400, status, headers: new Headers(), json: async () => reply, text: async () => JSON.stringify(reply) }) as Response);
}
const mount = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><CompanyBriefSection symbol="RELIANCE" /></QueryClientProvider>);
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("company brief section", () => {
  it("shows a loading skeleton, then the whole published brief with its citations", async () => {
    serve(published());
    mount();
    expect(screen.getByRole("status", { name: /loading the company brief/i })).toBeTruthy();
    await screen.findByText(/About Reliance Industries Ltd, from its own filings/);
    expect(screen.getByText(/^Reviewed/)).toBeTruthy();
    for (const h of ["Key figures", "How the group is held", "The businesses and their latest figures", "Where the money comes from", "Recent developments", "What is missing"]) expect(screen.getByRole("heading", { name: new RegExp(h) })).toBeTruthy();
    expect(screen.getByText(/Reliance.s share of each company/)).toBeTruthy();
    expect(screen.getByText("66.43%")).toBeTruthy();
    expect(screen.getByText(/Oil to Chemicals/)).toBeTruthy();
    expect(screen.getByText("Share of EBITDA", { exact: false })).toBeTruthy();
    expect(screen.getAllByRole("link", { name: /^Open Integrated Annual Report 2025-26.*page 131/ })[0].getAttribute("href")).toBe("https://www.ril.com/reports/RIL-Integrated-Annual-Report-2025-26.pdf#page=131");
    expect(document.querySelectorAll(".cb-cite").length).toBeGreaterThan(40);
    const det = screen.getByText("Sources and checks").closest("details")!;
    expect(within(det).getByText(/65 of 65/)).toBeTruthy();
    expect(within(det).getAllByRole("link").length).toBeGreaterThan(8);
    expect(screen.getByText(/Written from the company's own filings/)).toBeTruthy();
    expect(screen.getByText(/not a recommendation. Information only, not investment advice/)).toBeTruthy();
    expect(screen.getByText(/stake in Jio Platforms after the IPO/i)).toBeTruthy();
  });

  it("says why when there is no published brief, never a guess", async () => {
    serve({ symbol: "X", state: "empty", code: "no_annual_report", reason: "No annual report is on file for this company yet, so its brief has not been written.", disclaimer: "d", compliance: "Describes the company's financial health from its filings and prices; not a recommendation. Information only, not investment advice." });
    mount();
    await screen.findByText(/No annual report is on file/);
    expect(screen.queryByText("Key figures")).toBeNull();
    expect(screen.getByText(/not a recommendation/)).toBeTruthy();
  });

  it("offers a retry when the server cannot be reached", async () => {
    serve({ detail: { status: "error" } }, 500);
    mount();
    await screen.findByText(/could not be loaded/);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
  });

  it("notes what changed, a stale brief and a waiting draft honestly", async () => {
    serve(published({ stale: true, waiting: true, changes: { since: "2026-11-04", now: "2027-01-20", parts: ["key_figures", "mix"] } }));
    mount();
    await screen.findByText(/may be behind/);
    expect(screen.getByText(/key figures, where the money comes from rewritten from newer filings/)).toBeTruthy();
    expect(screen.getByText(/newer draft is waiting for review/)).toBeTruthy();
  });

  it("an automatically checked brief says so and claims no human review", async () => {
    serve(published({ publishMode: "auto", reviewedAt: null }));
    mount();
    await screen.findByText(/About Reliance/);
    expect(screen.getByText("Checked automatically")).toBeTruthy();
    expect(screen.getByText("Checked automatically against the filings; every line cites its page.")).toBeTruthy();
    expect(screen.queryByText(/^Reviewed/)).toBeNull();
  });

  it("a citation without a document address is shown but not linked", async () => {
    const b = JSON.parse(JSON.stringify(brief)) as Brief;
    delete b.docs.AR.url;
    serve(published({ brief: b }));
    mount();
    await screen.findByText(/About Reliance/);
    expect(document.querySelectorAll(".cb-cite.off").length).toBeGreaterThan(0);
  });
});

describe("brief helpers", () => {
  it("links only https filings and opens the cited page", () => {
    expect(citeUrl({ title: "t", kind: "k", url: "https://a.example/x.pdf" }, 7)).toBe("https://a.example/x.pdf#page=7");
    expect(citeUrl({ title: "t", kind: "k", url: "javascript:alert(1)" }, 7)).toBeNull();
    expect(citeUrl({ title: "t", kind: "k", url: "http://a.example/x.pdf" }, 7)).toBeNull();
    expect(citeUrl(undefined, 1)).toBeNull();
  });
  it("shares use the stated percentage, else the row's part of the rows", () => {
    expect(shares({ rows: [{ name: "A", value_cr: 25, share_pct: 40.4 }], cites: [] })[0].pct).toBe(40.4);
    expect(shares({ rows: [{ name: "A", value_cr: 25 }, { name: "B", value_cr: 75 }], cites: [] }).map((r) => r.pct)).toEqual([25, 75]);
    expect(shares(undefined)).toEqual([]);
  });
  it("lists every cited filing with its pages", () => {
    const c = citedPages(brief);
    expect(c.length).toBeGreaterThan(5);
    expect(c.find((x) => x.key === "AR")!.pages).toContain(131);
    expect(shortName("Reliance Industries Ltd")).toBe("Reliance");
  });
});

// Wording rule: the page and its admin describe, they never advise. The words below are not used in any text we write (the filings' own words are the company's).
const BANNED = /\b(buy|sell|hold|reduce|avoid|accumulate|target|best|multibagger|top pick)\b/i;
describe("wording", () => {
  const files = ["CompanyBrief.tsx", "../lib/companyBrief.ts", "../components/admin/BriefAdmin.tsx"];
  it.each(files)("%s has no advice words in its text", (f) => {
    const src = readFileSync(new URL(f, import.meta.url), "utf8").replace(/target="_blank"/g, "").replace(/\.target\b/g, "").replace(/\bBANNED\b/g, "");
    const hits = src.split("\n").map((l, i) => [i + 1, l] as const).filter(([, l]) => BANNED.test(l));
    expect(hits).toEqual([]);
  });
  it("the rendered page chrome, around neutral brief text, has none", async () => {
    const neutral: Brief = { symbol: "ACME", name: "Acme Ltd", as_of: "2026-10-30", docs: { AR: { title: "Annual report", kind: "Annual report", url: "https://a.example/ar.pdf" } },
      about: [{ text: "Acme makes chemicals.", cites: [{ doc: "AR", page: 2, needles: ["chemicals"] }] }], segments: [{ name: "Chemicals", what: "Makes chemicals.", what_cites: [{ doc: "AR", page: 2 }], points: [] }],
      recent: [{ date: "2026-10-30", title: "Results", text: "Revenue rose.", cites: [{ doc: "AR", page: 3 }] }], gaps: [] };
    serve(published({ brief: neutral, chips: { AR: "AR" }, checks: { date: "2026-10-30", citations: 3, passed: 3, unchecked: 0, fixed: [] }, disclaimer: "Written from the company's own filings." }));
    mount();
    await screen.findByText(/About Acme Ltd/);
    expect((document.querySelector(".cb")!.textContent || "").match(BANNED)).toBeNull();
  });
});
