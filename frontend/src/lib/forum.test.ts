import { describe, expect, it } from "vitest";
import { ago, draftProblem, linkify, pageWindow, validHandle } from "./forum";

describe("linkify", () => {
  it("makes only http(s) links and keeps everything else as text", () => {
    const t = linkify("see https://www.bseindia.com/x.pdf, and javascript:alert(1) <img src=x onerror=alert(1)>");
    expect(t.filter((x) => x.t === "link")).toEqual([{ t: "link", href: "https://www.bseindia.com/x.pdf", label: "bseindia.com/…" }]);
    expect(t.map((x) => (x.t === "text" ? x.v : "")).join("")).toContain("<img src=x onerror=alert(1)>");
  });
  it("refuses credentials in links and trims trailing punctuation", () => {
    expect(linkify("https://a:b@evil.example/x").some((x) => x.t === "link")).toBe(false);
    expect(linkify("(https://a.example/x).")[1]).toMatchObject({ href: "https://a.example/x" });
  });
});
describe("draftProblem", () => {
  it("checks lengths and link count", () => {
    expect(draftProblem("thread", "short", "x".repeat(30))).toMatch(/title/);
    expect(draftProblem("thread", "A fine title", "x".repeat(30))).toBe("");
    expect(draftProblem("reply", "", "x")).toMatch(/Write/);
    expect(draftProblem("reply", "", "https://a.example https://b.example https://c.example")).toMatch(/links/);
  });
});
describe("misc", () => {
  it("handles", () => { expect(validHandle("asha_k")).toBe(true); expect(validHandle("1abc")).toBe(false); });
  it("pageWindow", () => { expect(pageWindow(1, 3)).toEqual([1, 2, 3]); expect(pageWindow(10, 20)).toEqual([1, "…", 8, 9, 10, 11, 12, "…", 20]); });
  it("ago", () => { const n = Date.now(); expect(ago(new Date(n - 5000).toISOString(), n)).toBe("just now"); expect(ago(new Date(n - 7200_000).toISOString(), n)).toBe("2 h ago"); });
});
