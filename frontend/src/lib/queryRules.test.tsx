// @vitest-environment jsdom
// The "Rules for writing a query" guide: rule lookup for error messages, the main one-click fix, the remembered open state and the panel itself.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { QueryRules } from "../components/QueryRules";
import { RULES, RULES_KEY, keepRulesOpen, onlyFix, readRulesOpen, ruleFor } from "./queryRules";
import { applyFix, type Problem } from "./query";

const P = (o: Partial<Problem>): Problem => ({ code: "x", severity: "error", message: "m", start: 0, end: 0, line: 1, col: 1, text: "", fixes: [], ...o });

describe("error help", () => {
  it("has a rule and a fix for every code the guide lists, and the examples change from broken to working", () => {
    for (const [code, e] of Object.entries(RULES.errors)) {
      expect(ruleFor(P({ code }))).toEqual(e);
      expect(e.rule.length).toBeGreaterThan(10);
      expect(e.fix.length).toBeGreaterThan(5);
      if (e.bad) expect(e.good).toBeTruthy();
    }
  });
  it("gives NOT and sector their own rule when the parser reports them as an unknown ratio", () => {
    expect(ruleFor(P({ code: "unknown_metric", text: "NOT P/E" }))?.rule).toMatch(/NOT is not part of the language/);
    expect(ruleFor(P({ code: "unknown_metric", text: "Sector" }))?.rule).toMatch(/Sector, industry/);
    expect(ruleFor(P({ code: "unknown_metric", text: "Return on equty" }))).toEqual(RULES.errors.unknown_metric);
    expect(ruleFor(P({ code: "unknown_metric", text: "nothing" }))).toEqual(RULES.errors.unknown_metric);
  });
  it("returns null for a code it does not know", () => { expect(ruleFor(P({ code: "brand_new" }))).toBeNull(); });
  it("offers a main fix only when the repair is unambiguous", () => {
    const f1 = { label: "Use Return on equity", start: 0, end: 4, text: "Return on equity" };
    expect(onlyFix(P({ fixes: [f1] }))).toBe(f1);
    expect(onlyFix(P({ fixes: [f1, { ...f1, label: "Use Return on assets" }] }))).toBeNull();
    expect(onlyFix(P({ fixes: [] }))).toBeNull();
    expect(applyFix("rooe > 15", f1).text).toBe("Return on equity > 15");
  });
});

describe("remembering the panel", () => {
  afterEach(() => { cleanup(); localStorage.clear(); vi.restoreAllMocks(); });
  it("is open on the first visit and stays as it was left", () => {
    expect(readRulesOpen()).toBe(true);
    keepRulesOpen(false);
    expect(localStorage.getItem(RULES_KEY)).toBe("closed");
    expect(readRulesOpen()).toBe(false);
    keepRulesOpen(true);
    expect(readRulesOpen()).toBe(true);
  });
  it("still works when storage throws", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(readRulesOpen()).toBe(true);
    expect(() => keepRulesOpen(false)).not.toThrow();
  });
});

describe("the rules panel", () => {
  it("shows the golden rules, the syntax table, do and don't, and inserts an example with one click", () => {
    const onInsert = vi.fn(), onClose = vi.fn();
    render(<MemoryRouter><QueryRules onInsert={onInsert} onClose={onClose} /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Rules for writing a query" })).toBeTruthy();
    expect(screen.getAllByRole("listitem").length).toBeGreaterThan(RULES.golden.length + RULES.examples.length);
    expect(screen.getByRole("region", { name: "Syntax table" })).toBeTruthy();
    expect(RULES.golden.length).toBeGreaterThanOrEqual(6);
    expect(RULES.golden.length).toBeLessThanOrEqual(8);
    const buttons = screen.getAllByRole("button", { name: /^Put “/ });
    expect(buttons).toHaveLength(10);
    fireEvent.click(buttons[2]);
    expect(onInsert).toHaveBeenCalledWith(RULES.examples[2].query);
    fireEvent.click(screen.getByRole("button", { name: "Hide the rules" }));
    expect(onClose).toHaveBeenCalled();
    expect((screen.getByRole("link", { name: /questions for this page/ }) as HTMLAnchorElement).getAttribute("href")).toBe("/faq#faq-query-builder-1");
  });
});
