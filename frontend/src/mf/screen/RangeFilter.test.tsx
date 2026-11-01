// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { RangeFilter, STEPS, barIn, fromPos, toPos, valueAt } from "./RangeFilter";
import { NUM_BY } from "../../lib/mfScreenDefs";

afterEach(cleanup);
const edges = [0, 1, 2, 5, 10];
describe("slider scale", () => {
  it("maps values to positions and back, bin by bin", () => {
    expect(toPos(edges, 0)).toBe(0); expect(toPos(edges, 10)).toBe(1); expect(toPos(edges, 2)).toBeCloseTo(0.5);
    expect(toPos(edges, 3.5)).toBeCloseTo(0.625); expect(fromPos(edges, 0.625)).toBeCloseTo(3.5);
    for (const v of [0.3, 1.7, 4, 9]) expect(fromPos(edges, toPos(edges, v))).toBeCloseTo(v);
  });
  it("an end position means no bound", () => {
    expect(valueAt(edges, 0, 1)).toBe(""); expect(valueAt(edges, STEPS, 1)).toBe(""); expect(valueAt(edges, 500, 1)).toBe("2");
  });
  it("a bar is selected when it overlaps the range", () => {
    expect(barIn(edges, 0, 1.5, null)).toBe(false); expect(barIn(edges, 1, 1.5, null)).toBe(true); expect(barIn(edges, 3, null, 5)).toBe(false);
  });
});

describe("RangeFilter", () => {
  const hist = { edges, bins: [4, 3, 2, 1], n: 10, m: 14 };
  it("says how many funds have the figure and offers the no-data toggle only with a range", () => {
    const onNodata = vi.fn();
    const { rerender } = render(<RangeFilter def={NUM_BY.ter} hist={hist} lo={null} hi={null} nodata={false} onRange={() => {}} onNodata={onNodata} />);
    expect(screen.getByText("10")).toBeTruthy(); expect(screen.getByText("14")).toBeTruthy();
    expect((screen.getByLabelText(/Include funds with no data/) as HTMLInputElement).disabled).toBe(true);
    rerender(<RangeFilter def={NUM_BY.ter} hist={hist} lo={1} hi={5} nodata={false} onRange={() => {}} onNodata={onNodata} />);
    expect(screen.getByText(/4 without it are left out/)).toBeTruthy();
    fireEvent.click(screen.getByLabelText(/Include funds with no data/));
    expect(onNodata).toHaveBeenCalledWith(true);
  });
  it("typed boxes commit on Enter and presets set both ends", () => {
    const onRange = vi.fn();
    render(<RangeFilter def={NUM_BY.ter} hist={hist} lo={null} hi={null} nodata={false} onRange={onRange} onNodata={() => {}} />);
    const max = screen.getByLabelText("Expense ratio (TER), maximum");
    fireEvent.change(max, { target: { value: "1.5" } }); fireEvent.keyDown(max, { key: "Enter" });
    expect(onRange).toHaveBeenLastCalledWith("", "1.5");
    fireEvent.click(screen.getByText("0.5 to 1%"));
    expect(onRange).toHaveBeenLastCalledWith("0.5", "1");
  });
  it("without server data it says so instead of drawing a made-up histogram", () => {
    render(<RangeFilter def={NUM_BY.ter} lo={null} hi={null} nodata={false} onRange={() => {}} onNodata={() => {}} />);
    expect(screen.getByText(/not available yet/)).toBeTruthy();
  });
});
