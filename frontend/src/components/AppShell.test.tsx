// @vitest-environment jsdom
// The left rail: every group is a button that opens a labelled region, carries a quiet icon (no per-group colour), and the current page's group is open.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "./AppShell";

vi.mock("../lib/auth", () => ({ useAuth: () => ({ user: { email: "a@b.c" }, isAdmin: false }) }));
vi.mock("../lib/ui", async (orig) => ({ ...(await orig<typeof import("../lib/ui")>()), useUI: () => ({ plan: "gold" }) }));
vi.mock("../lib/screens", () => ({ useSavedScreens: () => [] }));
vi.mock("../lib/watchlist", () => ({ useWatchlist: () => ({ lists: [] }) }));
vi.mock("../lib/portfolio", () => ({ usePortfolio: () => ({ holdings: [] }) }));
vi.mock("../lib/alerts", () => ({ useAlerts: () => ({ alerts: [] }), useNotices: () => ({ unread: 0 }) }));

afterEach(() => { cleanup(); localStorage.clear(); });
const show = (path: string) => render(<MemoryRouter initialEntries={[path]}><Routes><Route element={<AppShell />}><Route path="*" element={<p>page</p>} /></Route></Routes></MemoryRouter>);

describe("AppShell rail", () => {
  it("keeps page questions inside the content column and leaves the global footer outside the rail", () => {
    const { container } = show("/premium/fundamentals");
    expect(container.querySelectorAll("#faq")).toHaveLength(1);
    expect(container.querySelector(".shell-main > #faq")).toBeTruthy();
    expect(container.querySelector(".shell .site-footer")).toBeNull();
  });
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
  it("gives each group an icon and no colour of its own, and opens the group of the current page", () => {
    const { container } = show("/screener");
    for (const g of container.querySelectorAll<HTMLElement>(".side-g")) {
      const name = g.querySelector(".side-gname")!.textContent!;
      expect(g.querySelector(".side-gbd svg"), name).toBeTruthy();
      expect(g.getAttribute("style"), name).toBeNull();
    }
    expect(screen.getByRole("button", { name: /Find stocks/ }).getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("button", { name: /Charts/ }).getAttribute("aria-expanded")).toBe("false");
  });
  it("toggles a group by click and remembers it", () => {
    show("/screener");
    const b = screen.getByRole("button", { name: /Charts/ });
    fireEvent.click(b);
    expect(b.getAttribute("aria-expanded")).toBe("true");
    expect(JSON.parse(localStorage.getItem("finlit:ui:side-groups")!).data["Charts"]).toBe(true);
  });
  it("keeps the Gold tag on gold tools and the collapse button", () => {
    show("/screener");
    expect(screen.getAllByLabelText("Gold plan").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Collapse the side menu" })).toBeTruthy();
  });
  it("filters the pages from the search box, opens the matching groups and says when nothing matches", () => {
    const { container } = show("/screener");
    const box = screen.getByRole("searchbox", { name: "Find a page" });
    fireEvent.change(box, { target: { value: "glossary" } });
    expect(container.querySelectorAll(".side-i").length).toBeGreaterThan(0);
    expect([...container.querySelectorAll(".side-i")].every((a) => /glossary/i.test(a.textContent!))).toBe(true);
    expect(screen.getByRole("button", { name: /Learn/ }).getAttribute("aria-expanded")).toBe("true");
    fireEvent.change(box, { target: { value: "zzzz-nothing" } });
    expect(screen.getByRole("status").textContent).toMatch(/No page matches/);
    fireEvent.click(screen.getByRole("button", { name: "Clear the search" }));
    expect(container.querySelectorAll("button.side-gb").length).toBeGreaterThanOrEqual(10);
  });
  it("moves focus with the arrow keys and Ctrl+/ focuses the search box", () => {
    const { container } = show("/screener");
    const heads = [...container.querySelectorAll<HTMLButtonElement>("button.side-gb")];
    heads[0].focus();
    fireEvent.keyDown(heads[0], { key: "ArrowUp" });
    expect(document.activeElement).toBe(screen.getByRole("searchbox"));
    fireEvent.keyDown(screen.getByRole("searchbox"), { key: "ArrowDown" });
    expect(document.activeElement).toBe(heads[0]);
    fireEvent.keyDown(window, { key: "/", ctrlKey: true });
    return new Promise<void>((done) => requestAnimationFrame(() => { expect(document.activeElement).toBe(screen.getByRole("searchbox")); done(); }));
  });
});
