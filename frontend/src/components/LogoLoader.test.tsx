// @vitest-environment jsdom
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { InlineLoading, LogoLoader, PageLoading } from "./LogoLoader";

const html = readFileSync(resolve(process.cwd(), "index.html"), "utf8");
const css = readFileSync(resolve(process.cwd(), "public/logo-loader.css"), "utf8");

describe("the logo loader", () => {
  it("tells a screen reader what is happening and hides the drawing", () => {
    render(<LogoLoader label="Loading the page" />);
    expect(screen.getByRole("status").textContent).toContain("Loading the page");
    expect(document.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
  });
  it("comes in sizes and with the wordmark on request", () => {
    const { container } = render(<><LogoLoader size="sm" /><LogoLoader size="xl" wordmark /></>);
    expect(container.querySelectorAll("svg.ll-sm").length).toBe(1);
    expect(container.querySelector(".ll-word")?.textContent).toBe("FinLit");
  });
  it("the page and inline versions carry the same drawing", () => {
    const a = renderToStaticMarkup(<PageLoading />), b = renderToStaticMarkup(<InlineLoading>Calculating…</InlineLoading>);
    for (const h of [a, b]) expect(h).toContain("ll-person");
    expect(b).toContain("Calculating…");
  });
  it("the first-load splash in index.html is the same markup as the component (regenerate it when the component changes)", () => {
    const want = renderToStaticMarkup(<div className="ll-splash"><LogoLoader size="xl" wordmark label="Loading FinLit" /></div>);
    expect(html).toContain(want);
    expect(html).toContain('href="%BASE_URL%logo-loader.css"');
  });
  it("the animation has its steps: draw, four hops, bars, arrow, and still shows the finished logo for reduced motion", () => {
    for (const name of ["ll-draw", "ll-climb", "ll-pa", "ll-pb", "ll-bar1", "ll-bar2", "ll-bar3", "ll-arrow", "ll-pop", "ll-life"]) expect(css).toContain("@keyframes " + name);
    expect(css).toContain("prefers-reduced-motion: no-preference");        // movement only for people who have not asked for less
    const hops = (css.match(/@keyframes ll-climb \{([\s\S]*?)\n\}/)?.[1] ?? "").match(/translate\(/g) ?? [];
    expect(hops.length).toBe(14);                                          // start, 4 x (take-off, mid-air, landing), end
    expect(css).toMatch(/\.ll-person \{ transform: translate\(151px, 54px\)/);   // without animation the person already stands on the top step
  });
});
