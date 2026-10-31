// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
afterEach(cleanup);
import { ChartInference } from "./ChartInference";
import { chartInference } from "../lib/chartInference";

const inf = (o = {}) => chartInference({ kind: "cross", n: 2259, r: -0.01, p: 0.803, rho: -0.16, xName: "P/E ratio", yName: "ROCE (%)", left: 3554, total: 5813, leftReason: "no ROCE on file", ...o });

describe("ChartInference", () => {
  it("renders headline, lines, how-to-read and the closing line as a polite note", () => {
    render(<ChartInference inference={inf()} />);
    const note = screen.getByRole("note");
    expect(note.getAttribute("aria-live")).toBe("polite");
    expect(note.textContent).toContain("Negligible relationship");
    expect(note.textContent).toContain("not distinguishable from zero");
    expect(note.textContent).toContain("3,554 are left out");
    expect(screen.getByText("How to read this")).toBeTruthy();
    expect(note.textContent).toContain("Information only, not investment advice.");
  });
  it("tooltip states the bands", () => {
    render(<ChartInference inference={inf()} />);
    expect(screen.getByRole("button", { name: /0\.7 or more very strong/ })).toBeTruthy();
  });
  it("shows a skeleton while loading", () => {
    render(<ChartInference inference={null} />);
    expect(screen.getByTestId("inference-skeleton").getAttribute("aria-busy")).toBe("true");
    expect(screen.queryByRole("note")).toBeNull();
  });
  it("degrades to a plain sentence when there are no statistics", () => {
    render(<ChartInference inference={inf({ n: 0 })} />);
    expect(screen.getByRole("note").textContent).toContain("Not enough points to say anything.");
  });
  it("updates when the numbers change", () => {
    const { rerender } = render(<ChartInference inference={inf()} />);
    rerender(<ChartInference inference={inf({ r: 0.62, p: 1e-8 })} />);
    expect(screen.getByRole("note").textContent).toContain("strong positive relationship");
  });
});
