import { describe, expect, it } from "vitest";
import { FIB_LEVELS, distToSegment, fibLines, hit, sanitize, thin, topHit, type Shape } from "./drawings";

const W = 400, H = 200;
describe("drawing geometry", () => {
  it("measures the distance to a segment, including past its ends", () => {
    expect(distToSegment(5, 5, 0, 0, 10, 0)).toBe(5); expect(distToSegment(15, 0, 0, 0, 10, 0)).toBe(5); expect(distToSegment(3, 4, 0, 0, 0, 0)).toBe(5);
  });
  it("puts the Fibonacci levels between the two heights", () => {
    const l = fibLines([0.1, 0.8], [0.5, 0.2]);
    expect(l).toHaveLength(FIB_LEVELS.length); expect(l[0].y).toBeCloseTo(0.8, 12); expect(l[l.length - 1].y).toBeCloseTo(0.2, 12); expect(l.find((x) => x.level === 0.5)!.y).toBeCloseTo(0.5, 12);
  });
  it("thins a freehand stroke but keeps both ends", () => {
    const pts = Array.from({ length: 200 }, (_, i) => [i / 2000, 0.5] as [number, number]);       // 0.2 px apart at 400 wide
    const t = thin(pts, W, H); expect(t.length).toBeLessThan(pts.length / 4); expect(t[0]).toEqual(pts[0]); expect(t[t.length - 1]).toEqual(pts[pts.length - 1]);
  });
  const line: Shape = { id: "a", c: "red", w: 3, k: "line", a: [0.1, 0.1], b: [0.9, 0.9] };
  const box: Shape = { id: "b", c: "blue", w: 3, k: "rect", a: [0.2, 0.2], b: [0.4, 0.4] };
  it("finds what a click lands on, topmost first", () => {
    expect(hit(line, 200, 100, W, H)).toBe(true); expect(hit(line, 20, 180, W, H)).toBe(false);
    expect(hit({ id: "h", c: "red", w: 3, k: "hline", a: [0, 0.5] }, 10, 102, W, H)).toBe(true); expect(hit({ id: "v", c: "red", w: 3, k: "vline", a: [0.5, 0] }, 250, 10, W, H)).toBe(false);
    expect(hit({ id: "e", c: "red", w: 3, k: "ellipse", a: [0.2, 0.2], b: [0.6, 0.8] }, 160, 100, W, H)).toBe(true); expect(hit({ id: "e", c: "red", w: 3, k: "ellipse", a: [0.2, 0.2], b: [0.6, 0.8] }, 5, 5, W, H)).toBe(false);
    expect(topHit([line, box], 120, 60, W, H)?.id).toBe("b"); expect(topHit([line, box], 390, 10, W, H)).toBeNull();
  });
});

describe("saved drawings", () => {
  it("keeps good shapes and drops anything malformed or unexpected", () => {
    const out = sanitize([
      { id: "1", k: "line", c: "green", w: 2, a: [0.1, 0.2], b: [2, -1] },                       // out-of-range points are clamped
      { id: "2", k: "pen", c: "red", w: 3, pts: [[0.1, 0.1], ["x", 1], [0.2, 0.2]] },            // the bad point is dropped
      { id: "3", k: "text", c: "javascript:alert(1)", w: 3, a: [0.5, 0.5], t: "  note  " },     // an unknown colour falls back to red
      { id: "4", k: "text", c: "red", w: 3, a: [0.5, 0.5], t: "   " },                           // empty text
      { id: "5", k: "script", a: [0, 0] }, null, 7, "x", { k: "hline", a: [0.1] },
    ]);
    expect(out.map((s) => s.id)).toEqual(["1", "2", "3"]);
    expect((out[0] as { b: number[] }).b).toEqual([1, 0]); expect((out[1] as { pts: number[][] }).pts).toHaveLength(2); expect(out[2].c).toBe("red");
    expect(sanitize("nope")).toEqual([]); expect(sanitize(Array.from({ length: 500 }, (_, i) => ({ id: String(i), k: "hline", c: "red", w: 2, a: [0, 0.5] })))).toHaveLength(200);
  });
});
