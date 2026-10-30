// @vitest-environment jsdom
// Mutual Fund Health Score upgrades in a DOM: history chart, breakdown + radar, screener (filters, URL state, CSV columns, locked page, no request below Gold),
// leaderboard, compare, chip, admin panel and the wording scan.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const st = vi.hoisted(() => ({ plan: "gold" as "basic" | "silver" | "gold", calls: [] as string[], routes: {} as Record<string, unknown> }));
vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiGet: vi.fn(async (path: string) => { st.calls.push(path); const k = Object.keys(st.routes).find((r) => path.startsWith(r)); if (!k) throw new Error("no route " + path); return st.routes[k]; }),
  apiSend: vi.fn(async () => ({})),
}));
vi.mock("../lib/ui", () => ({
  useUI: () => ({ has: (t: string) => ({ basic: 0, silver: 1, gold: 2 })[st.plan] >= ({ basic: 0, silver: 1, gold: 2 } as Record<string, number>)[t], upgrade: vi.fn(), toast: vi.fn() }),
  TIER: { gold: { n: "Gold", tc: "--gold", ic: "star" }, silver: { n: "Silver", tc: "--silver", ic: "star" } },
}));
import { HistoryChart, ScoreHistoryCard } from "./ScoreHistory";
import { ScoreBreakdown } from "./ScoreBreakdown";
import { ScoreCompare } from "./ScoreCompare";
import { ScoreChip } from "./ScoreCell";
import { ScoreAdminPanel } from "./ScoreAdminPanel";
import { FundScoreScreenerPage } from "../pages/FundScoreScreener";
import { LEVEL_TOLERANCE, VIEWS, chips, clearChip, compareTo, csvUrl, emptyQuery, paramsToQuery, queryToParams, serverParams, CSV_HEADS } from "../lib/mfScoreUp";
import { MF_SCORE_COMPLIANCE } from "../lib/mfScore";

const BANNED = /\b(buy|sell|hold|recommended|best[- ]to[- ]buy|top pick|winner|avoid)\b/i;
const pill = (p: number, r: number, c: number, q: number) => ({ performance: p, risk: r, cost: c, quality: q });
const pt = (d: string, f: number) => ({ date: d, week: d, final: f, label: f >= 65 ? "Healthy" : "Average", status: "RATED", pillars: pill(f, f - 5, f + 5, f), rank: 5, rankOf: 40, percentile: 80 });
const item = (n: number, o: Record<string, unknown> = {}) => ({ key: "mf:" + n, kind: "mf", code: n, symbol: null, name: `Fund ${n}`, amc: "Test Mutual Fund", plan: "Direct", group: "EQ-LARGE", sub: "large-cap", categoryLabel: "Large Cap",
  final: 80 - n, label: "Healthy", status: "RATED", reason: null, pillars: pill(70, 60, 50, 40), rank: n, rankOf: 40, aumCr: 1234, ageYears: 8.2, ter: 0.55, r1y: 12.3, r3y: 15.1, r5y: null, fullData: true, flags: [], ...o });
const wrap = (ui: React.ReactNode, at = "/fund-score-screener") => { const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } }); const Where = () => <output data-testid="loc">{useLocation().search}</output>;
  return render(<QueryClientProvider client={qc}><MemoryRouter initialEntries={[at]}><Routes><Route path="*" element={<>{ui}<Where /></>} /></Routes></MemoryRouter></QueryClientProvider>); };
vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} });
beforeEach(() => { st.plan = "gold"; st.calls = []; st.routes = {}; });
afterEach(cleanup);

describe("pure helpers", () => {
  it("states the ahead / level / behind tolerance", () => {
    expect(LEVEL_TOLERANCE).toBe(3);
    expect([compareTo(70, 60), compareTo(62, 60), compareTo(50, 60), compareTo(null, 60)]).toEqual(["ahead", "level", "behind", "na"]);
  });
  it("round-trips the screener state through the address", () => {
    const q = { ...emptyQuery(), plan: "all", subs: ["large-cap"], labels: ["Strong"], min: "60", cost: ["70", ""] as [string, string], full: true, sort: "ter", dir: "asc" as const, page: 3 };
    const back = paramsToQuery(queryToParams(q));
    expect(back).toMatchObject({ plan: "all", subs: ["large-cap"], labels: ["Strong"], min: "60", full: true, sort: "ter", dir: "asc", page: 3 });
    expect(back.cost).toEqual(["70", ""]);
    expect(queryToParams(emptyQuery()).toString()).toBe("");
    const sp = serverParams(q, { limit: 50, offset: 100 });
    expect(sp.get("cost_min")).toBe("70");
    expect(sp.get("offset")).toBe("100");
    expect(sp.get("plan")).toBe("all");
    expect(csvUrl(q)).toContain("format=csv");
    expect(csvUrl(q)).toContain("limit=6000");
  });
  it("shows and clears active filter chips", () => {
    const q = { ...emptyQuery(), min: "60", labels: ["Strong", "Healthy"], terMax: "1" };
    expect(chips(q).map((c) => c.text)).toEqual(["Strong, Healthy", "Score 60 to ∞", "Expense ratio up to 1%"]);
    expect(clearChip(q, "labels").labels).toEqual([]);
  });
  it("names the quick views neutrally and uses only the four parts", () => {
    for (const v of VIEWS) { expect(v.label + v.say).not.toMatch(BANNED); expect(Object.keys(v.set).every((k) => ["min", "perf", "risk", "cost", "quality"].includes(k))).toBe(true); }
  });
  it("lists the CSV columns the server sends", () => { expect(CSV_HEADS.slice(0, 6)).toEqual(["Fund", "Fund house", "Plan", "Category", "Score", "Label"]); expect(CSV_HEADS).toHaveLength(19); });
});

describe("score history", () => {
  it("draws the line, the zones and a tooltip", () => {
    const { container } = render(<HistoryChart points={[pt("2026-09-25", 61), pt("2026-10-02", 63), pt("2026-10-23", 68)]} />);
    expect(container.querySelectorAll("rect").length).toBe(5);
    expect(container.querySelectorAll("path").length).toBe(1);
    fireEvent.click(screen.getByLabelText("Risk"));
    expect(container.querySelectorAll("path").length).toBe(2);
    fireEvent.pointerMove(container.querySelector("svg")!, { clientX: 5 });
    expect(screen.getByRole("status").textContent).toMatch(/Score 61\.0/);
  });
  it("says why there is no chart yet", async () => {
    st.routes["/api/mf/5/score/history"] = { locked: false, points: [pt("2026-10-23", 68)], count: 1, firstDate: "2026-10-23", note: "Not enough history yet: the score is stored weekly from 23 Oct 2026.", changes: null };
    wrap(<ScoreHistoryCard code={5} />);
    expect((await screen.findByText(/Not enough history yet/)).textContent).toMatch(/Not enough history yet: the score is stored weekly from 23 Oct 2026/);
  });
  it("shows the stored change sentence", async () => {
    st.routes["/api/mf/5/score/history"] = { locked: false, points: [pt("2026-09-25", 61), pt("2026-10-23", 68)], count: 2, firstDate: "2026-09-25", note: null, changes: { text: "The score moved up 7 points, from 61.0 to 68.0, since 25 Sep 2026." } };
    wrap(<ScoreHistoryCard code={5} />);
    expect((await screen.findByTestId("score-change")).textContent).toMatch(/moved up 7 points/);
  });
  it("draws nothing for a locked answer", async () => {
    st.routes["/api/mf/5/score/history"] = { locked: true, points: [], count: null, firstDate: null, note: null, changes: null };
    const { container } = wrap(<ScoreHistoryCard code={5} />);
    await vi.waitFor(() => expect(container.querySelector("[aria-busy]")).toBeNull());
    expect(container.querySelector(".mfu")).toBeNull();
  });
});

describe("breakdown", () => {
  const m = (id: string, pillar: string, state: string, own: number | null, points: number | null, extra = {}) => ({ id, label: id.toLowerCase(), pillar, state, value: own, own, peer: 5, peerN: 30, points, weight: 8, groupValue: null, why: null, ...extra });
  const s = { locked: false, group: "EQ-LARGE", groupName: "Large", status: "RATED", final: 66, label: "Healthy", disclaimer: "", method: "", model: "", months: 74, peers: { kind: "grp", n: 31, text: "" },
    pillars: [{ key: "performance", name: "Performance", weight: 35, score: 70 }, { key: "risk", name: "Risk", weight: 30, score: 60 }, { key: "cost", name: "Cost", weight: 15, score: 50 }, { key: "quality", name: "Quality", weight: 20, score: 40 }],
    metrics: [m("A_ONE", "performance", "A", 12, 90), m("F_TWO", "cost", "F", null, 35, { whyText: "expense ratio not reported", why: "ter_missing" }), m("N_THREE", "quality", "N", null, null)],
    categoryMedian: { performance: 55, risk: 52, cost: 50, quality: 51, final: 52, n: 40, plan: "Direct", categoryLabel: "Large Cap" } } as never;
  it("shows the radar, the data gaps box and the table with state explanations", () => {
    render(<ScoreBreakdown s={s} />);
    expect(screen.getByRole("img", { name: /Category median \(40 funds\)/ })).toBeTruthy();
    const gaps = screen.getByLabelText("Data gaps");
    expect(gaps.textContent).toMatch(/1 measure\(s\) used the group value/); expect(gaps.textContent).toMatch(/expense ratio not reported/);
    expect(screen.getByText(/74 months/)).toBeTruthy(); expect(screen.getByText(/31 funds · widened/)).toBeTruthy();
    fireEvent.click(screen.getByText("Show the measure-by-measure table"));
    const t = screen.getByRole("table");
    expect(within(t).getAllByText("Filled").length).toBe(1); expect(within(t).getByText(/does not apply to this kind of fund/)).toBeTruthy();
    expect(within(t).getAllByRole("row").length).toBe(1 + 4 + 3);
  });
  it("draws nothing for an unrated fund", () => { const { container } = render(<ScoreBreakdown s={{ ...(s as object), final: null } as never} />); expect(container.innerHTML).toBe(""); });
});

describe("screener", () => {
  it("shows the upgrade page and makes no request below Gold", () => {
    for (const plan of ["basic", "silver"] as const) {
      st.plan = plan; st.calls = [];
      wrap(<FundScoreScreenerPage />);
      expect(screen.getByText(/Screen every fund by its Health Score/)).toBeTruthy();
      expect(st.calls).toEqual([]);
      cleanup();
    }
  });
  const setup = () => { st.routes["/api/mf/score-screener/facets"] = { locked: false, categories: [{ sub: "large-cap", label: "Large Cap", group: "EQ-LARGE", n: { Direct: 40, Regular: 40 } }], runDate: "2026-10-23" };
    st.routes["/api/mf/score-screener?"] = { locked: false, total: 120, runDate: "2026-10-23", items: [item(1), item(2), item(3, { final: null, label: null, ter: null })] }; };
  it("lists funds, filters through the address, pages, and offers CSV and compare", async () => {
    setup(); wrap(<FundScoreScreenerPage />);
    expect(await screen.findByText("Fund 1")).toBeTruthy();
    expect(screen.getByText(/120/)).toBeTruthy();
    expect(st.calls.some((c) => c.startsWith("/api/mf/score-screener?") && c.includes("plan=Direct") && c.includes("limit=50"))).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Strong" }));
    expect(screen.getByTestId("loc").textContent).toContain("labels=Strong");
    fireEvent.change(screen.getByLabelText("Score min"), { target: { value: "60" } });
    expect(screen.getByTestId("loc").textContent).toContain("min=60");
    expect(screen.getByText("Score 60 to ∞")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /High Risk part/ }));
    expect(screen.getByTestId("loc").textContent).toContain("risk_min=70");
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByTestId("loc").textContent).toContain("page=2");
    fireEvent.click(screen.getByRole("button", { name: "Clear all filters" }));
    expect(screen.getByTestId("loc").textContent).toBe("");
    expect(screen.getByRole("button", { name: /Download CSV/ })).toBeTruthy();
    const compare = screen.getByRole("button", { name: /Compare/ }) as HTMLButtonElement;
    expect(compare.disabled).toBe(true);
    fireEvent.click(screen.getByLabelText("Compare Fund 1")); fireEvent.click(screen.getByLabelText("Compare Fund 2"));
    expect(compare.disabled).toBe(false);
  });
  it("sorts by a column, showing missing values as dashes", async () => {
    setup(); wrap(<FundScoreScreenerPage />);
    await screen.findByText("Fund 1");
    fireEvent.click(screen.getByRole("button", { name: /Expense %/ }));
    expect(screen.getByTestId("loc").textContent).toMatch(/sort=ter&dir=desc/);
    const row = screen.getByText("Fund 3").closest("tr")!;
    expect(within(row).getAllByText("—").length).toBe(3);
  });
  it("opens the leaderboard with the median, the spread and the near-identical note", async () => {
    setup();
    st.routes["/api/mf/leaderboard"] = { locked: false, sub: "large-cap", plan: "Direct", categoryLabel: "Large Cap", items: [item(1), item(2)], stats: { median: 70, p25: 65, p75: 74, min: 60, max: 79, n: 2, notRated: 3, performance: 60, risk: 60, cost: 60, quality: 60 }, nearIdentical: true, nearIdenticalText: "Funds in this category are near-identical: cost carries the most weight." };
    wrap(<FundScoreScreenerPage />, "/fund-score-screener?tab=board&sub=large-cap");
    expect((await screen.findByTestId("board-stats")).textContent).toMatch(/Median score 70\.0.*65\.0 and 74\.0/);
    expect(screen.getByText(/near-identical/)).toBeTruthy();
    expect(screen.getByLabelText("Ranks 1 of 2 on this score")).toBeTruthy();
    expect(document.body.textContent).toMatch(/ranks higher on this score/);
  });
});

describe("compare, chip, admin", () => {
  it("shows ahead, level and behind with the tolerance, the radar, rings and the ETF vs index link", async () => {
    const mk = (code: number, f: number, p: number, group = "EQ-LARGE") => ({ code, symbol: null, plan: "Direct", group, final: f, label: "Healthy", status: "RATED", reason: null, pillars: pill(p, 60, 60, 60), rank: 1, rankOf: 9, flags: [], confidence: 1, category: "x" });
    st.routes["/api/mf/scores?"] = { locked: false, total: 2, items: [mk(1, 70, 70, "OT-PASSIVE"), mk(2, 80, 71), mk(3, 60, 60)] };
    st.routes["/api/mf/scores/history"] = { locked: false, series: { "mf:1": [{ date: "2026-09-25", final: 60, label: "Average" }, { date: "2026-10-23", final: 70, label: "Healthy" }], "mf:2": [], "mf:3": [] } };
    wrap(<ScoreCompare codes={[1, 2, 3]} names={["A", "B", "C"]} />);
    expect(await screen.findByText(/Level means within 3 points/)).toBeTruthy();
    await screen.findAllByText("ahead");
    const perf = screen.getByRole("rowheader", { name: "Performance" }).closest("tr")!;
    expect(within(perf).getByText("level")).toBeTruthy(); expect(within(perf).getByText("behind")).toBeTruthy();
    expect(within(screen.getByText("Score (0 to 100)").closest("tr")!).getByText("ahead")).toBeTruthy();
    expect(screen.getByRole("img", { name: /The four parts of each fund/ })).toBeTruthy();
    expect(screen.getByRole("img", { name: /Score over time/ })).toBeTruthy();
    expect(screen.getByRole("link", { name: "ETF vs index fund" })).toBeTruthy();
  });
  it("locks compare below Gold and asks nothing for history", () => {
    st.plan = "silver"; st.routes["/api/mf/scores?"] = { locked: true, items: [] };
    wrap(<ScoreCompare codes={[1, 2]} />);
    expect(st.calls.some((c) => c.includes("history"))).toBe(false);
    expect(screen.getAllByText("Locked: Gold plan").length).toBeGreaterThan(3);
  });
  it("draws the score chip only with a score", () => {
    const { container, rerender } = render(<ScoreChip item={{ final: 71.4, label: "Healthy", status: "RATED" }} />);
    expect(container.textContent).toContain("71"); expect(container.querySelector(".b-hi")).toBeTruthy();
    rerender(<ScoreChip item={{ final: null, label: null, status: "NOT RATED" }} />); expect(container.innerHTML).toBe("");
    rerender(<ScoreChip />); expect(container.innerHTML).toBe("");
  });
  it("shows the admin health view marked internal", async () => {
    st.routes["/api/admin/mf-score/health"] = { internal: true, lastRun: { at: "2026-10-23T02:00:00", status: "ok", written: 5120, seconds: 9.1 }, total: 5120, status: { RATED: 4000, "NOT RATED": 120 },
      distribution: { bins: [], byGroup: { "EQ-LARGE": [0, 1, 2, 3, 4, 5, 4, 3, 2, 1] } }, filled: [{ group: "EQ-LARGE", funds: 90, withAGap: 12, measuresFilled: 15 }], zeroCounters: { ter_zero: 3 },
      notRated: [{ reason: "Under 12 months of NAV history", n: 120 }], topMissing: [{ id: "TER_ABS", label: "Expense ratio", why: "ter_missing", whyText: "expense ratio not reported", n: 40 }], peerSizes: { buckets: ["0 to 7"], byKind: { sub: [3] } }, history: { rows: 9, first: "2026-10-19", last: "2026-10-19" } };
    st.routes["/api/admin/mf-score/calibration"] = { internal: true, label: "Internal, descriptive, not a forecast. Do not publish.", monthsAgo: 12, asOf: "", historyStarts: null, funds: 0, quintiles: [], note: "The stored score history is too short for this look back: no weekly rows are stored yet.", how: "x" };
    wrap(<ScoreAdminPanel />);
    expect(await screen.findByText(/5,120 funds stored/)).toBeTruthy();
    expect(screen.getByText(/expense ratio not reported/)).toBeTruthy(); expect(screen.getByText(/ter_zero: 3/)).toBeTruthy();
    expect(await screen.findByText(/Internal, descriptive, not a forecast/)).toBeTruthy(); expect(await screen.findByText(/too short for this look back/)).toBeTruthy();
  });
});

describe("wording", () => {
  it("has no advice words in the new components", () => {
    for (const f of ["ScoreHistory.tsx", "ScoreBreakdown.tsx", "ScoreCompare.tsx", "ScoreAlertButton.tsx", "ScoreAdminPanel.tsx", "Radar.tsx", "../pages/FundScoreScreener.tsx", "../lib/mfScoreUp.ts"]) {
      const src = readFileSync(resolve(__dirname, f), "utf8");
      const strings = (src.match(/"[^"\n]{8,}"|`[^`\n]{8,}`/g) || []).filter((x) => !/className|^["`](\.\.|\/|@)/.test(x));
      for (const x of strings) expect(x.replace(/not a recommendation|not investment advice/gi, ""), f).not.toMatch(BANNED);
    }
    expect(MF_SCORE_COMPLIANCE).toContain("not a recommendation");
  });
});
