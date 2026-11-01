// @vitest-environment jsdom
import { useState } from "react";
import { MemoryRouter } from "react-router";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HeaderMenu, MobileNavigation } from "./SiteNavigation";
import { HEADER_MORE } from "../lib/nav";

afterEach(cleanup);
function Desktop() {
  const [open, setOpen] = useState<string | null>(null);
  return <MemoryRouter><HeaderMenu section={HEADER_MORE} open={open === "more"} setOpen={setOpen} path="/" /><button>Outside navigation</button></MemoryRouter>;
}
describe("header disclosure navigation", () => {
  it("opens explicitly and closes with Escape, returning focus to the trigger", () => {
    render(<Desktop />);
    const trigger = screen.getByRole("button", { name: "More" });
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    const link = screen.getByRole("link", { name: /About FinLit/ });
    link.focus();
    fireEvent.keyDown(link, { key: "Escape" });
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(trigger);
    expect(screen.queryByRole("link", { name: /About FinLit/ })).toBeNull();
  });
  it("closes on an outside pointer or when keyboard focus leaves", () => {
    render(<Desktop />);
    const trigger = screen.getByRole("button", { name: "More" });
    const outside = screen.getByRole("button", { name: "Outside navigation" });
    fireEvent.click(trigger);
    fireEvent.pointerDown(outside);
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(trigger);
    act(() => { trigger.focus(); outside.focus(); });
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
  });
  it("closes after selecting a destination", () => {
    render(<Desktop />);
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    fireEvent.click(screen.getByRole("link", { name: /About FinLit/ }));
    expect(screen.getByRole("button", { name: "More" }).getAttribute("aria-expanded")).toBe("false");
  });
});
describe("phone navigation", () => {
  it("keeps the complete catalogue reachable and closes even for a same-page destination", () => {
    const close = vi.fn();
    render(<MemoryRouter initialEntries={["/platform"]}><MobileNavigation signedIn onClose={close} /></MemoryRouter>);
    fireEvent.click(screen.getByText("Products", { selector: "summary" }));
    const catalogue = screen.getByRole("link", { name: "All products and tools" });
    expect(catalogue.getAttribute("href")).toBe("/platform");
    fireEvent.click(catalogue);
    expect(close).toHaveBeenCalledOnce();
    expect(screen.getByRole("link", { name: "Dashboard" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Services" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Plans" })).toBeTruthy();
  });
  it("offers sign-in and registration to visitors without a workspace link", () => {
    render(<MemoryRouter><MobileNavigation signedIn={false} onClose={() => {}} /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "Sign in" }).getAttribute("href")).toBe("/login");
    expect(screen.getByRole("link", { name: "Create free account" }).getAttribute("href")).toContain("mode=signup");
    expect(screen.queryByRole("link", { name: "Dashboard" })).toBeNull();
  });
});
