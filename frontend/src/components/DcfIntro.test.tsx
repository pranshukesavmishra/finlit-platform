// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it } from "vitest";
import { DcfIntro } from "./DcfIntro";

afterEach(cleanup);
const BANNED = /\b(buy|buying|sell|hold|reduce|avoid|accumulate|target|best)\b/i;

describe("the DCF calculator introduction", () => {
  it("explains what a DCF is, five steps and six results, and is open at the start", () => {
    const { container } = render(<DcfIntro />);
    expect(container.querySelector("details")?.hasAttribute("open")).toBe(true);
    expect(screen.getByText("What is a DCF?")).toBeTruthy();
    const steps = within(container.querySelector("ol")!).getAllByRole("listitem");
    expect(steps.length).toBe(5);
    expect(steps[0].textContent).toMatch(/Choose a company/); expect(steps[4].textContent).toMatch(/Review the working/);
    expect(container.querySelectorAll(".dcf-get li").length).toBe(6);
  });
  it("describes a calculation and never advises: no advice words, and the required sentence is there", () => {
    const { container } = render(<DcfIntro />);
    expect(container.textContent).not.toMatch(BANNED);
    expect(container.textContent).toContain("Describes the company's financial health from its filings and prices; not a recommendation. Information only, not investment advice.");
  });
  it("the DCF page and its words no longer call a price a 'buy price'", () => {
    for (const f of ["../pages/Dcf.tsx", "../lib/dcf.ts"]) expect(readFileSync(new URL(f, import.meta.url), "utf8"), f).not.toMatch(/buy price/i);
  });
});
