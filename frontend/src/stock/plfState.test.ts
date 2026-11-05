// The show/hide rules of the earnings alert. Founder, 5 Nov 2026: "every time I scroll from section 4 to 5 (or back) it must hide and the icon must appear,
// and every time I scroll back to its own section the popup must appear again, whatever the number of times."
import { describe, expect, it } from "vitest";
import { PLF_START, plfCardShown, plfEdgeShown, plfMode, plfReduce, type PlfEvent, type PlfState } from "./plfState";

const run = (evs: PlfEvent[], from: PlfState = PLF_START) => evs.reduce(plfReduce, from);
const inn: PlfEvent = { type: "scroll", away: false }, out: PlfEvent = { type: "scroll", away: true };

describe("alert state machine", () => {
  it("starts in place: the card shows, no icon", () => {
    expect(plfMode(PLF_START)).toBe("inplace");
    expect(plfCardShown("inplace")).toBe(true); expect(plfEdgeShown("inplace")).toBe(false);
  });
  it("hides with the icon when the reader leaves, and shows again when the reader returns", () => {
    expect(plfMode(run([out]))).toBe("away");
    expect(plfEdgeShown(plfMode(run([out])))).toBe(true); expect(plfCardShown(plfMode(run([out])))).toBe(false);
    expect(plfMode(run([out, inn]))).toBe("inplace");
  });
  it("alternates correctly over 50 up/down passes", () => {
    let s = PLF_START;
    for (let k = 0; k < 50; k++) {
      s = plfReduce(s, out); expect(plfMode(s)).toBe("away");
      s = plfReduce(s, inn); expect(plfMode(s)).toBe("inplace");
    }
  });
  it("the edge icon opens a floating card, and scrolling back to the section replaces it with the in-place card", () => {
    const s = run([out, { type: "open" }]);
    expect(plfMode(s)).toBe("opened"); expect(plfCardShown("opened")).toBe(true); expect(plfEdgeShown("opened")).toBe(false);
    const back = plfReduce(s, inn);
    expect(plfMode(back)).toBe("inplace"); expect(back.opened).toBe(false);
    expect(plfMode(plfReduce(back, out))).toBe("away");   // the next departure hides it again: nothing sticky
  });
  it("opening from the icon on every pass never blocks the next pass (the reported bug)", () => {
    let s = PLF_START;
    for (let k = 0; k < 30; k++) {
      s = run([out, { type: "open" }], s); expect(plfMode(s)).toBe("opened");
      s = plfReduce(s, inn); expect(plfMode(s)).toBe("inplace");
      s = plfReduce(s, out); expect(plfMode(s)).toBe("away");
      s = plfReduce(s, inn); expect(plfMode(s)).toBe("inplace");
    }
  });
  it("staying away while open keeps the floating card (many scroll readings in a row)", () => {
    const s = run([out, { type: "open" }, out, out, out]);
    expect(plfMode(s)).toBe("opened");
  });
  it("Esc, a click outside, or the x on the floating card close it back to the icon, and the icon opens it again", () => {
    let s = run([out, { type: "open" }, { type: "close" }]);
    expect(plfMode(s)).toBe("away"); expect(plfEdgeShown(plfMode(s))).toBe(true);
    s = plfReduce(s, { type: "open" }); expect(plfMode(s)).toBe("opened");
    expect(plfMode(run([{ type: "close" }, inn]))).toBe("inplace");   // a stray close while in place does nothing
  });
  it("open does nothing while the reader is in place", () => {
    expect(plfMode(run([{ type: "open" }]))).toBe("inplace");
    expect(run([{ type: "open" }]).opened).toBe(false);
  });
  it("the x on the in-place card dismisses it: no card and no icon, however much the reader scrolls", () => {
    let s = run([{ type: "dismiss" }]);
    expect(plfMode(s)).toBe("dismissed"); expect(plfCardShown("dismissed")).toBe(false); expect(plfEdgeShown("dismissed")).toBe(false);
    for (let k = 0; k < 10; k++) { s = plfReduce(plfReduce(s, out), inn); expect(plfMode(s)).toBe("dismissed"); }
    expect(plfMode(plfReduce(plfReduce(s, out), { type: "open" }))).toBe("dismissed");   // the icon is gone, so there is nothing to click
  });
  it("a different alert or company starts fresh", () => {
    const s = run([{ type: "dismiss" }, out, { type: "reset" }]);
    expect(plfMode(s)).toBe("away"); expect(plfEdgeShown(plfMode(s))).toBe(true);
    expect(plfMode(plfReduce(s, inn))).toBe("inplace");
  });
  it("Show details in the results bar brings back a dismissed alert, and opens it when the reader is away", () => {
    expect(plfMode(run([{ type: "dismiss" }, { type: "show" }]))).toBe("inplace");
    expect(plfMode(run([out, { type: "dismiss" }, { type: "show" }, { type: "open" }]))).toBe("opened");
  });
  it("a scroll reading that repeats the same answer changes nothing (same object, no re-render)", () => {
    const s = run([out, { type: "open" }]);
    expect(plfReduce(s, out)).toBe(s);
  });
  it("a long random walk always agrees with the position: in place iff the reader is on the section, unless dismissed", () => {
    let seed = 7; const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
    let s = PLF_START, dismissed = false;
    for (let k = 0; k < 2000; k++) {
      const r = rnd(), e: PlfEvent = r < .4 ? out : r < .75 ? inn : r < .88 ? { type: "open" } : r < .96 ? { type: "close" } : r < .98 ? { type: "dismiss" } : { type: "reset" };
      if (e.type === "dismiss" && !s.away) dismissed = true;
      s = plfReduce(s, e);
      if (e.type === "reset") dismissed = false;
      if (e.type === "dismiss") dismissed = true;
      expect(s.dismissed).toBe(dismissed);
      if (!s.dismissed && !s.away) expect(plfMode(s)).toBe("inplace");
      if (!s.dismissed && s.away) expect(["away", "opened"]).toContain(plfMode(s));
      if (!s.away) expect(s.opened).toBe(false);
    }
  });
});
