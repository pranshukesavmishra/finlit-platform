// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EarningsCallSection } from "./EarningsCall";
import { callLabel, dayText, loadHistory, pickYear, pushHistory, usageText, yearsOf, type CallDetail, type CallList, type CallRow } from "../lib/earnings";

const QS = [["strategy-moat", "Strategy & moat", "Strategy"], ["guidance-outlook", "Guidance & outlook", "Outlook"], ["margins-costs", "Margins & costs", "Margins"], ["risks-raised", "Risks raised", "Risks"]]
  .map(([id, label, title]) => ({ id, label, title }));
const row = (fy: number, q: number, extra: Partial<CallRow> = {}): CallRow => ({ fiscalYear: fy, quarter: q, label: callLabel(fy, q), callDate: "2026-10-20", filedAt: "2026-10-23", transcriptUrl: `https://nsearchives.nseindia.com/c/${fy}${q}.pdf`, pages: 48, ...extra });
const LIST: CallList = { symbol: "HDFCBANK", name: "HDFC Bank Ltd", available: true, locked: false, calls: [row(2027, 2), row(2027, 1), row(2026, 4)], questions: QS, usage: { used: 1, limit: 5 },
  note: "AI-summarised from the transcript. Check the quotes.", disclaimer: "Information only, not investment advice." };
const DETAIL = (r: CallRow, used = 1): CallDetail => ({ ...r, symbol: "HDFCBANK", name: "HDFC Bank Ltd", usage: { used, limit: 5 }, summarisedByAi: true, note: LIST.note, notCovered: "The call did not cover this.", disclaimer: LIST.disclaimer,
  questions: [
    { ...QS[0], ready: true, covered: true, sentences: [{ text: "Management aims to grow retail deposits faster than the system.", quote: "we want to grow deposits faster than the system over the next two years", quoteRef: "page 4" },
                                                      { text: "It says branch reach is its main advantage.", quote: "our branch network remains the biggest advantage we have", quoteRef: "page 5" }] },
    { ...QS[1], ready: true, covered: true, sentences: [{ text: "Management expects loan growth in line with the system.", quote: "we expect loan growth broadly in line with the system", quoteRef: "page 9" }] },
    { ...QS[2], ready: false, covered: false, sentences: [] },
    { ...QS[3], ready: true, covered: false, sentences: [] },
  ] });

type Reply = { status?: number; body: unknown };
function serve(handler: (url: string) => Reply) {
  const calls: string[] = [];
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    calls.push(url);
    const { status = 200, body } = handler(url);
    return { ok: status < 400, status, headers: new Headers({ "content-type": "application/json" }), json: async () => body, text: async () => JSON.stringify(body) } as Response;
  });
  return calls;
}
const ok = (url: string): Reply => {
  const m = /\/api\/earnings-calls\/HDFCBANK\/(\d+)\/(\d)$/.exec(url);
  if (!m) return { body: LIST };
  return { body: DETAIL(LIST.calls.find((c) => c.fiscalYear === Number(m[1]) && c.quarter === Number(m[2]))!) };
};
const mount = () => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter><EarningsCallSection symbol="HDFCBANK" name="HDFC Bank Ltd" /></MemoryRouter>
  </QueryClientProvider>);
const open = async (label = /Read the call summary/) => { fireEvent.click(await screen.findByRole("button", { name: label })); return await screen.findByRole("dialog"); };

beforeEach(() => { sessionStorage.clear(); });
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("the Earnings call section", () => {
  it("shows a loading state, then the latest call, its question labels and a button; the answers are not on the page yet", async () => {
    serve(ok);
    mount();
    expect(screen.getByRole("status", { name: "Loading the earnings call" })).toBeTruthy();
    expect(await screen.findByText("Q2 FY27 earnings call")).toBeTruthy();
    expect(screen.getByText(/Transcript filed 23 Oct 2026 · 3 calls summarised/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Strategy & moat" })).toBeTruthy();
    expect(screen.queryByText(/aims to grow retail deposits/)).toBeNull();
    expect(document.body.textContent).toContain("AI-summarised from the transcript. Check the quotes.");
    expect(document.body.textContent).toContain("Information only, not investment advice.");
  });

  it("says the summaries are not available yet when no call has been summarised", async () => {
    serve(() => ({ body: { ...LIST, available: false, calls: [] } }));
    mount();
    expect(await screen.findByText("Earnings-call summaries are not available yet")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Read the call summary/ })).toBeNull();
  });

  it("shows an error with a way to try again", async () => {
    let fail = true;
    serve((u) => (fail ? { status: 500, body: { detail: { status: "error" } } } : ok(u)));
    mount();
    const a = await screen.findByRole("alert", undefined, { timeout: 5000 });
    expect(a.textContent).toContain("could not be loaded");
    fail = false;
    fireEvent.click(within(a).getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Q2 FY27 earnings call")).toBeTruthy();
  });
});

describe("the dialog", () => {
  it("opens as a labelled modal on document.body with the call, the rail, the intro and the footer", async () => {
    serve(ok);
    mount();
    const dlg = await open();
    expect(dlg.parentElement).toBe(document.body);
    expect(dlg.getAttribute("aria-modal")).toBe("true");
    expect(within(dlg).getByRole("heading", { name: "HDFC Bank Ltd, Q2 FY27 earnings call" })).toBeTruthy();
    expect(dlg.textContent).toContain("filed 23 Oct 2026, 1 of 5 calls this month");
    expect(dlg.textContent).toContain("Summarised by AI");
    expect(dlg.textContent).toContain("The answers come from this call's transcript.");
    expect(await within(dlg).findByText("I have read the Q2 FY27 call from its transcript and summarised it. What would you like to know?")).toBeTruthy();
    expect(dlg.textContent).toContain("Answers come from the Q2 FY27 transcript only. Where the call does not cover something, the answer says so.");
    expect(within(dlg).getByLabelText("Choose a question about the Q2 FY27 call")).toBeTruthy();
    const link = within(dlg).getByRole("link", { name: /Open PDF/ }) as HTMLAnchorElement;
    expect(link.href).toBe("https://nsearchives.nseindia.com/c/20272.pdf") ; expect(link.rel).toContain("noopener");
    expect(dlg.textContent).toContain("48 pages"); expect(dlg.textContent).toContain("20 Oct 2026");
  });

  it("shows the first answer as a labelled row of sentences, and each quote only when asked for", async () => {
    serve(ok);
    mount();
    const dlg = await open();
    const art = await within(dlg).findByRole("article", { name: "Strategy & moat" });
    expect(within(art).getByText("Strategy")).toBeTruthy();
    expect(art.querySelectorAll("li")).toHaveLength(2);
    expect(art.textContent).not.toContain("we want to grow deposits faster");
    const btns = within(art).getAllByRole("button", { name: "Show the quote" });
    fireEvent.click(btns[0]);
    expect(art.querySelector("blockquote")?.textContent).toContain("we want to grow deposits faster than the system over the next two years");
    expect(art.querySelector("cite")?.textContent).toBe("Q2 FY27, page 4");
    expect(within(art).getByRole("button", { name: "Hide the quote" }).getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(within(art).getByRole("button", { name: "Hide the quote" }));
    expect(art.querySelector("blockquote")).toBeNull();
  });

  it("switches question from a chip or the dropdown; a question the call does not cover says so; an unanswered one is disabled", async () => {
    serve(ok);
    mount();
    const dlg = await open();
    await within(dlg).findByRole("article", { name: "Strategy & moat" });
    fireEvent.click(within(dlg).getByRole("button", { name: "Guidance & outlook" }));
    expect(await within(dlg).findByRole("article", { name: "Guidance & outlook" })).toBeTruthy();
    fireEvent.change(within(dlg).getByLabelText("Choose a question about the Q2 FY27 call"), { target: { value: "risks-raised" } });
    const none = await within(dlg).findByRole("article", { name: "Risks raised" });
    expect(none.textContent).toContain("The call did not cover this.");
    expect(within(dlg).queryAllByRole("button", { name: "Show the quote" })).toHaveLength(0);
    expect((within(dlg).getByRole("button", { name: "Margins & costs" }) as HTMLButtonElement).disabled).toBe(true);
    expect((within(dlg).getByRole("option", { name: "Margins & costs" }) as HTMLOptionElement).disabled).toBe(true);
  });

  it("offers only the quarters and years that have a call, and opening another call asks the server for it", async () => {
    const calls = serve(ok);
    mount();
    const dlg = await open();
    await within(dlg).findByRole("article", { name: "Strategy & moat" });
    const q = (n: number) => within(dlg).getByRole("button", { name: new RegExp(`^Q${n}$`) }) as HTMLButtonElement;
    expect([1, 2, 3, 4].map((n) => q(n).disabled)).toEqual([false, false, true, true]);          // FY27 has Q1 and Q2 only
    expect(Array.from((within(dlg).getByLabelText("Financial year") as HTMLSelectElement).options).map((o) => o.textContent)).toEqual(["FY27", "FY26"]);
    fireEvent.click(q(1));
    await waitFor(() => expect(dlg.textContent).toContain("HDFC Bank Ltd, Q1 FY27 earnings call"));
    expect(calls.some((u) => u.endsWith("/HDFCBANK/2027/1"))).toBe(true);
    fireEvent.change(within(dlg).getByLabelText("Financial year"), { target: { value: "2026" } });      // FY26 has only Q4: the picker lands on it
    await waitFor(() => expect(dlg.textContent).toContain("HDFC Bank Ltd, Q4 FY26 earnings call"));
    expect(calls.filter((u) => u.endsWith("/HDFCBANK/2027/2"))).toHaveLength(1);
  });

  it("keeps a history of the questions asked in this tab only", async () => {
    serve(ok);
    mount();
    const dlg = await open();
    await within(dlg).findByRole("article", { name: "Strategy & moat" });
    expect(within(dlg).queryByText("History")).toBeNull();
    fireEvent.click(within(dlg).getByRole("button", { name: "Guidance & outlook" }));
    await within(dlg).findByRole("article", { name: "Guidance & outlook" });
    expect(within(dlg).getByText("History")).toBeTruthy();
    expect(JSON.parse(sessionStorage.getItem("finlit.ec.history.HDFCBANK")!)).toEqual([{ fy: 2027, q: 2, qid: "guidance-outlook" }]);
    fireEvent.click(within(dlg).getByRole("button", { name: "Strategy & moat" }));
    fireEvent.click(within(dlg).getByRole("button", { name: "Q2 FY27 · Guidance & outlook" }));
    expect(await within(dlg).findByRole("article", { name: "Guidance & outlook" })).toBeTruthy();
    expect(localStorage.getItem("finlit.ec.history.HDFCBANK")).toBeNull();
  });

  it("closes on Escape and on the close button, and gives focus back", async () => {
    serve(ok);
    mount();
    const trigger = await screen.findByRole("button", { name: /Read the call summary/ });
    trigger.focus();
    await open();
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(document.activeElement).toBe(trigger);
    await open();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("keeps Tab inside the dialog", async () => {
    Object.defineProperty(HTMLElement.prototype, "offsetParent", { configurable: true, get() { return this.parentNode; } });      // jsdom has no layout: every element counts as visible
    serve(ok);
    mount();
    const dlg = await open();
    await within(dlg).findByRole("article", { name: "Strategy & moat" });
    const all = dlg.querySelectorAll<HTMLElement>("a[href], button:not([disabled]), select:not([disabled])");
    (all[all.length - 1]).focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(dlg.contains(document.activeElement)).toBe(true);
    expect(document.activeElement).toBe(all[0]);
    delete (HTMLElement.prototype as { offsetParent?: unknown }).offsetParent;
  });
});

describe("locked, limit and error states", () => {
  it("below Gold the dialog shows the labels but asks for no answers and shows none", async () => {
    const calls = serve(() => ({ body: { ...LIST, locked: true, usage: null } }));
    mount();
    expect(await screen.findByText(/The answers are part of the Gold plan/)).toBeTruthy();
    const dlg = await open(/See what is inside/);
    expect(dlg.textContent).toContain("Earnings-call summaries are part of the Gold plan");
    expect((within(dlg).getByRole("button", { name: "Strategy & moat" }) as HTMLButtonElement).disabled).toBe(true);
    expect(within(dlg).getByRole("link", { name: "Compare plans" }).getAttribute("href")).toBe("/plans");
    expect(calls.every((u) => !/\/\d{4}\/\d$/.test(u))).toBe(true);                       // the detail is never requested
    expect(dlg.textContent).not.toContain("aims to grow");
  });

  it("says when the month's calls are used up and that opened calls stay open", async () => {
    serve((u) => (/\/2027\/2$/.test(u) ? { status: 403, body: { detail: { status: "limit_reached", detail: "x", used: 5, limit: 5, plan: "gold" } } } : ok(u)));
    mount();
    const dlg = await open();
    expect((await within(dlg).findByRole("alert")).textContent).toContain("You have used your 5 calls for this month");
    expect(dlg.textContent).toContain("Calls you already opened stay open");
    expect(dlg.textContent).toContain("5 of 5 calls this month");
    expect(within(dlg).queryByRole("article")).toBeNull();
  });

  it("handles a call with no summary yet and a failing request with a retry", async () => {
    serve((u) => (/\/2027\/2$/.test(u) ? { status: 404, body: { detail: { status: "not_found" } } } : ok(u)));
    mount();
    const dlg = await open();
    expect(await within(dlg).findByText("No summary of this call yet")).toBeTruthy();
    cleanup();
    vi.restoreAllMocks();
    let down = true;
    serve((u) => (/\/2027\/2$/.test(u) && down ? { status: 500, body: {} } : ok(u)));
    mount();
    const d2 = await open();
    const alert = await within(d2).findByRole("alert", undefined, { timeout: 5000 });
    down = false;
    fireEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await within(d2).findByRole("article", { name: "Strategy & moat" })).toBeTruthy();
  });

  it("never uses advice words in anything it says itself", async () => {
    serve(ok);
    mount();
    const dlg = await open();
    await within(dlg).findByRole("article", { name: "Strategy & moat" });
    const own = (dlg.textContent || "").replace(DETAIL(LIST.calls[0]).questions.flatMap((a) => a.sentences.flatMap((s) => [s.text, s.quote])).join("|"), "");
    expect(own + (document.querySelector(".ec-card")?.textContent || "")).not.toMatch(/\b(buy|sell|hold|accumulate|target|we recommend)\b/i);
  });
});

describe("helpers", () => {
  it("formats days without a time zone shift and the usage line", () => {
    expect(dayText("2026-10-23")).toBe("23 Oct 2026"); expect(dayText("2026-01-05T00:00:00")).toBe("5 Jan 2026"); expect(dayText(null)).toBe("");
    expect(usageText({ used: 1, limit: 5 })).toBe("1 of 5 calls this month"); expect(usageText({ used: 9, limit: 5 })).toBe("5 of 5 calls this month"); expect(usageText({ used: 3, limit: null })).toBe("");
  });
  it("picks a year keeping the quarter when it exists", () => {
    const c = [row(2027, 2), row(2027, 1), row(2026, 4), row(2026, 2)];
    expect(yearsOf(c)).toEqual([2027, 2026]); expect(pickYear(c, 2026, 2)?.label).toBe("Q2 FY26"); expect(pickYear(c, 2026, 1)?.label).toBe("Q4 FY26"); expect(pickYear(c, 2025, 1)).toBeNull();
  });
  it("keeps eight distinct history entries, newest first, and survives a broken store", () => {
    const mem: Record<string, string> = {};
    const store = { getItem: (k: string) => mem[k] ?? null, setItem: (k: string, v: string) => { mem[k] = v; } };
    for (let i = 0; i < 10; i++) pushHistory("X", { fy: 2027, q: 1, qid: "q" + i }, store);
    pushHistory("X", { fy: 2027, q: 1, qid: "q5" }, store);
    const h = loadHistory("X", store);
    expect(h).toHaveLength(8); expect(h[0].qid).toBe("q5"); expect(new Set(h.map((x) => x.qid)).size).toBe(8);
    expect(loadHistory("X", { getItem: () => "{not json" })).toEqual([]);
    expect(() => pushHistory("X", { fy: 2027, q: 1, qid: "a" }, { getItem: () => null, setItem: () => { throw new Error("quota"); } })).not.toThrow();
  });
});
