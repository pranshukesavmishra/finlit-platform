// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { CompanySearch } from "./CompanySearch";
const state = vi.hoisted(() => ({ failed: false, retry: vi.fn() }));
vi.mock("../lib/api", () => ({ useSearchIndex: () => ({ data: { rows: [["TCS", "Tata Consultancy Services", null, 1], ["TATAMOTORS", "Tata Motors", null, 1]] }, isError: state.failed, isLoading: false, refetch: state.retry }) }));
afterEach(() => { cleanup(); state.failed = false; state.retry.mockClear(); });
const open = () => render(<MemoryRouter><Routes><Route path="/" element={<CompanySearch />} /><Route path="/stocks/:symbol" element={<p>Company report opened</p>} /></Routes></MemoryRouter>);
describe("landing company search", () => {
  it("starts empty, supports keyboard choice and opens the chosen company", () => {
    open(); const input = screen.getByRole("combobox");
    expect((input as HTMLInputElement).value).toBe("");
    expect(screen.queryByRole("listbox")).toBeNull();
    fireEvent.change(input, { target: { value: "Tata" } });
    const options = screen.getAllByRole("option");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(options[1].getAttribute("aria-selected")).toBe("true");
    expect(input.getAttribute("aria-activedescendant")).toBe(options[1].id);
    fireEvent.submit(input.closest("form")!);
    expect(screen.getByText("Company report opened")).toBeTruthy();
  });
  it("Escape dismisses results and clicking a result navigates", () => {
    open(); const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "TCS" } });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(input.getAttribute("aria-expanded")).toBe("false");
    fireEvent.focus(input); fireEvent.click(screen.getByRole("option"));
    expect(screen.getByText("Company report opened")).toBeTruthy();
  });
  it("explains unavailable search and lets the visitor retry", () => {
    state.failed = true; open();
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "no match" } });
    expect(screen.getByRole("status").textContent).toContain("unavailable");
    fireEvent.click(screen.getByRole("button", { name: "Retry search" }));
    expect(state.retry).toHaveBeenCalledOnce();
  });
});
