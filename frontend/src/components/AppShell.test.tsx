// @vitest-environment jsdom
// The left rail: every group is a button that opens a labelled region, carries its badge icon and colour token, and the current page's group is open.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "./AppShell";
import { SIDE_BADGES } from "../lib/sideGroups";

vi.mock("../lib/auth", () => ({ useAuth: () => ({ user: { email: "a@b.c" }, isAdmin: false }) }));
vi.mock("../lib/ui", async (orig) => ({ ...(await orig<typeof import("../lib/ui")>()), useUI: () => ({ plan: "gold" }) }));
vi.mock("../lib/screens", () => ({ useSavedScreens: () => [] }));
vi.mock("../lib/watchlist", () => ({ useWatchlist: () => ({ lists: [] }) }));
vi.mock("../lib/portfolio", () => ({ usePortfolio: () => ({ holdings: [] }) }));
vi.mock("../lib/alerts", () => ({ useAlerts: () => ({ alerts: [] }), useNotices: () => ({ unread: 0 }) }));

afterEach(() => { cleanup(); localStorage.clear(); });
const show = (path: string) => render(<MemoryRouter initialEntries={[path]}><Routes><Route element={<AppShell />}><Route path="*" element={<p>page</p>} /></Route></Routes></MemoryRouter>);

describe("AppShell rail", () => {
  it("renders every group as a button with aria-expanded, controlling a labelled region", () => {
    const { container } = show("/screener");
    const heads = [...container.querySelectorAll<HTMLButtonElement>("button.side-gb")];
    expect(heads.length).toBeGreaterThanOrEqual(10);
    for (const h of heads) {
      expect(["true", "false"]).toContain(h.getAttribute("aria-expanded"));
      const region = container.querySelector("#" + h.getAttribute("aria-controls"));
      expect(region?.getAttribute("role")).toBe("region");
      expect(region?.getAttribute("aria-label")).toBe(h.querySelector(".side-gname")?.textContent);
    }
  });
  it("gives each group a badge icon and a colour token, and opens the group of the current page", () => {
    const { container } = show("/screener");
    for (const g of container.querySelectorAll<HTMLElement>(".side-g")) {
      const name = g.querySelector(".side-gname")!.textContent!;
      expect(g.querySelector(".side-gbd svg"), name).toBeTruthy();
      expect(g.style.getPropertyValue("--gt"), name).toBe(`var(${SIDE_BADGES[name].tone})`);
    }
    expect(screen.getByRole("button", { name: /Find stocks/ }).getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("button", { name: /Charts/ }).getAttribute("aria-expanded")).toBe("false");
  });
  it("toggles a group by click and remembers it", () => {
    show("/screener");
    const b = screen.getByRole("button", { name: /Charts/ });
    fireEvent.click(b);
    expect(b.getAttribute("aria-expanded")).toBe("true");
    expect(JSON.parse(localStorage.getItem("finlit-side-groups")!)["Charts"]).toBe(true);
  });
  it("keeps the Gold tag on gold tools and the collapse button", () => {
    show("/screener");
    expect(screen.getAllByLabelText("Gold plan").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Collapse the side menu" })).toBeTruthy();
  });
});
