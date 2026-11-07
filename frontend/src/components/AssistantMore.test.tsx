// @vitest-environment jsdom
// The company page assistant: the five quick chips stay, and "More questions" opens the founder's 40 questions in 12 groups.
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";
import { Assistant, OPEN_AI } from "./Assistant";
import { bankGroups, STARTERS } from "../lib/questionBank";

const ask = vi.fn(async (q: string, _h?: unknown) => ({ response: "answer to " + q }));
vi.mock("../lib/siteApi", () => ({ askAssistant: (q: string, h: unknown) => ask(q, h) }));
vi.mock("./Enquiry", () => ({ useEnquiry: () => () => {} }));
beforeAll(() => { Element.prototype.scrollIntoView = () => {}; });
afterEach(() => { cleanup(); ask.mockClear(); });

const open = (path = "/stocks/reliance", sector?: string) => {
  const r = render(<MemoryRouter initialEntries={[path]}><Assistant sector={sector} /></MemoryRouter>);
  act(() => { dispatchEvent(new Event(OPEN_AI)); });   // the "Ask FinLit AI" button in the header bar fires this
  return r;
};

describe("bankGroups", () => {
  it("has the 12 groups with 2,7,5,3,4,5,4,5,2,1,1,1 questions (Q21 only for a lender) and the symbol filled in", () => {
    expect(bankGroups("/stocks/reliance").map((g) => g.items.length)).toEqual([2, 7, 5, 3, 3, 5, 4, 5, 2, 1, 1, 1]);
    expect(bankGroups("/stocks/hdfcbank", { lender: true }).map((g) => g.items.length)).toEqual([2, 7, 5, 3, 4, 5, 4, 5, 2, 1, 1, 1]);
    const all = bankGroups("/stocks/reliance").flatMap((g) => g.items);
    expect(all[0].text).toBe("Which sector, industry and sub-industry does RELIANCE belong to, and which cap bucket is it in?");
    expect(all.some((q) => q.text.includes("{"))).toBe(false);
    expect(bankGroups("/about")).toEqual([]);
  });
});

describe("Assistant more questions", () => {
  it("keeps the quick chips and offers a collapsed More questions control", () => {
    open();
    expect(screen.getByRole("button", { name: /What is RELIANCE's YoY and QoQ revenue growth/ })).toBeTruthy();
    const more = screen.getByRole("button", { name: /More questions/ });
    expect(more.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("Profit & Loss")).toBeNull();
  });
  it("opens the 12 groups; a group opens its questions; a tap sends the question with the company in it", async () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: /More questions/ }));
    const list = screen.getByRole("group", { name: /More questions about this company/ });
    expect(within(list).getAllByRole("button")).toHaveLength(12);
    const head = within(list).getByRole("button", { name: /Profit & Loss/ });
    expect(head.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(head);
    expect(head.getAttribute("aria-expanded")).toBe("true");
    expect(document.getElementById(head.getAttribute("aria-controls")!)!.querySelectorAll("button")).toHaveLength(7);
    fireEvent.click(screen.getByRole("button", { name: "What are RELIANCE's 3-year and 5-year profit CAGRs?" }));
    expect(ask).toHaveBeenCalledWith("What are RELIANCE's 3-year and 5-year profit CAGRs?", expect.anything());
    expect(await screen.findByText(/answer to What are RELIANCE's 3-year/)).toBeTruthy();
  });
  it("shows the banks question only when the page knows the company is a lender", () => {
    const { unmount } = open();
    fireEvent.click(screen.getByRole("button", { name: /More questions/ }));
    fireEvent.click(screen.getByRole("button", { name: /Ratios/ }));
    expect(screen.queryByText(/NIM, GNPA, NNPA and CASA/)).toBeNull();
    unmount();
    open("/stocks/hdfcbank", "Banks");
    fireEvent.click(screen.getByRole("button", { name: /More questions/ }));
    fireEvent.click(screen.getByRole("button", { name: /Ratios/ }));
    expect(screen.getByText(/NIM, GNPA, NNPA and CASA/)).toBeTruthy();
  });
  it("puts the two-company question in the input with XYZ selected instead of sending it", () => {
    open();
    fireEvent.click(screen.getByRole("button", { name: /More questions/ }));
    fireEvent.click(screen.getByRole("button", { name: /^Compare/ }));
    fireEvent.click(screen.getByRole("button", { name: /compare with XYZ/ }));
    const input = screen.getByLabelText("Your question") as HTMLInputElement;
    expect(ask).not.toHaveBeenCalled();
    expect(input.value).toBe("How does RELIANCE compare with XYZ on growth, margins, returns and valuation?");
    expect(input.value.slice(input.selectionStart!, input.selectionEnd!)).toBe("XYZ");
    expect(document.activeElement).toBe(input);
  });
  it("is not offered away from a company page", () => {
    open("/about");
    expect(screen.queryByRole("button", { name: /More questions/ })).toBeNull();
  });
});

describe("Assistant starter questions", () => {
  it("offers starter questions on a page with no company list and no FAQ, and a tap answers at once without calling the model", async () => {
    open("/nowhere-in-particular");
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "What is the difference between a mutual fund and an ETF?" })); });
    expect(ask).not.toHaveBeenCalled();
    expect(screen.getByText(/ETF trades on the stock exchange/)).toBeTruthy();
  });
  it("starter questions and answers never use advice wording", () => {
    const { container } = open("/nowhere-in-particular");
    expect(container.textContent).not.toMatch(/\b(buy|sell|hold|reduce|avoid|accumulate|target|best|multibagger|top pick)\b/i);
    for (const x of STARTERS) expect(x.a).not.toMatch(/\b(buy|sell|hold|reduce|avoid|accumulate|target|best|multibagger|top pick)\b/i);
  });
});
