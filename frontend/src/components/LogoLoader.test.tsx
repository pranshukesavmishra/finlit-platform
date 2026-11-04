// @vitest-environment jsdom
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FinLitLogo, InlineLoading, LogoLoader, PageLoading } from "./LogoLoader";

const html = readFileSync(resolve(process.cwd(), "index.html"), "utf8");
const css = readFileSync(resolve(process.cwd(), "src/styles/logo-loader.css"), "utf8");

describe("the FinLit logo and its loader", () => {
  it("the loader tells a screen reader what is happening and hides the drawing", () => {
    render(<LogoLoader label="Loading the page" />);
    expect(screen.getByRole("status").textContent).toContain("Loading the page");
    expect(document.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
  });
  it("comes in sizes", () => {
    const { container } = render(<><LogoLoader size="sm" /><LogoLoader size="xl" /></>);
    expect(container.querySelectorAll("svg.ll-sm").length).toBe(1);
    expect(container.querySelectorAll("svg.ll-xl").length).toBe(1);
  });
  it("the still logo (the header) has every part of the brand and no animation class; the loader plays the same drawing", () => {
    const still = renderToStaticMarkup(<FinLitLogo className="lg-svg" />), play = renderToStaticMarkup(<LogoLoader />);
    for (const part of ["ll-F", "ll-n", "ll-i", "ll-t", "ll-stairs", "ll-person", "ll-b1", "ll-b2", "ll-b3", "ll-arrow"]) { expect(still).toContain(part); expect(play).toContain(part); }
    expect(still).not.toContain("ll-play");
    expect(play).toContain("ll-play");
    expect(renderToStaticMarkup(<PageLoading />)).toContain("ll-person");
    expect(renderToStaticMarkup(<InlineLoading>Calculating…</InlineLoading>)).toContain("Calculating…");
  });
  it("the first-load splash in index.html is the same markup as the component (regenerate it when the component changes)", () => {
    const want = renderToStaticMarkup(<div className="ll-splash"><LogoLoader size="xl" label="Loading FinLit" /></div>);
    expect(html).toContain(want);
    expect(html).toContain('href="/src/styles/logo-loader.css"');   // linked as a source file: Vite bundles it with a content hash, so it can never be served stale
    expect(existsSync(resolve(process.cwd(), "public/logo-loader.css"))).toBe(false);   // a plain file in public/ keeps its name and is cached by browsers
  });
  it("the animation has its beats, plays only for people who have not asked for less motion, and the still logo is the finished one", () => {
    for (const name of ["ll-life", "ll-wipe", "ll-rise-f", "ll-rise-n", "ll-rise-i", "ll-rise-t", "ll-walk", "ll-bar1", "ll-bar2", "ll-bar3", "ll-sweep"]) expect(css).toContain("@keyframes " + name);
    expect(css).toContain("prefers-reduced-motion: no-preference");
    expect(css.match(/\.ll-play [^{]*\{[^}]*animation:/g)?.length).toBeGreaterThanOrEqual(10);   // movement lives only under .ll-play and the media query
    const walk = css.match(/@keyframes ll-walk \{([\s\S]*?)\n\}/)?.[1] ?? "";
    expect(walk).toMatch(/50% \{ transform: translate\(0px, 0px\)/);                              // he ends exactly where the logo has him
    expect(css).toMatch(/\.ll \{[^}]*--ll-d: 3\.6s/);                                           // a loop of 3.6 s: unhurried
  });
});
