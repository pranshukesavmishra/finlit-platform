// @vitest-environment jsdom
// Latest results page: the enlarge (zoom) arrow at the top right of the results panel (task #9).
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { QResp } from "../lib/qresults";

const st = vi.hoisted(() => ({ resp: null as unknown }));
vi.mock("../lib/qresults", async (orig) => ({
  ...(await orig<typeof import("../lib/qresults")>()),
  useQuarterResults: () => ({ data: st.resp, error: null, isError: false, isLoading: false, isFetching: false }),
}));
vi.mock("../lib/ui", () => ({ useUI: () => ({ plan: "silver", upgrade: vi.fn(), toast: vi.fn() }) }));
vi.mock("../lib/auth", () => ({ useAuth: () => ({ user: null }) }));
vi.mock("../lib/title", () => ({ useDocTitle: () => undefined }));
vi.mock("../components/ChartHelp", () => ({ ChartHelp: () => null }));
import { QuarterResultsPage } from "./QuarterResults";

const summary = { companies: 10, declared: 10, due: 0, awaiting: 0, withNumbers: 8, flagged: 0, medianRevenueYoY: 1, medianProfitYoY: 1, profitUpShare: 50, marginUpShare: 50, nRevenue: 8, nProfit: 8, nMargin: 8 };
const resp = (): QResp => ({
  plan: "silver", locked: false, today: "2026-10-27", quarter: { key: "2026-09", label: "Jul to Sep 2026", fiscal: "Q2 FY27", periodEnd: "2026-09-30", from: "2026-10-01", to: "2026-12-31" }, quarters: [],
  total: 5, offset: 0, limit: 50, summary, totals: summary, rows: [], days: [], facets: { sectors: [], indices: [] },
  distribution: { total: 5, sectors: [{ name: "IT", n: 3 }], caps: [{ name: "Large", n: 5 }] },
});

beforeEach(() => { st.resp = resp(); document.body.style.overflow = ""; vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} }); });
afterEach(cleanup);
const show = () => render(<MemoryRouter initialEntries={["/results/quarter"]}><Routes><Route path="/results/quarter" element={<QuarterResultsPage />} /></Routes></MemoryRouter>);
const arrow = () => screen.getByRole("button", { name: /Enlarge the results table|Back to the page/ });
const panel = () => document.querySelector("section.qr-card") as HTMLElement;

describe("results panel enlarge arrow", () => {
  it("is in the panel header, next to the unit line, and starts closed", () => {
    show();
    expect(panel().querySelector(".card-h .qr-zoom")).toBe(arrow());
    expect(arrow().getAttribute("aria-pressed")).toBe("false");
    expect(panel().classList.contains("qr-zoomed")).toBe(false);
    expect(document.querySelector(".qr-backdrop")).toBeNull();
  });

  it("opens the panel big over the page and holds the page still", () => {
    show();
    fireEvent.click(arrow());
    expect(panel().classList.contains("qr-zoomed")).toBe(true);
    expect(arrow().getAttribute("aria-pressed")).toBe("true");
    expect(arrow().getAttribute("aria-label")).toBe("Back to the page");
    expect(document.querySelector(".qr-backdrop")).toBeTruthy();
    expect(document.body.style.overflow).toBe("hidden");
  });

  it("closes with the same arrow, with Esc and with a click outside, and lets the page scroll again", () => {
    show();
    fireEvent.click(arrow()); fireEvent.click(arrow());
    expect(panel().classList.contains("qr-zoomed")).toBe(false);
    expect(document.body.style.overflow).toBe("");

    fireEvent.click(arrow()); fireEvent.keyDown(window, { key: "Escape" });
    expect(panel().classList.contains("qr-zoomed")).toBe(false);
    expect(document.body.style.overflow).toBe("");

    fireEvent.click(arrow()); fireEvent.click(document.querySelector(".qr-backdrop") as HTMLElement);
    expect(panel().classList.contains("qr-zoomed")).toBe(false);
    expect(document.querySelector(".qr-backdrop")).toBeNull();
    expect(document.body.style.overflow).toBe("");
  });

  it("gives the page back its scrolling if the page is left while enlarged", () => {
    const { unmount } = show();
    fireEvent.click(arrow());
    expect(document.body.style.overflow).toBe("hidden");
    unmount();
    expect(document.body.style.overflow).toBe("");
  });
});
