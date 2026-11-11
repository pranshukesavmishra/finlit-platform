// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CoLogo } from "./CoLogo";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const quotes = { rows: [["HDFCBANK", 1500, 1.2, "2026-11-10", 70, "healthy", "/api/logos/abcd1234abcd1234.png"], ["TCS", 4000, -0.5, "2026-11-10", 80, "strong", null]] };
const stub = () => vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, status: 200, headers: new Headers(), json: async () => quotes }) as unknown as Response));
const mount = (ui: React.ReactNode) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);

describe("company logo", () => {
  it("shows the company's own logo once the shared list arrives, and its initials before that", async () => {
    stub();
    const { container } = mount(<CoLogo symbol="hdfcbank" name="HDFC Bank Ltd" size={24} />);
    expect(container.querySelector(".gs-logo-txt")).toBeTruthy();                      // initials first: no layout jump when the logo comes in
    await waitFor(() => expect(container.querySelector("img")?.getAttribute("src")).toMatch(/\/api\/logos\/abcd1234abcd1234\.png$/));
    expect(container.querySelector("img")?.getAttribute("alt")).toBe("");              // decorative: the name beside it says who it is
    expect(container.querySelector(".gs-logo")?.getAttribute("style")).toMatch(/width: 24px/);
  });
  it("keeps the initials tile for a company with no logo", async () => {
    stub();
    const { container } = mount(<CoLogo symbol="TCS" name="Tata Consultancy Services" />);
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(container.querySelector("img")).toBeNull(); expect(container.querySelector(".gs-logo-txt")?.textContent).toBe("TC");
  });
  it("draws the initials without a data provider at all (a table under test), and `inline` wraps it for a line of text", () => {
    const { container } = render(<CoLogo symbol="X" name="Xyz Ltd" inline />);
    expect(container.querySelector(".cl-in .gs-logo-txt")).toBeTruthy(); expect(screen.queryByRole("img")).toBeNull();
  });
});
