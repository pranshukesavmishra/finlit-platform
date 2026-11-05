// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const st = vi.hoisted(() => ({ plan: "gold", upgrade: vi.fn() }));
vi.mock("../../../lib/ui", () => ({ useUI: () => ({ has: (t: string) => st.plan === "gold" || t !== "gold", upgrade: st.upgrade, toast: vi.fn() }), TIER: { basic: { n: "Basic", ic: "sprout", tc: "--t-basic" }, gold: { n: "Gold", ic: "crown", tc: "--t-gold" }, silver: { n: "Silver", ic: "medal", tc: "--t-silver" } } }));
vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
import { PresetPanel } from "./PresetPanel";
import { PresetPage } from "./PresetPage";
import { usePresetRoute } from "./usePresetRoute";
import { orderGroups, readPresetUrl, resolveChips, sortPresetRows } from "../../../lib/presets";

const chip = (id: string, label: string, d = false) => ({ id, label, default: d, description: label + " description" });
const P = (id: string, name: string, group: string, o = {}) => ({ id, name, group, cardText: name + " text", count: 5, asOf: "2026-10-31", status: "live", blockedReason: null, chips: [], howItWorks: ["Rule one", "Rule two"], locked: false, ...o });
const LIST = { asOf: "2026-10-31", groups: [
  { id: "own", name: "Ownership", presets: [P("inst", "Institutions buying", "Ownership")] },
  { id: "safe", name: "Safety", presets: [P("debt", "Debt-free compounders", "Safety"), P("psu", "PSU stocks", "Safety", { status: "blocked", count: null, blockedReason: "Coming soon: needs a PSU flag" })] },
  { id: "top", name: "Top rated", presets: [P("large", "Highest-rated large caps", "Top rated", { chips: [chip("trend", "Trend check")] })] },
  { id: "thm", name: "Themes", presets: [P("themes", "Sector themes in play", "Themes"), P("emp", "Emerging tech", "Themes", { chips: [chip("sub-ems", "EMS and electronics"), chip("rated", "Rated only", true)] })] },
] };
const col = (key: string, label: string, format = "num1") => ({ key, label, format, align: "right" });
const DETAIL = { id: "large", name: "Highest-rated large caps", asOf: "2026-10-31", count: 86, shown: 3, cardText: "Card text", disclaimer: "A screen narrows a list. It is not a recommendation.", howItWorks: ["Rule one"],
  columns: [col("prism", "Prism score", "score"), col("ret1y", "1-year return", "pct"), col("mcap", "Market cap", "cr")],
  rows: [{ symbol: "AAA", name: "Alpha Ltd", prism: 80, ret1y: 12.5, mcap: 90000, badges: ["Prism-confirmed"] }, { symbol: "BBB", name: "Beta Ltd", prism: 90, ret1y: null, mcap: 50000, badges: [] }, { symbol: "CCC", name: "Gamma", prism: 70, ret1y: -3, mcap: 70000, badges: ["Provisional"] }] };
const THEMES = { ...DETAIL, id: "themes", name: "Sector themes in play", themes: [{ industry: "Pharma", state: "in_play", breadth: 43, rs3: 7.5, members: 81, leaders: ["AAA"] }, { industry: "Telecom", state: "closest", breadth: 50, rs3: 41.9, members: 6, leaders: ["CCC"] }] };
const EMPTY = { ...DETAIL, id: "debt", name: "Debt-free compounders", count: 0, shown: 0, rows: [], closestMisses: [{ symbol: "ZZZ", name: "Zed", failed: ["Debt to equity above 0.1"] }] };

let calls: string[] = [], listBody: unknown = LIST, listStatus = 200, detail: Record<string, [number, unknown]> = {};
beforeEach(() => {
  calls = []; listBody = LIST; listStatus = 200; st.plan = "gold"; st.upgrade.mockReset(); detail = { large: [200, DETAIL], themes: [200, THEMES], debt: [200, EMPTY], emp: [200, { ...DETAIL, id: "emp", name: "Emerging tech" }] };
  vi.stubGlobal("fetch", vi.fn(async (u: string) => {
    calls.push(u);
    const m = /\/api\/screener\/presets\/([^?]+)/.exec(u);
    const [status, body] = m ? detail[m[1]] ?? [404, { detail: { status: "not_found" } }] : [listStatus, listBody];
    return { ok: status < 400, status, headers: new Headers(), json: async () => body } as unknown as Response;
  }));
});
afterEach(cleanup);

const Where = () => { const l = useLocation(); return <output data-testid="loc">{l.pathname + l.search}</output>; };
const Panel = () => { const r = usePresetRoute(); return <PresetPanel route={r} basics={<button type="button">Prism quick view</button>} basicsActive={false} />; };
const Page = () => { const r = usePresetRoute(); return r.id ? <PresetPage route={r} basics={<span>basics</span>} /> : <Panel />; };
const mount = (qs = "") => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={["/advanced-score-screener" + qs]}><Page /><Where /></MemoryRouter></QueryClientProvider>);
const loc = () => screen.getByTestId("loc").textContent || "";
const rowSyms = () => within(screen.getByRole("table")).getAllByRole("row").slice(1).map((r) => r.querySelector("b")?.textContent);

describe("grouped panel", () => {
  it("orders the groups as the spec does, Prism basics last, and opens the first group", async () => {
    mount();
    await screen.findByRole("button", { name: /Top rated/ });
    const names = screen.getAllByRole("button", { expanded: undefined }).filter((b) => b.hasAttribute("aria-expanded")).map((b) => b.querySelector(".psx-gt")?.textContent);
    expect(names).toEqual(["Top rated", "Themes", "Safety", "Ownership", "Prism basics"]);
    expect(screen.getByRole("button", { name: /Top rated/ }).getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("button", { name: /Safety/ }).getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(screen.getByRole("button", { name: /Safety/ }));
    expect(screen.getByRole("button", { name: /Safety/ }).getAttribute("aria-expanded")).toBe("true");
  });
  it("shows blocked screens as disabled cards with their reason", async () => {
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /Safety/ }));
    const card = screen.getByRole("button", { name: /PSU stocks/ });
    expect(card.getAttribute("aria-disabled")).toBe("true");
    expect(card.textContent).toContain("Coming soon: needs a PSU flag");
    fireEvent.click(card);
    expect(loc()).not.toContain("preset");
  });
  it("Prism basics is listed once: the server's own Prism basics group is not shown next to the page's list", async () => {
    listBody = { ...LIST, groups: [...LIST.groups, { id: "prism-basics", name: "Prism basics", presets: [P("pb1", "Prism strong and lower risk", "Prism basics")] }] };
    mount();
    await screen.findByText("Top rated");
    expect(screen.getAllByText("Prism basics")).toHaveLength(1);
  });
  it("keeps the Prism quick views working when the list is unavailable", async () => {
    listStatus = 500;
    mount();
    expect(await screen.findByText(/unavailable right now/, {}, { timeout: 4000 })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Prism quick view" })).toBeTruthy();
  });
  it("locked cards ask for Gold and do not open", async () => {
    listBody = { ...LIST, groups: [{ id: "top", name: "Top rated", presets: [P("large", "Highest-rated large caps", "Top rated", { locked: true, count: null })] }] };
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /Highest-rated large caps/ }));
    expect(st.upgrade).toHaveBeenCalled();
    expect(loc()).not.toContain("preset");
  });
});

describe("screen view", () => {
  it("choosing a screen sets the address and shows the response rows, card facts, how it works and the disclaimer", async () => {
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /Highest-rated large caps/ }));
    expect(loc()).toBe("/advanced-score-screener?preset=large");
    await screen.findByRole("table");
    expect(rowSyms()).toEqual(["AAA", "BBB", "CCC"]);
    expect(screen.getByText("86 match")).toBeTruthy();
    expect(screen.getByText("showing 3")).toBeTruthy();
    expect(screen.getByText(/as of 31 Oct 2026/)).toBeTruthy();
    expect(screen.getByText("How this screen works")).toBeTruthy();
    expect(screen.getByText("A screen narrows a list. It is not a recommendation.")).toBeTruthy();
    expect(screen.getByText("Prism-confirmed")).toBeTruthy();
    expect(screen.getByRole("link", { name: /AAA/ }).getAttribute("href")).toBe("/stocks/AAA");
    expect(within(rowOf("BBB")).getAllByLabelText("not available").length).toBe(1);   // a missing value is a dash, not 0
  });
  it("sorts the shown rows client-side, missing values last", async () => {
    mount("?preset=large");
    await screen.findByRole("table");
    fireEvent.click(screen.getByRole("button", { name: "Sort by 1-year return" }));
    expect(rowSyms()).toEqual(["AAA", "CCC", "BBB"]);
    fireEvent.click(screen.getByRole("button", { name: "Sort by 1-year return" }));
    expect(rowSyms()).toEqual(["CCC", "AAA", "BBB"]);
  });
  it("chips toggle, update the address and ask again with the chip; friendly params map to chip ids", async () => {
    mount("?preset=emp");
    await screen.findByRole("table");
    expect(calls.at(-1)).toContain("chip=rated");
    expect(screen.getByRole("button", { name: "Rated only" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "EMS and electronics" }));
    await waitFor(() => expect(calls.at(-1)).toMatch(/chip=rated&chip=sub-ems|chip=sub-ems&chip=rated/));
    expect(loc()).toContain("chip=sub-ems");
    fireEvent.click(screen.getByRole("button", { name: "Rated only" }));
    fireEvent.click(screen.getByRole("button", { name: "EMS and electronics" }));
    expect(loc()).toContain("chip=none");   // every option off, where one is on by default
  });
  it("a screen with a Trend check chip is asked with it from ?trend=1", async () => {
    mount("?preset=large&trend=1");
    await screen.findByRole("table");
    expect(calls.at(-1)).toBe("/api/screener/presets/large?chip=trend");
  });
  it("a BSE-only company shows its name with the exchange and code, and NSE-listed only leaves it out", async () => {
    detail.large = [200, { ...DETAIL, rows: [{ symbol: "AAA", name: "Alpha Ltd", exchange: "NSE", badges: [] }, { symbol: "543914", name: "Delta Small Ltd", exchange: "BSE", badges: [] }] }];
    mount("?preset=large");
    await screen.findByRole("table");
    expect(screen.getByText("Delta Small Ltd")).toBeTruthy(); expect(screen.getByText("BSE only, code 543914")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "NSE-listed only" }));
    expect(rowSyms()).toEqual(["AAA"]);
  });
  it("an empty result says so and lists the closest misses with the rule missed", async () => {
    mount("?preset=debt");
    expect(await screen.findByText("No company meets every rule today.")).toBeTruthy();
    expect(screen.getByText(/Debt to equity above 0.1/)).toBeTruthy();
    expect(screen.getByText("Closest to qualifying")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });
  it("theme cards filter the table to that theme's leaders", async () => {
    mount("?preset=themes");
    await screen.findByRole("table");
    expect(rowSyms()).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: /Pharma/ }));
    expect(rowSyms()).toEqual(["AAA"]);
    expect(screen.getByRole("button", { name: /Pharma/ }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: /Pharma/ }));
    expect(rowSyms()).toHaveLength(3);
  });
  it("an unknown screen id gets a calm message; Clear screen returns to the panel", async () => {
    mount("?preset=nope");
    expect(await screen.findByText("We could not find that screen")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Clear screen" }));
    expect(loc()).toBe("/advanced-score-screener");
    expect(await screen.findByRole("button", { name: /Top rated/ })).toBeTruthy();
  });
  it("a 403 from the detail shows the Gold teaser and never a table", async () => {
    detail.large = [403, { detail: { status: "plan_required" } }];
    mount("?preset=large");
    expect(await screen.findByText(/part of Gold/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Unlock with Gold/ }));
    expect(st.upgrade).toHaveBeenCalled();
    expect(screen.queryByRole("table")).toBeNull();
  });
});
const rowOf = (s: string) => screen.getByRole("link", { name: new RegExp(s) }).closest("tr")!;

describe("lib", () => {
  it("orders groups and drops empty ones", () => {
    expect(orderGroups([{ id: "x", name: "Zed", presets: [P("a", "A", "Zed") as never] }, { id: "e", name: "Safety", presets: [] }, { id: "t", name: "Trend", presets: [P("b", "B", "Trend") as never] }]).map((g) => g.name)).toEqual(["Trend", "Zed"]);
  });
  it("reads and resolves the address", () => {
    const u = readPresetUrl(new URLSearchParams("preset=p&chip=a&sub=ems&trend=1"));
    expect(u).toMatchObject({ preset: "p", chips: ["a"], trend: true, subs: ["ems"] });
    expect(resolveChips(u, { chips: [chip("sub-ems", "E")] } as never)).toEqual(["a", "trend", "sub-ems"]);
    expect(resolveChips(readPresetUrl(new URLSearchParams("preset=p")), { chips: [chip("r", "R", true), chip("q", "Q")] } as never)).toEqual(["r"]);
  });
  it("sorts text and numbers", () => {
    expect(sortPresetRows([{ symbol: "B" }, { symbol: "A" }], { key: "symbol", dir: 1 }).map((r) => r.symbol)).toEqual(["A", "B"]);
  });
});

describe("a company listed only on the BSE", () => {
  it("is shown by its name, never by the bare BSE code; the link and the CSV keep the code", async () => {
    detail.large = [200, { ...DETAIL, rows: [
      { symbol: "AAA", name: "Alpha Ltd", prism: 80, ret1y: 12.5, mcap: 90000, badges: [] },
      { symbol: "526775", name: "Valiant Communications Ltd", prism: 93, ret1y: 40, mcap: 1200, badges: [] },
      { symbol: "530001", name: null, prism: 70, ret1y: 5, mcap: 800, badges: [] },
    ] }];
    mount("?preset=large");
    await screen.findByText("Valiant Communications Ltd");
    expect(rowSyms()).toEqual(["AAA", "Valiant Communications Ltd", "530001"]);                       // the title is the name; with no name on file the code stays
    const table = screen.getByRole("table");
    expect(within(table).getAllByText("Valiant Communications Ltd")).toHaveLength(1);                // the name is not printed twice (title and small line)
    expect((within(table).getByText("Valiant Communications Ltd").closest("a") as HTMLAnchorElement).getAttribute("href")).toBe("/stocks/526775");
    expect(within(table).getByText("530001").getAttribute("title")).toMatch(/name is not in our data/);   // a blank has its reason
  });
});

describe("redesign: list text, notes, theme figures and the Basic tab", () => {
  it("the card and the screen say how much of what passes the list shows", async () => {
    listBody = { ...LIST, groups: [{ id: "top", name: "Top rated", presets: [P("large", "Highest-rated large caps", "Top rated", { listText: "Top 10 of 40 that pass" })] }] };
    detail.large = [200, { ...DETAIL, count: 40, shown: 10, listText: "Top 10 of 40 that pass", notes: ["2 rated companies were left out because their long-term technical view is blank."], rankScoreNote: "Ranked by a weighted score." }];
    mount("?preset=large");
    expect((await screen.findAllByText("Top 10 of 40 that pass")).length).toBeGreaterThanOrEqual(1);
    expect(await screen.findByText(/2 rated companies were left out/)).toBeTruthy();
    expect(await screen.findByText("Ranked by a weighted score.")).toBeTruthy();
    expect(screen.queryByText(/40 match/)).toBeNull();
  });
  it("a sector theme card shows the share near the 52-week high against the market, and why a closest sector is not in play", async () => {
    detail.themes = [200, { ...THEMES, themes: [{ industry: "Pharma", state: "in_play", breadth: 52, marketBreadth: 31, rs3: 7.5, members: 81, leaders: ["AAA"] },
      { industry: "Telecom", state: "closest", breadth: 38, marketBreadth: 31, rs3: 4.1, members: 12, leaders: [], reason: "Breadth is 38%, below the 40% needed." }] }];
    mount("?preset=themes");
    const card = await screen.findByRole("button", { name: /Pharma/ });
    expect(card.textContent).toMatch(/Near the high.*52%.*market 31%/);
    expect(screen.getByText("Breadth is 38%, below the 40% needed.")).toBeTruthy();
    expect(screen.queryByText("B50")).toBeNull();
  });
  it("a Basic-tab screen asks for Silver, not Gold, when the plan is short", async () => {
    detail.large = [403, { detail: { status: "plan_required" } }];
    st.plan = "basic";
    const Basic = () => { const r = usePresetRoute("basic"); return r.id ? <PresetPage route={r} /> : <PresetPanel route={r} />; };
    render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter initialEntries={["/score-screener?preset=large"]}><Basic /></MemoryRouter></QueryClientProvider>);
    expect(await screen.findByRole("heading", { name: /This screen is part of Silver/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Unlock with Silver/ }));
    expect(st.upgrade).toHaveBeenCalledWith("silver", expect.any(String));
    expect(screen.queryByText("Prism basics")).toBeNull();
  });
});


describe("results page by 25 (issue 30.b)", () => {
  const many = (from: number, n: number) => Array.from({ length: n }, (_, i) => ({ symbol: `S${from + i}`, name: `Stock ${from + i}`, prism: 70, ret1y: 5, mcap: 1000 + i, badges: [] as string[] }));
  const PAGED = { ...DETAIL, count: 60, shown: 25, pageSize: 25, offset: 0, limit: 25, available: 60, hasMore: true, rows: many(1, 25) };
  const serve = () => vi.stubGlobal("fetch", vi.fn(async (u: string) => {
    calls.push(u);
    if (!/\/presets\/large/.test(u)) return { ok: true, status: 200, headers: new Headers(), json: async () => LIST } as unknown as Response;
    const off = Number(/offset=(\d+)/.exec(u)?.[1] ?? 0), lim = Number(/limit=(\d+)/.exec(u)?.[1] ?? 25);
    const rows = many(1, 60).slice(off, off + lim);
    return { ok: true, status: 200, headers: new Headers(), json: async () => ({ ...PAGED, rows, shown: rows.length, offset: off, limit: lim, hasMore: off + rows.length < 60 }) } as unknown as Response;
  }));
  it("shows 1 to 25 of 60, then the next 25 with numbering that carries on, and back", async () => {
    serve(); mount("?preset=large");
    await screen.findByText("Stock 1");
    const pager = screen.getByRole("navigation", { name: "Pages of this screen" });
    expect(pager.textContent).toMatch(/Showing 1.25 of 60/);
    expect(rowSyms()).toHaveLength(25);
    expect((within(pager).getByRole("button", { name: "Previous 25" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(within(pager).getByRole("button", { name: "Show next 25" }));
    await screen.findByText("Stock 26");
    expect(calls.some((c) => /presets\/large\?offset=25/.test(c) || /offset=25/.test(c))).toBe(true);
    expect(screen.getByRole("navigation", { name: "Pages of this screen" }).textContent).toMatch(/Showing 26.50 of 60/);
    expect(within(screen.getByRole("table")).getAllByRole("row")[1].querySelector("td")?.textContent).toBe("26");
    fireEvent.click(screen.getByRole("button", { name: "Show next 10" }));
    await screen.findByText("Stock 51");
    const last = screen.getByRole("navigation", { name: "Pages of this screen" });
    expect(last.textContent).toMatch(/Showing 51.60 of 60/);
    expect((within(last).getByRole("button", { name: /Show next/ }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(within(last).getByRole("button", { name: "Previous 25" }));
    await screen.findByText("Stock 26");
  });
  it("a Top 10 list or a short list has no pager", async () => {
    mount("?preset=large");
    await screen.findByText("Alpha Ltd");
    expect(screen.queryByRole("navigation", { name: "Pages of this screen" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Export/ })).toBeNull();
  });
  it("has no export button", async () => {
    serve(); mount("?preset=large");
    await screen.findByText("Stock 1");
    expect(screen.queryByRole("button", { name: /Export/ })).toBeNull();
  });
});
