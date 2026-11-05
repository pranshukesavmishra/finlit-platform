// @vitest-environment jsdom
// Sector Pulse, the industry page, the stock card and the Learn page, against the real batch output of 29 Oct 2026 (src/lib/__fixtures__/sectors).
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import board from "../lib/__fixtures__/sectors/board.json";
import ferrous from "../lib/__fixtures__/sectors/ferrous-metals.json";
import sambhv from "../lib/__fixtures__/sectors/sambhv.json";
import { ApiError } from "../lib/api";
import { chartGeometry, filterCounts, inFilter, mergedReasons, sortRows, type Board, type IndustryPage, type StockSector } from "../lib/sectors";
import { mainFinding, studyCards, studyRows } from "../lib/sectorStudy";

const st = vi.hoisted(() => ({ board: null as unknown, page: null as unknown, stock: null as unknown }));
const q = (d: unknown) => (d instanceof Error ? { data: undefined, isLoading: false, isError: true, error: d, refetch: () => {} } : { data: d, isLoading: false, isError: false, error: null, refetch: () => {} });
vi.mock("../lib/sectors", async (orig) => ({ ...(await orig<typeof import("../lib/sectors")>()), useSectorBoard: () => q(st.board), useSectorPage: () => q(st.page), useStockSector: () => q(st.stock) }));
vi.mock("../lib/leadership", async (orig) => ({ ...(await orig<typeof import("../lib/leadership")>()), useLeadership: () => ({ data: undefined }) }));
vi.mock("../lib/ui", () => ({ useUI: () => ({ toast: vi.fn(), plan: "basic", upgrade: vi.fn(), has: () => true }), TIER: { basic: { n: "Basic", ic: "sprout", tc: "--t-basic" }, silver: { n: "Silver", ic: "medal", tc: "--t-silver" }, gold: { n: "Gold", ic: "crown", tc: "--t-gold" } } }));
vi.mock("../lib/rotation", async (orig) => ({ ...(await orig<typeof import("../lib/rotation")>()), useRotationMap: () => ({ data: undefined, isLoading: false, isError: false }), useRotationCard: () => ({ data: undefined, isLoading: false, isError: false }) }));   // the rotation card has its own tests (Rotation.test.tsx)
vi.mock("../lib/title", () => ({ useDocTitle: () => undefined }));
import { SectorPulsePage } from "./SectorPulse";
import { SectorIndustryPage } from "./SectorIndustry";
import { LearnSectorSignalsPage } from "./LearnSectorSignals";
import { SectorPeersSection, oneLine } from "../stock/SectorPeers";

const B = board as unknown as Board;
const P = ferrous as unknown as IndustryPage;
const S = sambhv as unknown as StockSector;
const basicBoard = (): Board => ({ ...B, rows: B.rows.map((r) => ({ ...r, leader_flags: null })), leader_flags: null, locked: { leader_flags: "silver" } });
const notLoaded = () => new ApiError(503, { status: "not_loaded", reason: "Sector data is not loaded yet: the nightly sector job is switched off on this server." } as never);

beforeEach(() => { vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} }); st.board = B; st.page = P; st.stock = S; });
afterEach(cleanup);
const at = (ui: React.ReactElement, path = "/") => render(<MemoryRouter initialEntries={[path]}><Routes><Route path="/sectors/:slug" element={ui} /><Route path="*" element={ui} /></Routes></MemoryRouter>);

describe("helpers", () => {
  it("filters and counts like the design", () => {
    const c = filterCounts(B.rows);
    expect(c).toEqual({ all: 37, thrust: 0, washout: 15, fading: 22, flags: 20 });
    expect(B.rows.filter((r) => inFilter(r, "flags")).every((r) => (r.leader_flags ?? 0) > 0)).toBe(true);
    expect(filterCounts(basicBoard().rows).flags).toBeNull();
  });
  it("sorts with missing values last and keeps the board order for ties", () => {
    const by = sortRows(B.rows, "above_50", "desc");
    expect(by[0].breadth.above_50).toBeGreaterThanOrEqual(by[1].breadth.above_50 ?? 0);
    expect(sortRows(B.rows, "name", "asc")[0].name).toBe([...B.rows].map((r) => r.name).sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()))[0]);
    expect(sortRows(B.rows, null, "asc").map((r) => r.slug)).toEqual(B.rows.map((r) => r.slug));
    const withNull = sortRows([{ ...B.rows[0], leader_flags: null }, { ...B.rows[1], leader_flags: 3 }], "flags", "asc");
    expect(withNull[0].leader_flags).toBe(3);
  });
  it("merges the two traded-value reasons into one bar", () => {
    const m = mergedReasons(B.universe.reasons);
    expect(m.filter((r) => r.reason.startsWith("median traded value")).length).toBe(1);
    expect(m[0].stocks).toBe(1076 + 97);
    expect(m.reduce((s, r) => s + r.stocks, 0)).toBe(B.universe.reasons.reduce((s, r) => s + r.stocks, 0));
  });
  it("places every band and event of the chart on the history", () => {
    const g = chartGeometry(P, 40, 880, 20, 300);
    expect(g.bandRects.length).toBe(P.bands.length);
    expect(g.marks.length).toBe(P.events.filter((e) => P.history.dates.includes(e.date)).length);
    expect(g.path(P.history.above_50).startsWith("M")).toBe(true);
    expect(g.y(0)).toBe(300); expect(g.y(100)).toBe(20);
  });
  it("builds study sentences only from the figures, and says nothing without them", () => {
    expect(studyCards(B.study.figures).map((c) => c.key)).toEqual(["C", "CAP", "market", "Confirmed"]);
    expect(studyCards(B.study.figures)[0].text).toContain("48%");
    expect(studyRows(B.study.figures).find((r) => r.signal === "Big rallies")?.cases).toBe(285);
    expect(studyRows(B.study.figures).find((r) => r.signal === "6-month quarter at a C thrust")?.cases).toBe(10914);
    expect(mainFinding(B.study.figures)).toContain("215 cases in 36 separate weeks");
    expect(studyCards(undefined)).toEqual([]); expect(mainFinding({})).toBeNull();
  });
});

describe("Sector Pulse", () => {
  it("shows the date line, six tiles with zero counts, the market block and the breadth warning from the data", () => {
    at(<SectorPulsePage />);
    expect(screen.getByRole("heading", { level: 1, name: "Sector Pulse" })).toBeTruthy();
    expect(document.body.textContent).toContain("1,198 stocks counted");
    expect(document.body.textContent).toContain("37 groups with a reading (31 NSE industries and 6 sector groups)");
    const tiles = screen.getByLabelText("How many groups are in each state");
    expect(within(tiles).getAllByRole("listitem")).toHaveLength(6);
    expect(tiles.querySelectorAll(".zero").length).toBe(4);
    expect(document.body.textContent).toContain("22,936.75"); expect(document.body.textContent).toContain("−4.1%");
    expect(screen.getByText(/22 of 37 groups are Fading/)).toBeTruthy();
  });
  it("lists every group in a table whose rows open the industry page, and the filter buttons narrow it", () => {
    at(<SectorPulsePage />);
    const rows = () => within(screen.getByTestId("groups-table")).getAllByRole("row").length - 1;
    expect(rows()).toBe(37);
    fireEvent.click(screen.getByRole("button", { name: /^Fading/ }));
    expect(rows()).toBe(22);
    fireEvent.click(screen.getByRole("button", { name: /^Fresh thrusts/ }));
    expect(screen.getByText("No group is in a fresh thrust today.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /^All/ }));
    expect(screen.getByRole("link", { name: "Ferrous Metals" }).getAttribute("href")).toBe("/sectors/ferrous-metals");
    expect(screen.getByLabelText(/Ferrous Metals: share of counted stocks above their 9-day average 29%/)).toBeTruthy();
  });
  it("sorts by a column header and says which way", () => {
    at(<SectorPulsePage />);
    const head = screen.getByRole("columnheader", { name: /Index vs 52-wk high/ });
    fireEvent.click(within(head).getByRole("button"));
    expect(head.getAttribute("aria-sort")).toBe("ascending");
    fireEvent.click(within(head).getByRole("button"));
    expect(head.getAttribute("aria-sort")).toBe("descending");
  });
  it("shows the higher-low share under 20% with a spoken reason, the too-few list, the universe and the flags", () => {
    at(<SectorPulsePage />);
    expect(screen.getAllByText(/under 20%: a capitulation/).length).toBeGreaterThan(0);
    expect(screen.getByText("Too few stocks for a reading")).toBeTruthy();
    expect(screen.getByText(/Construction Materials/)).toBeTruthy();
    expect(screen.getByText("2,591")).toBeTruthy(); expect(screen.getByText("1,198")).toBeTruthy();
    expect(screen.getByText(/Show all 58/)).toBeTruthy();
    expect(screen.getByText("KRISHANA")).toBeTruthy();
    expect(document.body.textContent).toContain("not a recommendation");
    expect(document.body.textContent).not.toMatch(/\b(buy now|sell now|target price|accumulate)\b/i);
  });
  it("for Basic: leader flags are locked in words, the filter is disabled, nothing is an empty cell", () => {
    st.board = basicBoard();
    at(<SectorPulsePage />);
    expect((screen.getByRole("button", { name: /With leader flags/ }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/The list of leader flags is part of the Silver plan/)).toBeTruthy();
    expect(screen.getAllByText("Silver").length).toBeGreaterThan(30);
    expect(screen.queryByText("KRISHANA")).toBeNull();
  });
  it("when the data is not loaded it says why, with the server's sentence", () => {
    st.board = notLoaded();
    at(<SectorPulsePage />);
    expect(screen.getByText(/Sector data is not loaded yet: the nightly sector job is switched off/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });
});

describe("industry page", () => {
  const open = () => at(<SectorIndustryPage />, "/sectors/ferrous-metals");
  it("shows the state chip, the meta line, the market strip and the summary", () => {
    open();
    expect(screen.getByRole("heading", { level: 1, name: "Ferrous Metals" })).toBeTruthy();
    expect(document.body.textContent).toContain("Washout · since 21 Sept");
    expect(document.body.textContent).toContain("14 stocks counted, 8 not counted");
    expect(document.body.textContent).toContain("Nifty 50 22,936.75, 4.1% below its 200-day exponential average");
    expect(screen.getByText(/Ferrous Metals stocks have been sold broadly/)).toBeTruthy();
    expect(document.querySelector(".sx-cyc4 .here")?.textContent).toContain("1 · Washout");
    expect(document.body.textContent).toContain("2 · Thrust (CAP if it came now)");
  });
  it("draws the chart with its words, markers and a keyboard cursor", () => {
    open();
    const g = screen.getByRole("group", { name: /Breadth over 260 sessions from 10 Oct 2025 to 29 Oct 2026/ });
    expect(g.getAttribute("tabindex")).toBe("0");
    const readout = screen.getByTestId("chart-readout");
    expect(readout.textContent).toContain("29 Oct 2026"); expect(readout.textContent).toContain("9-day 29%"); expect(readout.textContent).toContain("50-day 7%");
    fireEvent.keyDown(g, { key: "ArrowLeft" });
    expect(screen.getByTestId("chart-readout").textContent).toContain("28 Oct 2026");
    fireEvent.keyDown(g, { key: "Home" });
    expect(screen.getByTestId("chart-readout").textContent).toContain("10 Oct 2025");
    expect(document.querySelectorAll(".ev-t").length).toBe(P.events.filter((e) => e.kind === "thrust_c" || e.kind === "thrust_cap").length);
    expect(screen.getByTestId("chart-story").textContent).toContain("C on 12 Dec, C on 28 Jan, C on 7 Apr, CAP on 29 Jul");
    expect(screen.getByText(/Show the chart as a table \(260 sessions\)/)).toBeTruthy();
  });
  it("derives the six number cards from the data", () => {
    open();
    const t = document.body.textContent ?? "";
    expect(t).toContain("29% · 14% · 7%"); expect(t).toContain("−16.9%"); expect(t).toContain("4 sessions ago");
    expect(t).toContain("Only 2 of the 14 stocks"); expect(t).toContain("CAP · 29 Jul 2026");
    expect(t).toContain("It turned Fading the next session, on 30 Jul");
    expect(t).toContain("None has one live");
  });
  it("shows the study box from the board's figures and marks the type possible now", () => {
    open();
    expect(screen.getByText("C thrust · 476 cases")).toBeTruthy();
    expect(screen.getByText("CAP thrust · 214 cases").closest(".sx-sc")?.textContent).toContain("The type possible here now");
    expect(document.body.textContent).toContain("Today: Nifty below 200-day");
  });
  it("Gold: ranked table with peer labels, notes and the not-counted chips with their reasons", () => {
    open();
    const rows = within(screen.getByTestId("ranked-table")).getAllByRole("row");
    expect(rows).toHaveLength(15);
    expect(rows[1].textContent).toContain("KIRLFER"); expect(rows[1].textContent).toContain("+0.3%"); expect(rows[1].textContent).toContain("In line");
    expect(screen.getByText("Not counted: 8 Ferrous Metals stocks")).toBeTruthy();
    expect(screen.getAllByText("AMFI average market cap under Rs 1,000 crore", { selector: ".sx-pill" })).toHaveLength(7);
    expect(document.body.textContent).toContain("Describes price and breadth data");
  });
  it("Basic: the table and the not-counted list are replaced by a sentence naming the plan; the chart stays", () => {
    st.page = { ...P, stocks: null, not_counted: null, leader_flags: null, locked: { stocks: "silver", not_counted: "silver", leader_flags: "silver" } };
    open();
    expect(screen.getByText("The ranked stock table is part of the Silver plan")).toBeTruthy();
    expect(screen.getByText("The list of stocks that are not counted is part of the Silver plan")).toBeTruthy();
    expect(screen.queryByTestId("ranked-table")).toBeNull(); expect(screen.getByTestId("chart-readout")).toBeTruthy();
    expect(document.body.textContent).toContain("Whether any flag is live is part of the Silver plan");
    expect(document.body.textContent).toContain("14 stocks counted, 8 listed stocks not counted".replace("8 listed", "8 listed"));
  });
  it("Silver: the peer label column says Gold instead of a blank", () => {
    st.page = { ...P, stocks: P.stocks!.map((s) => ({ ...s, peer_label: null })), locked: { peer_label: "gold" } };
    open();
    expect(within(screen.getByTestId("ranked-table")).getAllByText("Gold").length).toBe(14);
  });
  it("unknown or unavailable: says so, never a blank page", () => {
    st.page = new ApiError(404, { status: "not_found", reason: "There is no industry or sector group with this address." } as never);
    open();
    expect(screen.getByText("No such industry")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Back to Sector Pulse" })).toBeTruthy();
  });
});

describe("stock page section", () => {
  it("adds the rotation line under the industry's state, from sector.rotation", () => {
    st.stock = { ...S, rotation: { corner: "ahead_slowing", corner_name: "Ahead but slowing", weeks_in_corner: 1, this_week_reading_name: "Ahead and gaining", rank: 7, ranked: 37, rank_change_1w: 1, rank_change_4w: -3, strength_pts: 7.8, change_pts: -2.1, breadth: "narrow", breadth_name: "Narrow" } };
    render(<MemoryRouter><SectorPeersSection symbol="SAMBHV" name="Sambhv Steel Tubes" /></MemoryRouter>);
    const line = screen.getByTestId("stock-rotation");
    expect(line.textContent).toContain("Against other industries:"); expect(line.textContent).toContain("Ahead but slowing"); expect(line.textContent).toContain("7 of 37");
    expect(line.textContent).toContain("+7.8 pts"); expect(line.textContent).toContain("New this week; this week reads Ahead and gaining"); expect(line.textContent).toContain("Past returns, not a forecast");
  });
  it("writes the one line and the two cards from the sector JSON", () => {
    expect(oneLine("SAMBHV", S)).toBe("SAMBHV is in the top quarter of Industrial Products stocks over 6 months (+32.4%), and the industry as a whole is in a Washout while the Nifty 50 is below its 200-day exponential average.");
    render(<MemoryRouter><SectorPeersSection symbol="SAMBHV" name="Sambhv Steel Tubes" /></MemoryRouter>);
    const t = screen.getByTestId("sector-peers").textContent ?? "";
    expect(t).toContain("20th of 105 counted Industrial Products stocks by 6-month return");
    expect(t).toContain("Bottomed before the industry"); expect(t).toContain("−4.1%"); expect(t).toContain("105 of 219");
    expect(t).toContain("No leader flag. A flag needs a 52-week closing high");
    expect(screen.getByRole("link", { name: "Open the Industrial Products page" }).getAttribute("href")).toBe("/sectors/industrial-products");
    expect(t).toContain("not a recommendation");
  });
  it("below Gold: the industry's state and what Gold adds, no rank", () => {
    st.stock = { symbol: "SAMBHV", name: "Sambhv Steel Tubes Limited", group: { ...S.group!, summary: undefined }, in_group: null, locked: { stock: "gold" } };
    render(<MemoryRouter><SectorPeersSection symbol="SAMBHV" name="Sambhv" /></MemoryRouter>);
    const t = screen.getByTestId("sector-peers").textContent ?? "";
    expect(t).toContain("The Sector & peers cards are part of the Gold plan"); expect(t).toContain("Washout"); expect(t).not.toContain("20th of");
  });
  it("not counted, unclassified and unavailable each say why", () => {
    st.stock = { ...S, in_group: false, note: "Not counted: traded value under Rs 1 crore a day.", not_counted_because: ["median traded value under Rs 1 crore a day"] };
    render(<MemoryRouter><SectorPeersSection symbol="X" name="X" /></MemoryRouter>);
    expect(screen.getByText("Not counted: traded value under Rs 1 crore a day.")).toBeTruthy();
    cleanup();
    st.stock = { symbol: "NEWCO", group: null, in_group: false, note: "Industry not yet classified.", locked: {} };
    render(<MemoryRouter><SectorPeersSection symbol="NEWCO" name="Newco" /></MemoryRouter>);
    expect(screen.getAllByText(/Industry not yet classified/).length).toBeGreaterThan(0);
    cleanup();
    st.stock = notLoaded();
    render(<MemoryRouter><SectorPeersSection symbol="X" name="X" /></MemoryRouter>);
    expect(screen.getByTestId("sector-blank").textContent).toContain("Sector data is not loaded yet");
  });
});

describe("Learn page", () => {
  it("has the four steps, the live counts, the study table from the figures, the finding, tabs and the cannot-tell list", () => {
    at(<LearnSectorSignalsPage />);
    expect(screen.getByRole("heading", { level: 1, name: "How to read sector signals" })).toBeTruthy();
    expect(screen.getByText("Measure breadth")).toBeTruthy();
    expect(document.body.textContent).toContain("1,243 of the 2,591 NSE stocks with an industry");
    expect(within(screen.getByTestId("study-table")).getAllByRole("row").length).toBeGreaterThan(8);
    expect(document.body.textContent).toContain("The main finding: the market mattered more than the thrust");
    fireEvent.click(screen.getByRole("tab", { name: "A stock in its industry" }));
    expect(screen.getByText("6-month quarter")).toBeTruthy();
    expect(screen.getByText("What these signals cannot tell you")).toBeTruthy();
    expect(document.body.textContent).toContain("These are past averages, not forecasts.");
  });
  it("without the board it still teaches, and says why the table is empty", () => {
    st.board = notLoaded();
    at(<LearnSectorSignalsPage />);
    expect(screen.getByText("Place it in the cycle")).toBeTruthy();
    expect(document.body.textContent).toContain("The study table is filled from the Sector Pulse data, which is not available just now. Sector data is not loaded yet");
  });
});
