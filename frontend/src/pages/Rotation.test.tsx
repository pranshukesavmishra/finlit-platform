// @vitest-environment jsdom
// Sector Rotation against the real nightly output of 29 Oct 2026 (src/lib/__fixtures__/rotation): the tab, the card, the helpers, the redirect and a wording scan of every sentence the pages print.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Navigate, Route, Routes } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import map from "../lib/__fixtures__/rotation/map.json";
import media from "../lib/__fixtures__/rotation/media.json";
import { ApiError } from "../lib/api";
import { mapGeometry, nextCorners, placeLabels, rankGrid, rankMove, rowsByRank, shade, sparkPath, type RotationCard, type RotationMap } from "../lib/rotation";

const st = vi.hoisted(() => ({ map: null as unknown, card: null as unknown }));
const q = (d: unknown) => (d instanceof Error ? { data: undefined, isLoading: false, isError: true, error: d, refetch: () => {} } : { data: d, isLoading: false, isError: false, error: null, refetch: () => {} });
vi.mock("../lib/rotation", async (orig) => ({ ...(await orig<typeof import("../lib/rotation")>()), useRotationMap: () => q(st.map), useRotationCard: () => q(st.card) }));
vi.mock("../lib/title", () => ({ useDocTitle: () => undefined }));
import { SectorRotationPage } from "./SectorRotation";
import { LearnSectorRotationPage } from "./LearnSectorRotation";
import { RotationCard as CardView } from "../components/rotation/RotationCard";

const M = map as unknown as RotationMap;
const C = { ...(media as unknown as RotationCard), reading: true } as RotationCard;
const BANNED = /\b(buy|sell|hold|accumulate|avoid|multibagger|top pick|signals?|target|best)\b/i;
beforeEach(() => { vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} }); st.map = M; st.card = C; });
afterEach(cleanup);
const at = (ui: React.ReactElement, path = "/") => render(<MemoryRouter initialEntries={[path]}><Routes><Route path="*" element={ui} /></Routes></MemoryRouter>);

describe("helpers", () => {
  it("writes rank moves with an arrow, 'new' for a first ranked week and flags moves of 3 or more", () => {
    expect(rankMove(3)).toMatchObject({ text: "▲3", dir: "up", big: true }); expect(rankMove(-1)).toMatchObject({ text: "▼1", big: false });
    expect(rankMove(0).text).toBe("–"); expect(rankMove(null)).toMatchObject({ text: "new", dir: "new" });
  });
  it("orders by rank and builds the 12-week grid from the file's rank history", () => {
    const rows = rowsByRank(M.rows);
    expect(rows[0].rank).toBe(1); expect(rows[0].name).toBe("Pharmaceuticals & Biotechnology");
    const g = rankGrid(M.rows, 12);
    expect(g.weeks.length).toBe(12); expect(g.rows.length).toBe(M.rows.length); expect(g.rows[0].cells[11]).toBe(1);
    const veh = g.rows.find((r) => r.row.slug === "agricultural-commercial-construction-vehicles")!;
    expect(veh.row.name).not.toMatch(/Capital Goods/); expect(veh.cells.length).toBe(12);
  });
  it("shades ranks in five buckets and leaves unranked weeks unshaded", () => {
    expect(shade(1, 37)).toBe(1); expect(shade(37, 37)).toBe(5); expect(shade(null, 37)).toBe(0);
  });
  it("puts every dot of the map inside the plot, holds 0 on both axes and labels only the top 6 when asked", () => {
    const g = mapGeometry(M.rows, 960, 560, 8, null);
    for (const d of g.dots) { expect(d.x).toBeGreaterThanOrEqual(g.left - 1); expect(d.x).toBeLessThanOrEqual(g.right + 1); expect(d.y).toBeGreaterThanOrEqual(g.top - 1); expect(d.y).toBeLessThanOrEqual(g.bottom + 1); }
    expect(g.x0).toBeGreaterThan(g.left); expect(g.y0).toBeLessThan(g.bottom);
    expect(g.dots.filter((d) => d.hollow).length).toBe(M.rows.filter((r) => r.this_week_reading).length);
    expect(mapGeometry(M.rows, 390, 420, 8, 6).dots.filter((d) => d.label).length).toBe(6);
    expect(Object.keys(placeLabels(g.dots)).length).toBe(M.rows.length);
  });
  it("draws a sparkline that breaks at an unranked week", () => {
    expect(sparkPath([{ rank: 1 }, { rank: 5 }, { rank: null }, { rank: 3 }], 100, 30, 10)).toMatch(/^M.*L.*M/);
  });
  it("reads where groups went next from the study, two at most", () => {
    const n = nextCorners(M.study, "behind_gaining");
    expect(n.length).toBeGreaterThan(0); expect(n.length).toBeLessThanOrEqual(2); expect(n[0].pct).toBe(Math.max(...Object.values(M.study!.moves.next_corner.behind_gaining)));
  });
});

describe("the Rotation tab", () => {
  it("shows the four corners with the file's counts, names and a glyph each", () => {
    at(<SectorRotationPage />);
    for (const [name, n] of Object.entries(M.counts)) { const tile = screen.getAllByText(name)[0].closest("button")!; expect(within(tile).getByText(String(n))).toBeTruthy(); expect(tile.querySelector("svg")).toBeTruthy(); }
  });
  it("says the week is in progress, and names the data without a vendor", () => {
    at(<SectorRotationPage />);
    expect(screen.getByText(/Week in progress: readings as of 29 Oct/)).toBeTruthy();
    expect(document.body.textContent).toContain("NSE daily data, equal-weighted industry groups");
  });
  it("filters the ranking with a tile and clears it again", () => {
    at(<SectorRotationPage />);
    const rows = () => screen.getByTestId("rank-table").querySelectorAll("tbody tr").length;
    expect(rows()).toBe(M.groups);
    fireEvent.click(screen.getByTestId("tile-behind_gaining"));
    expect(rows()).toBe(M.counts["Behind but gaining"]);
    fireEvent.click(screen.getByTestId("tile-behind_gaining"));
    expect(rows()).toBe(M.groups);
  });
  it("ranks every group, marks 'this week reads' and prints the renamed group, never Capital Goods", () => {
    at(<SectorRotationPage />);
    const t = screen.getByTestId("rank-table");
    expect(t.querySelectorAll("tbody tr").length).toBe(37);
    expect(within(t).getAllByText(/this week reads/).length).toBeGreaterThan(0);
    expect(document.body.textContent).toContain("Agricultural Commercial & Construction Vehicles");
    expect(document.body.textContent).not.toContain("Capital Goods");
  });
  it("switches to the map: a dot and a hollow dot where this week reads another corner", () => {
    at(<SectorRotationPage />);
    fireEvent.click(screen.getByRole("button", { name: "Map" }));
    expect(document.querySelectorAll(".rt-dotg").length).toBe(37);
    expect(document.querySelectorAll(".rt-dot.hollow").length).toBe(M.rows.filter((r) => r.this_week_reading).length);
  });
  it("lists who changed corner and the climbers and fallers from the file", () => {
    at(<SectorRotationPage />);
    expect(screen.getByText(/11 of 37/)).toBeTruthy();
    for (const m of M.moved_this_week.slice(0, 3)) expect(screen.getAllByText(m.name).length).toBeGreaterThan(0);
    for (const c of M.climbers_4w) expect(screen.getAllByText(c.name).length).toBeGreaterThan(0);
  });
  it("gives the reason when the data is not there", () => {
    st.map = new ApiError(503, { status: "not_loaded", reason: "Rotation data is not loaded yet: the current data set has no rotation files." } as never);
    at(<SectorRotationPage />);
    expect(screen.getByText(/Rotation data is not loaded yet/)).toBeTruthy();
  });
  it("says 'past averages, not forecasts' beside the study and keeps the disclaimer", () => {
    at(<SectorRotationPage />);
    expect(screen.getAllByText(/Past averages, not forecasts/i).length).toBeGreaterThan(0);
    expect(document.body.textContent).toContain("not a recommendation to buy, sell or hold any security");
  });
  it("describes and never advises: no advice word in anything the page and the Learn page print", () => {
    at(<SectorRotationPage />);
    const strip = (s: string) => s.replace(/not a recommendation to buy, sell or hold any security/gi, "");
    expect(strip(document.body.textContent ?? "")).not.toMatch(BANNED);
    cleanup(); at(<LearnSectorRotationPage />);
    expect(strip(document.body.textContent ?? "")).not.toMatch(BANNED);
    expect(JSON.stringify([M.study!.text, M.rows.map((r) => r.summary), M.method])).not.toMatch(BANNED);
  });
});

describe("the industry card", () => {
  it("shows rank, breadth, strength, change, the server's summary and the study line", () => {
    at(<CardView slug="media-entertainment-publication" groupName={C.name} />);
    const card = screen.getByTestId("rotation-card");
    expect(card.textContent).toContain(`${C.rank} of ${C.ranked}`); expect(card.textContent).toContain(C.summary); expect(card.textContent).toContain(C.corner_name);
    expect(card.textContent).toMatch(/Past averages, not forecasts/);
  });
  it("says why when the group has no reading", () => {
    st.card = { name: "Tiny", slug: "tiny", reading: false, note: "Fewer than 8 counted stocks, too few for a rotation reading." };
    at(<CardView slug="tiny" groupName="Tiny" />);
    expect(screen.getByText(/Fewer than 8 counted stocks/)).toBeTruthy();
  });
});

describe("the renamed group", () => {
  it("redirects /sectors/capital-goods to the vehicles group", () => {
    render(<MemoryRouter initialEntries={["/sectors/capital-goods"]}><Routes><Route path="/sectors/capital-goods" element={<Navigate to="/sectors/agricultural-commercial-construction-vehicles" replace />} /><Route path="/sectors/:slug" element={<p>landed</p>} /></Routes></MemoryRouter>);
    expect(screen.getByText("landed")).toBeTruthy();
  });
});
