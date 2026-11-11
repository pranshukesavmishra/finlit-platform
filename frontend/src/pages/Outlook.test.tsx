// @vitest-environment jsdom
// The outlook page: choosing "Set your own model" puts the sliders first (right under the model cards), then the charts; "Our model" shows no sliders.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
vi.mock("../lib/ui", () => ({ useUI: () => ({ has: () => true, upgrade: vi.fn(), toast: vi.fn() }), TIER: { gold: { n: "Gold" }, silver: { n: "Silver" } } }));
vi.mock("../lib/auth", () => ({ useAuth: () => ({ user: { id: 1 } }) }));
vi.mock("../lib/demo", () => ({ DEMO: false }));
vi.mock("../components/Gate", () => ({ Gate: ({ children }: { children: React.ReactNode }) => <>{children}</>, TierChip: () => null }));
vi.mock("../components/OutlookPicker", () => ({ OutlookPicker: () => <section aria-label="picker" /> }));
vi.mock("../components/PageHeader", () => ({ PageHeader: () => <header /> }));
vi.mock("../charts/OutlookChart", () => ({ OutlookChart: () => <div data-testid="chart" />, buildSeries: () => [] }));
vi.mock("../lib/outlook", async (orig) => ({ ...(await orig<typeof import("../lib/outlook")>()), useOutlook: () => ({ data: undefined, isLoading: true, isFetching: true, error: null }) }));
import { OutlookPage } from "./Outlook";

afterEach(cleanup);
const open = () => render(<QueryClientProvider client={new QueryClient()}><MemoryRouter initialEntries={["/outlook/RELIANCE"]}><Routes><Route path="/outlook/:symbol" element={<OutlookPage />} /></Routes></MemoryRouter></QueryClientProvider>);
const before = (a: Element, b: Element) => !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);

describe("outlook page, Set your own model", () => {
  it("shows no sliders with Our model", () => { open(); expect(screen.queryByRole("group", { name: /Weight of each input/ })).toBeNull(); expect(screen.queryByText(/Set your own model: assumptions/)).toBeNull(); });
  it("opens the sliders first: right after the model cards and before the charts and the detail tabs", () => {
    open();
    fireEvent.click(screen.getByRole("radio", { name: /Set your own model/ }));
    const assume = screen.getByRole("heading", { name: /Set your own model: assumptions/ }).closest("section")!;
    const cards = screen.getByRole("radiogroup", { name: /Estimation model/ });
    const charts = document.querySelector(".ol-charts")!, tabs = screen.getByRole("tablist", { name: /Details of the estimate/ });
    expect(before(cards, assume)).toBe(true); expect(before(assume, charts)).toBe(true); expect(before(assume, tabs)).toBe(true);
    expect(assume.querySelectorAll('input[type="range"]').length).toBeGreaterThan(5);
    fireEvent.click(screen.getByRole("radio", { name: "Revenue estimate" }));
    expect(assume.querySelectorAll('input[type="range"]').length).toBe(6);                    // revenue has six inputs, profit seven
  });
});
