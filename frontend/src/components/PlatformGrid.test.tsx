import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { PlatformGrid } from "./PlatformGrid";
import { PLATFORM_CARDS } from "../lib/platformCards";

const html = renderToStaticMarkup(<MemoryRouter><PlatformGrid /></MemoryRouter>);
// Every route path declared in App.tsx, read from the source so a removed page fails this test.
const app = readFileSync(new URL("../App.tsx", import.meta.url), "utf8");
const routes = new Set([...app.matchAll(/path="([^"]+)"/g)].map((m) => "/" + m[1].replace(/\/\*$/, "")));

describe("Explore our platform grid", () => {
  it("renders 11 cards with the exact titles, in order", () => {
    expect((html.match(/class="pg-card"/g) ?? []).length).toBe(11);
    const titles = ["Pick Your Stocks", "Analyse Any Stock", "Compare Companies", "Track with Watchlists", "Analyse Your Portfolio", "Stay Ahead with Alerts", "Follow Market News", "Join the Discussion", "Explore ETFs", "Explore Mutual Funds", "Smart Finance Calculators"];
    expect(PLATFORM_CARDS.map((c) => c.title)).toEqual(titles);
    titles.forEach((t) => expect(html).toContain(t));
    expect(html).not.toContain("Value Smarter");
    expect(html).toContain("Everything you need to invest smarter");
  });
  it("numbers 01 to 11, three bullets each, a known plan badge", () => {
    expect(PLATFORM_CARDS.map((c) => c.n)).toEqual(Array.from({ length: 11 }, (_, i) => String(i + 1).padStart(2, "0")));
    PLATFORM_CARDS.forEach((c) => { expect(c.bullets).toHaveLength(3); expect(["FREE ACCOUNT", "SILVER"]).toContain(c.plan); });
  });
  it("links every card to a route that exists in App.tsx", () => {
    PLATFORM_CARDS.forEach((c) => { expect(routes.has(c.to), c.to).toBe(true); expect(html).toContain(`href="${c.to}"`); });
  });
  it("uses no advice wording", () => { expect(html).not.toMatch(/\b(buy|sell|target price)\b/i); });
});
