import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { PlatformGrid } from "./PlatformGrid";
import { PLATFORM_CARDS, PLAN_LINK, PLAN_TIER, TIER_FILTERS, filterByTier } from "../lib/platformCards";
import { planTarget } from "../lib/planTarget";

const html = renderToStaticMarkup(<MemoryRouter><PlatformGrid /></MemoryRouter>);
// Every route path declared in App.tsx, read from the source so a removed page fails this test.
const app = readFileSync(new URL("../App.tsx", import.meta.url), "utf8");
const routes = new Set([...app.matchAll(/path="([^"]+)"/g)].map((m) => "/" + m[1].replace(/\/\*$/, "")));

describe("Explore our platform grid", () => {
  it("renders 13 cards with the exact titles, in order", () => {
    expect((html.match(/class="pg-card"/g) ?? []).length).toBe(13);
    const titles = ["Pick Your Stocks", "Analyse Any Stock", "Compare Companies", "Track with Watchlists", "Analyse Your Portfolio", "Stay Ahead with Alerts", "Follow Market News", "Join the Discussion", "Explore ETFs", "Explore Mutual Funds", "Mutual Fund Research", "Revenue and Profit Outlook", "Smart Finance Calculators"];
    expect(PLATFORM_CARDS.map((c) => c.title)).toEqual(titles);
    titles.forEach((t) => expect(html).toContain(t));
    expect(html).not.toContain("Value Smarter");
    expect(html).toContain("Everything you need to invest smarter");
  });
  it("numbers 01 to 13, three bullets each, a known plan badge", () => {
    expect(PLATFORM_CARDS.map((c) => c.n)).toEqual(Array.from({ length: 13 }, (_, i) => String(i + 1).padStart(2, "0")));
    PLATFORM_CARDS.forEach((c) => { expect(c.bullets).toHaveLength(3); expect(["FREE ACCOUNT", "SILVER", "GOLD"]).toContain(c.plan); });
  });
  it("links every card to a route that exists in App.tsx", () => {
    PLATFORM_CARDS.forEach((c) => { expect(routes.has(c.to), c.to).toBe(true); expect(html).toContain(`href="${c.to}"`); });
  });
  it("uses no advice wording", () => { expect(html).not.toMatch(/\b(buy|sell|target price|recommend\w*)\b|\bhold (rating|call)/i); });
  it("filters by the lowest plan", () => {
    expect(filterByTier(PLATFORM_CARDS, "all")).toHaveLength(13);
    const by = (k: "basic" | "silver" | "gold") => filterByTier(PLATFORM_CARDS, k).map((c) => c.title);
    expect(by("silver")).toEqual(["Track with Watchlists", "Analyse Your Portfolio"]);
    expect(by("gold")).toEqual(["Revenue and Profit Outlook"]);
    expect(by("basic")).toHaveLength(10);
    expect(TIER_FILTERS.map((f) => f.label)).toEqual(["All", "Free", "Silver", "Gold"]);
    PLATFORM_CARDS.forEach((c) => expect(by(PLAN_TIER[c.plan])).toContain(c.title));
  });
  it("shows the Silver and Gold banners and sends them, and the paid badges, to the plan", () => {
    expect(PLAN_LINK).toEqual({ silver: "/plans#silver", gold: "/plans#gold" });
    expect(html).toContain('href="/plans#gold"'); expect(html).toContain('href="/plans#silver"');
    expect(html).toContain("See the Gold plan"); expect(html).toContain("See the Silver plan");
    const goldBadges = html.match(/<a[^>]*class="pg-badge gold"[^>]*href="\/plans#gold"|<a[^>]*href="\/plans#gold"[^>]*class="pg-badge gold"/g) ?? [];
    expect(goldBadges).toHaveLength(1);
    expect((html.match(/class="pg-badge silver"/g) ?? []).length).toBe(2);
    expect(html).toContain("Free, Silver and Gold");
  });
  it("never nests a link inside a link", () => { expect(html).not.toMatch(/<a\b(?:(?!<\/a>)[\s\S])*<a\b/); });
  it("the Gold banner lists only what Gold really adds, and never the admin-only Prism PDF", () => {
    const gold = html.slice(html.indexOf("pg-plan gold"), html.indexOf("pg-filter"));
    ["FinLit Prism", "model filters", "Profit and revenue outlook", "up to 50 watchlists"].forEach((t) => expect(gold).toContain(t));
    expect(gold).not.toMatch(/pdf/i);
    const silver = html.slice(html.indexOf("pg-plan silver"), html.indexOf("pg-plan gold"));
    expect(silver).not.toMatch(/Prism|outlook|up to 4/i);
  });
  it("every paid badge matches how the page is really gated", () => {
    const gated: Record<string, [string, string]> = { "/watchlist": ["pages/Watchlist.tsx", "silver"], "/holdings": ["pages/Holdings.tsx", "silver"], "/outlook": ["pages/Outlook.tsx", "gold"] };
    PLATFORM_CARDS.forEach((c) => {
      const t = PLAN_TIER[c.plan];
      if (t !== "basic") { const [f, tier] = gated[c.to]; expect(tier).toBe(t); expect(readFileSync(new URL("../" + f, import.meta.url), "utf8")).toContain(`<Gate tier="${tier}"`); }
      else expect(gated[c.to], c.title).toBeUndefined();
    });
    const back = readFileSync(new URL("../../../backend/finlit/outlook/router.py", import.meta.url), "utf8");
    expect(back).toContain('has(ctx.plan, "gold")');
  });
  it("opens a plan from /plans#gold, #silver or ?plan=gold", () => {
    expect(planTarget("#gold", "")).toBe("gold"); expect(planTarget("#silver", "")).toBe("silver"); expect(planTarget("", "?plan=gold")).toBe("gold");
    expect(planTarget("#plan-gold", "")).toBe("gold"); expect(planTarget("#nope", "")).toBeNull(); expect(planTarget("", "")).toBeNull();
  });
});
