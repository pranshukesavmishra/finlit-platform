// @vitest-environment jsdom
// "Raise a Query" in the banner and "Share feedback" on every page: both open one dialog tagged with the page, and send what the server expects.
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const st = vi.hoisted(() => ({ user: null as unknown, sent: [] as unknown[], fail: null as null | { status: number; body: unknown } }));
vi.mock("../lib/auth", () => ({ useAuth: () => ({ user: st.user, plan: "silver", ready: true, isAdmin: false }) }));
vi.mock("../lib/api", async (orig) => {
  const m = await orig<typeof import("../lib/api")>();
  return { ...m, apiSend: vi.fn(async (_method: string, _path: string, body: unknown) => {
    st.sent.push(body);
    if (st.fail) throw new m.ApiError(st.fail.status, st.fail.body as never);
    return { status: "received", id: 1 };
  }) };
});
import { PageFeedbackDock } from "./PageFeedback";
import { PageHeader } from "./PageHeader";
import { panel } from "../lib/pageFeedback";

const member = { id: "u1", email: "m@example.com", name: "M", role: "investor", plan: "silver", verified: true, mfa: false, mfaOk: false };
const open = (path = "/score-screener", withBanner = true) => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
    <MemoryRouter initialEntries={[path]}>
      <Routes><Route path="*" element={<>{withBanner && <PageHeader title="Basic score screener" description="Score every company" />}<PageFeedbackDock /></>} /></Routes>
    </MemoryRouter>
  </QueryClientProvider>);

beforeEach(() => { st.user = member; st.sent = []; st.fail = null; panel.set(null); });
afterEach(cleanup);

describe("Raise a Query and Share feedback", () => {
  it("every page banner has a Raise a Query button, and a Share feedback button is always on screen", () => {
    open();
    expect(screen.getByRole("button", { name: "Raise a Query" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Share feedback" })).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Raise a Query" }).length).toBe(1);   // the banner carries it, so the dock does not repeat it
  });
  it("a page without a banner gets Raise a Query in the dock instead, so no page is without one", async () => {
    open("/somewhere", false);
    await waitFor(() => expect(screen.getAllByRole("button", { name: /Raise a Query/ }).length).toBe(1));
    expect(screen.getByRole("button", { name: "Share feedback" })).toBeTruthy();
  });
  it("the query dialog says which page it is about, checks the text, and sends it tagged with the page", async () => {
    open("/stocks/RELIANCE?tab=x");
    fireEvent.click(screen.getByRole("button", { name: "Raise a Query" }));
    const dlg = screen.getByRole("dialog", { name: "Raise a query" });
    expect(within(dlg).getByText("Company report")).toBeTruthy();
    expect(within(dlg).getByText(/\/stocks\/RELIANCE/)).toBeTruthy();
    fireEvent.click(within(dlg).getByRole("button", { name: "Send query" }));
    expect(within(dlg).getByRole("alert").textContent).toMatch(/at least 10/);
    expect(st.sent.length).toBe(0);
    fireEvent.click(within(dlg).getByRole("radio", { name: "Something is wrong" }));
    fireEvent.change(within(dlg).getByRole("textbox"), { target: { value: "The P/E number on this page looks different from the filing." } });
    fireEvent.click(within(dlg).getByRole("button", { name: "Send query" }));
    await waitFor(() => expect(within(dlg).getByRole("status").textContent).toMatch(/Query sent/));
    expect(st.sent[0]).toMatchObject({ kind: "query", page: "/stocks/RELIANCE", pageName: "Company report", category: "issue", rating: null, message: "The P/E number on this page looks different from the filing." });
    expect((st.sent[0] as { context: Record<string, string> }).context).toMatchObject({ symbol: "RELIANCE", plan: "silver" });
    expect((st.sent[0] as { email?: string }).email).toBeUndefined();                // a member is reached through the account
  });
  it("feedback takes a star rating alone, and sends the rating, the type and the page", async () => {
    open("/dcf");
    fireEvent.click(screen.getByRole("button", { name: "Share feedback" }));
    const dlg = screen.getByRole("dialog", { name: "Share feedback" });
    fireEvent.click(within(dlg).getByRole("button", { name: "Send feedback" }));
    expect(within(dlg).getByRole("alert").textContent).toMatch(/rating or write/);
    fireEvent.click(within(dlg).getByRole("radio", { name: "4 of 5, Very good" }));
    fireEvent.click(within(dlg).getByRole("radio", { name: "Look and feel" }));
    fireEvent.click(within(dlg).getByRole("button", { name: "Send feedback" }));
    await waitFor(() => expect(within(dlg).getByRole("status").textContent).toMatch(/Thank you/));
    expect(st.sent[0]).toMatchObject({ kind: "feedback", page: "/dcf", pageName: "DCF valuation calculator", category: "ui_ux", rating: 4, message: "" });
  });
  it("a visitor must give an email, and it is sent with the message", async () => {
    st.user = null;
    open();
    fireEvent.click(screen.getByRole("button", { name: "Raise a Query" }));
    const dlg = screen.getByRole("dialog");
    fireEvent.change(within(dlg).getByLabelText(/Your question/), { target: { value: "How are the scores on this page worked out?" } });
    fireEvent.click(within(dlg).getByRole("button", { name: "Send query" }));
    expect(within(dlg).getByRole("alert").textContent).toMatch(/email/);
    fireEvent.change(within(dlg).getByLabelText(/Your email/), { target: { value: "visitor@example.com" } });
    fireEvent.click(within(dlg).getByRole("button", { name: "Send query" }));
    await waitFor(() => expect(within(dlg).getByRole("status")).toBeTruthy());
    expect(st.sent[0]).toMatchObject({ email: "visitor@example.com" });
  });
  it("a refusal from the server is shown and the text is kept", async () => {
    st.fail = { status: 429, body: { status: "rate_limited", detail: "Too many attempts. Please wait and try again." } };
    open();
    fireEvent.click(screen.getByRole("button", { name: "Raise a Query" }));
    const dlg = screen.getByRole("dialog");
    fireEvent.change(within(dlg).getByRole("textbox"), { target: { value: "A perfectly reasonable question about this page." } });
    fireEvent.click(within(dlg).getByRole("button", { name: "Send query" }));
    await waitFor(() => expect(within(dlg).getByRole("alert").textContent).toMatch(/Too many attempts/));
    expect((within(dlg).getByRole("textbox") as HTMLTextAreaElement).value).toMatch(/perfectly reasonable/);
  });
  it("Escape and Cancel close the dialog", () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: "Share feedback" }));
    expect(screen.getByRole("dialog")).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Raise a Query" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
  it("is not drawn on the admin pages", () => {
    open("/admin/feedback", false);
    expect(screen.queryByRole("button", { name: "Share feedback" })).toBeNull();
  });
});
