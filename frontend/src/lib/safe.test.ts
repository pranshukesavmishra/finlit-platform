import { describe, expect, it } from "vitest";
import { safeNext } from "./safe";

describe("safeNext", () => {
  it("keeps same-site paths", () => { expect(safeNext("/dashboard")).toBe("/dashboard"); expect(safeNext("/stocks/TCS?x=1#top")).toBe("/stocks/TCS?x=1#top"); });
  it("falls back for anything that could leave the site", () => {
    for (const bad of [null, "", "https://evil.example", "//evil.example", "/\\evil.example", "javascript:alert(1)", "/ok\nSet-Cookie: x"]) expect(safeNext(bad)).toBe("/dashboard");
  });
});
