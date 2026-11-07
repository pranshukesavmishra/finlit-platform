// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { edgeOf, numberPads } from "./scrollHints";
import { lockBody, lockCount } from "./useSheet";

describe("sideways scroll hints", () => {
  it("says where more columns are", () => {
    expect(edgeOf({ scrollLeft: 0, scrollWidth: 300, clientWidth: 300 })).toBe("none");
    expect(edgeOf({ scrollLeft: 0, scrollWidth: 600, clientWidth: 300 })).toBe("end");
    expect(edgeOf({ scrollLeft: 150, scrollWidth: 600, clientWidth: 300 })).toBe("both");
    expect(edgeOf({ scrollLeft: 300, scrollWidth: 600, clientWidth: 300 })).toBe("start");
  });
  it("ignores a 1-2px rounding overflow", () => {
    expect(edgeOf({ scrollLeft: 0, scrollWidth: 302, clientWidth: 300 })).toBe("none");
  });
});

describe("number pads", () => {
  it("gives number boxes the right phone keyboard and keeps an explicit choice", () => {
    document.body.innerHTML = '<input type="number" id="a"><input type="number" step="1" min="0" id="b"><input type="number" inputmode="tel" id="c"><input id="d">';
    numberPads();
    expect(document.getElementById("a")!.getAttribute("inputmode")).toBe("decimal");
    expect(document.getElementById("b")!.getAttribute("inputmode")).toBe("numeric");
    expect(document.getElementById("c")!.getAttribute("inputmode")).toBe("tel");
    expect(document.getElementById("d")!.hasAttribute("inputmode")).toBe(false);
  });
});

describe("page lock behind sheets", () => {
  it("unlocks only when every open sheet has closed, and twice-closing is harmless", () => {
    document.body.style.overflow = "";
    const a = lockBody(), b = lockBody();
    expect(document.body.style.overflow).toBe("hidden");
    a(); a();
    expect(lockCount()).toBe(1);
    expect(document.body.style.overflow).toBe("hidden");
    b();
    expect(lockCount()).toBe(0);
    expect(document.body.style.overflow).toBe("");
  });
});
