// Regression (docs/KNOWN-ISSUES.md d): a donut with a single slice drew nothing, because an arc that ends where it starts is empty. It must be a ring.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Donut } from "./Atlas";

describe("Donut", () => {
  it("draws a ring in the part's colour for a single slice", () => {
    const html = renderToStaticMarkup(<Donut parts={[{ label: "Promoter", value: 100, color: "#123abc" }]} center="100%" />);
    expect(html).toMatch(/<circle[^>]*stroke="#123abc"/);
  });
  it("draws one coloured path per slice for several slices", () => {
    const html = renderToStaticMarkup(<Donut parts={[{ label: "A", value: 60, color: "#111111" }, { label: "B", value: 40, color: "#222222" }]} center="x" />);
    expect(html).toMatch(/<path[^>]*fill="#111111"/);
    expect(html).toMatch(/<path[^>]*fill="#222222"/);
  });
});
