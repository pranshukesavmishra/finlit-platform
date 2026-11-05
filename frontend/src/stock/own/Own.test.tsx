// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../../components/ChartHelp", () => ({ ChartHelp: () => null }));
import fixture from "../../lib/__fixtures__/ownershipInsightsReliance.json";
import type { Ownership } from "../../lib/api";
import { csvText, seriesFromTable, type OwnInsights } from "../../lib/ownView";
import { OwnInsightCards } from "./OwnInsightCards";
import { OwnFacts } from "./OwnFacts";
import { OwnCharts } from "./OwnCharts";
import { OwnershipSection } from "./OwnershipSection";

const ins = fixture as unknown as OwnInsights & { available: boolean };
const full: OwnInsights = { ...ins, available: true, premium: { state: "ok", reason: null, has: { structure: true, holders: true } } };
const S = seriesFromTable(ins.table!);
/** The stored shareholding in the shape /api/stocks/SYM/ownership sends, from the fixture's 21 filings (older filings are not needed here). */
const o = { meta: { symbol: "RELIANCE" }, periods: S.periods, asOf: "Sep 2026", comparedWith: "Sep 2025", series: S.values, latest: ins.table!.map((r) => ({ key: r.key, label: r.label, value: r.now, change1yPts: r.change_1y })) } as unknown as Ownership;
const wrap = (el: React.ReactElement) => render(<MemoryRouter>{el}</MemoryRouter>);
afterEach(cleanup);

describe("What changed, in short", () => {
  it("shows three cards with the tone as icon and word, a title and one number; the full text is for screen readers and tooltips", () => {
    const { container } = wrap(<OwnInsightCards ins={full} />);
    const cards = container.querySelectorAll(".ow-icard");
    expect(cards).toHaveLength(3);
    expect(cards[0].textContent).toContain("Worth knowing"); expect(cards[0].textContent).toContain("Indian funds buying what foreign funds sell"); expect(cards[0].textContent).toContain("Indian +1.4 pts, foreign −2.0 pts in a year");
    expect(cards[1].textContent).toContain("Supportive"); expect(cards[1].querySelector(".ow-glyph")?.textContent).toBe("+");
    expect(cards[0].getAttribute("title")).toBe(ins.cards![0].text);
    expect(cards[0].querySelector(".sr-only")?.textContent).toBe(ins.cards![0].text);
    expect(container.querySelector(".ow-glyph")?.getAttribute("aria-hidden")).toBe("true");
  });
  it("keeps the rest behind Show more, and Show fewer closes them", () => {
    wrap(<OwnInsightCards ins={full} />);
    expect(screen.queryByText("Foreign funds selling")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show 5 more" }));
    expect(screen.getByText("Foreign funds selling")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Show fewer" }).getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Show fewer" }));
    expect(screen.queryByText("Foreign funds selling")).toBeNull();
  });
  it("shows the quiet text when no card fires", () => {
    wrap(<OwnInsightCards ins={{ ...full, cards: [], more: [], quiet_text: "The latest filing shows no notable change." }} />);
    expect(screen.getByText("The latest filing shows no notable change.")).toBeTruthy(); expect(screen.queryByRole("button", { name: /Show/ })).toBeNull();
  });
  it("says why when the insights cannot be had, and shows a placeholder while they load", () => {
    const { container, rerender } = wrap(<OwnInsightCards why="The shareholding filings for this company have not been loaded yet." />);
    expect(container.textContent).toContain("have not been loaded yet");
    rerender(<MemoryRouter><OwnInsightCards /></MemoryRouter>);
    expect(container.querySelector(".skeleton")).toBeTruthy();
    rerender(<MemoryRouter><OwnInsightCards ins={full} stale /></MemoryRouter>);
    expect(container.textContent).toContain("being refreshed");
  });
  it("never gives advice", () => {
    const { container } = wrap(<OwnInsightCards ins={full} />);
    fireEvent.click(screen.getByRole("button", { name: /Show/ }));
    expect(container.textContent).not.toMatch(/\b(buy now|sell now|hold the stock|target price|avoid|accumulate|reduce|multibagger|top pick|best)\b/i);
  });
});

describe("the section", () => {
  it("draws the five parts in the designed order with the footer", () => {
    const { container } = wrap(<OwnershipSection o={o} ins={full} />);
    const t = container.textContent!;
    const order = ["What changed, in short", "Owners today", "Who bought and who sold", "How the shareholding pattern changed", "Also from the filing", "Largest institutional holders"].map((x) => t.indexOf(x));
    expect(order.every((x) => x >= 0)).toBe(true); expect([...order].sort((a, b) => a - b)).toEqual(order);
    expect(t).toContain("pts = percentage points of the company. From quarterly shareholding filings. Information only, not advice.");
    expect(container.querySelector("#ownership")).toBeTruthy();
    expect(container.querySelector(".own-yr2")).toBeTruthy();
  });
  it("the donut shows the promoters in the centre, and hovering a name or a slice changes it", () => {
    const { container } = wrap(<OwnershipSection o={o} ins={full} />);
    const centre = () => container.querySelector(".ow-center")!.textContent!;
    expect(centre()).toContain("PROMOTERS"); expect(centre()).toContain("50.4%");
    fireEvent.mouseEnter(screen.getByText("Foreign institutions", { selector: ".ow-legend .ow-n" }).closest("li")!);
    expect(centre()).toContain("FOREIGN INSTITUTIONS"); expect(centre()).toContain("16.7%");
    fireEvent.mouseEnter(container.querySelector('circle[data-slice="dii"]')!);
    expect(centre()).toContain("21.7%");
    fireEvent.mouseLeave(container.querySelector(".ow-donut-wrap")!);
    expect(centre()).toContain("PROMOTERS");
    expect(container.querySelector(".ow-donut svg")!.getAttribute("aria-label")).toContain("Promoters 50.4%");
    expect(container.querySelectorAll(".ow-legend li")).toHaveLength(5);
  });
  it("all chart labels are page text and no SVG holds a text element", () => {
    const { container } = wrap(<OwnershipSection o={o} ins={full} />);
    expect(container.querySelectorAll("svg text, svg tspan")).toHaveLength(0);
    expect(container.querySelector(".ow-tick")!.textContent).toMatch(/%$/);
  });
  it("picking a year changes the donut and the bought and sold bars to that year's last filing; the charts stay on the newest", () => {
    const { container } = wrap(<OwnershipSection o={o} ins={full} />);
    fireEvent.click(screen.getByRole("radio", { name: "2024" }));
    expect(container.querySelector("#ow-owners")!.textContent).toBe("Owners in Dec 2024");           // 2024's last filing in the data
    expect(container.querySelector(".ow-center")!.textContent).toContain("50.1%");
    expect(container.querySelector("#ow-moves")!.parentElement!.textContent).toContain("Dec 2023 → Dec 2024");
    expect(container.querySelector("#own-history")!.textContent).toContain("Sep 2026");
  });
  it("without insights it still draws the numbers and says why the readings are missing", () => {
    const { container } = wrap(<OwnershipSection o={o} insWhy="The short readings could not be loaded just now; the numbers below are unaffected." />);
    expect(container.textContent).toContain("could not be loaded just now"); expect(container.querySelector(".ow-donut")).toBeTruthy(); expect(container.querySelectorAll(".ow-panel")).toHaveLength(4);
    expect(container.textContent).toContain("Also from the filing");
  });
  it("shows a placeholder before the shareholding arrives and a reason when there is none", () => {
    const a = wrap(<OwnershipSection />); expect(a.container.querySelector(".skeleton")).toBeTruthy(); cleanup();
    const b = wrap(<OwnershipSection o={{ ...o, latest: [], periods: [] } as Ownership} />); expect(b.container.textContent).toContain("has not been loaded yet");
  });
  it("insights that are older than the stored shareholding are not shown as current", () => {
    const { container } = wrap(<OwnershipSection o={o} ins={{ ...full, as_of: "Jun 2026" }} />);
    expect(container.textContent).toContain("being refreshed for the newest filing"); expect(container.querySelector(".ow-icard")).toBeNull();
  });
});

describe("who bought and who sold, in the page", () => {
  it("defaults to one year with neutral badges and the plain note", () => {
    const { container } = wrap(<OwnershipSection o={o} ins={full} />);
    const badges = [...container.querySelectorAll("#ow-moves ~ * .ow-badge, .ow-move .ow-badge")].map((b) => b.textContent);
    expect(badges).toEqual(["▲ Bought 0.4 pts", "▼ Sold 2.0 pts", "▲ Bought 1.4 pts", "▲ Bought 0.2 pts"]);
    expect(container.textContent).toContain("No new shares were issued in this period, so a rise means buying and a fall means selling.");
    expect(screen.getByRole("button", { name: "1 year" }).getAttribute("aria-pressed")).toBe("true");
  });
  it("the period switch moves the comparison: last quarter, 3 years, 5 years", () => {
    const { container } = wrap(<OwnershipSection o={o} ins={full} />);
    fireEvent.click(screen.getByRole("button", { name: "Last quarter" }));
    expect(container.textContent).toContain("Jun 2026 → Sep 2026");
    fireEvent.click(screen.getByRole("button", { name: "3 years" }));
    expect(container.textContent).toContain("Sep 2023 → Sep 2026");
    fireEvent.click(screen.getByRole("button", { name: "5 years" }));
    expect(container.textContent).toContain("Sep 2021 → Sep 2026"); expect(container.textContent).toContain("The share count for Sep 2021 is not in the data");
    expect([...container.querySelectorAll(".ow-move .ow-badge")].map((b) => b.textContent)[0]).toBe("▼ Down 0.2 pts");
  });
  it("a share-count change of 0.5% or more switches the wording to Up / Down", () => {
    const issued = { ...full, facts: { ...full.facts, share_count_by_period: { ...full.facts!.share_count_by_period, "Sep 2025": 1000, "Sep 2026": 1010 } } };
    const { container } = wrap(<OwnershipSection o={o} ins={issued} />);
    expect([...container.querySelectorAll(".ow-move .ow-badge")].map((b) => b.textContent)).toEqual(["▲ Up 0.4 pts", "▼ Down 2.0 pts", "▲ Up 1.4 pts", "▲ Up 0.2 pts"]);
    expect(container.textContent).toContain("new shares were issued"); expect(container.textContent).not.toContain("a rise means buying");
  });
  it("disables windows that reach before the first filing", () => {
    const short = { ...o, periods: S.periods.slice(-3), series: Object.fromEntries(Object.entries(S.values).map(([k, v]) => [k, v!.slice(-3)])) } as unknown as Ownership;
    wrap(<OwnershipSection o={short} ins={full} />);
    expect((screen.getByRole("button", { name: "Last quarter" }) as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByRole("button", { name: "1 year" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "5 years" }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("the line charts, in the page", () => {
  it("draws four panels (Government is not charted) with now, start and change as page text", () => {
    const { container } = wrap(<OwnCharts series={S} symbol="RELIANCE" />);
    const panels = [...container.querySelectorAll(".ow-panel")];
    expect(panels.map((p) => p.getAttribute("data-group"))).toEqual(["promoters", "fii", "dii", "public"]);
    expect(panels[0].textContent).toContain("50.4%"); expect(panels[0].textContent).toContain("now, from 50.6% in Sep 2021"); expect(panels[0].textContent).toContain("▼ −0.2 pts");
    expect(panels[1].textContent).toContain("▼ −11.0 pts"); expect(panels[2].textContent).toContain("▲ +10.8 pts"); expect(panels[3].textContent).toContain("▲ +0.5 pts");
    expect(panels[1].querySelectorAll(".ow-tick")).toHaveLength(2);
    expect(panels[0].querySelector(".ow-xl")!.textContent).toBe("Sep 2021");
    expect(container.textContent).toContain("Government holds 0.1%.");
  });
  it("a hollow dot at the start and a filled dot at the end", () => {
    const { container } = wrap(<OwnCharts series={S} symbol="RELIANCE" />);
    const p = container.querySelector(".ow-panel")!;
    expect(p.querySelectorAll('[data-dot="start"]')).toHaveLength(1); expect(p.querySelectorAll('[data-dot="end"]')).toHaveLength(1);
    expect((p.querySelector('[data-dot="end"]') as HTMLElement).style.background).not.toBe(""); expect((p.querySelector('[data-dot="start"]') as HTMLElement).style.background).toBe("");
    expect(container.querySelector('[data-dot="start"]')!.className).toBe("ow-start");
  });
  it("1Y, 3Y and 5Y trim the window to 5, 13 and 21 filings", () => {
    const { container } = wrap(<OwnCharts series={S} symbol="RELIANCE" />);
    const filings = () => container.querySelector(".ow-panel")!.querySelectorAll(".ow-hit span").length;
    expect(filings()).toBe(21);
    fireEvent.click(screen.getByRole("button", { name: "3Y" })); expect(filings()).toBe(13); expect(container.querySelector(".ow-panel .ow-xl")!.textContent).toBe("Sep 2023");
    fireEvent.click(screen.getByRole("button", { name: "1Y" })); expect(filings()).toBe(5); expect(container.querySelector(".ow-panel .ow-xl")!.textContent).toBe("Sep 2025");
    expect(container.textContent).toContain("Sep 2025 to Sep 2026");
    fireEvent.click(screen.getByRole("button", { name: "5Y" })); expect(filings()).toBe(21);
  });
  it("hovering a quarter shows its value; leaving clears it; the arrow keys work too", () => {
    const { container } = wrap(<OwnCharts series={S} symbol="RELIANCE" />);
    const plot = container.querySelector(".ow-panel .ow-plot")!;
    expect(container.querySelector(".ow-tip")).toBeNull();
    fireEvent.mouseEnter(plot.querySelectorAll(".ow-hit span")[19]);
    expect(container.querySelector(".ow-tip")!.textContent).toBe("Jun 2026: 50.48%");
    fireEvent.mouseLeave(plot); expect(container.querySelector(".ow-tip")).toBeNull();
    fireEvent.keyDown(plot, { key: "End" }); expect(container.querySelector(".ow-tip")!.textContent).toBe("Sep 2026: 50.44%");
    fireEvent.keyDown(plot, { key: "ArrowLeft" }); expect(container.querySelector(".ow-tip")!.textContent).toBe("Jun 2026: 50.48%");
    fireEvent.keyDown(plot, { key: "Escape" }); expect(container.querySelector(".ow-tip")).toBeNull();
  });
  it("Show the numbers opens the table for the window, newest first, and hides again", () => {
    const { container } = wrap(<OwnCharts series={S} symbol="RELIANCE" />);
    expect(container.querySelector("table")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show the numbers" }));
    const rows = container.querySelectorAll("tbody tr");
    expect(rows).toHaveLength(21);
    expect(within(rows[0] as HTMLElement).getAllByRole("cell").map((c) => c.textContent)).toEqual(["50.44%", "16.67%", "21.72%", "11.07%", "0.09%"]);
    expect(rows[0].querySelector("th")!.textContent).toBe("Sep 2026");
    fireEvent.click(screen.getByRole("button", { name: "1Y" })); expect(container.querySelectorAll("tbody tr")).toHaveLength(5);
    fireEvent.click(screen.getByRole("button", { name: "Hide the numbers" })); expect(container.querySelector("table")).toBeNull();
  });
  it("Download CSV hands the browser the same text the numbers come from", () => {
    const blobs: Blob[] = [];
    URL.createObjectURL = vi.fn((b: Blob) => { blobs.push(b); return "blob:x"; }) as never; URL.revokeObjectURL = vi.fn() as never;
    let name = "";
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) { name = this.download; });
    wrap(<OwnCharts series={S} symbol="RELIANCE" />);
    fireEvent.click(screen.getByRole("button", { name: "Download CSV" }));
    expect(click).toHaveBeenCalled(); expect(name).toBe("RELIANCE_shareholding.csv"); expect(blobs[0].type).toBe("text/csv");
    return new Promise<void>((done) => { const r = new FileReader(); r.onload = () => { expect(r.result).toBe(csvText(S)); click.mockRestore(); done(); }; r.readAsText(blobs[0]); });
  });
  it("trimmed windows with a short history: only what exists is offered, and one filing draws nothing but says why", () => {
    const six = { periods: S.periods.slice(-6), values: Object.fromEntries(Object.entries(S.values).map(([k, v]) => [k, v!.slice(-6)])) };
    const { container } = wrap(<OwnCharts series={six} symbol="X" />);
    expect(container.querySelector(".ow-panel")!.querySelectorAll(".ow-hit span")).toHaveLength(6);        // 5Y asks for 21, the 6 that exist are shown
    expect((screen.getByRole("button", { name: "1Y" }) as HTMLButtonElement).disabled).toBe(false);
    expect((screen.getByRole("button", { name: "3Y" }) as HTMLButtonElement).disabled).toBe(false);   // offered once, as "all of it"
    expect((screen.getByRole("button", { name: "5Y" }) as HTMLButtonElement).disabled).toBe(true);
    cleanup();
    const one = wrap(<OwnCharts series={{ periods: ["Sep 2026"], values: { promoters: [50] } }} symbol="X" />);
    expect(one.container.textContent).toContain("Not enough filings yet to draw a trend");
  });
});

describe("Also from the filing and the largest institutional holders", () => {
  it("shows the four facts and the named holders from the stored insights", () => {
    const { container } = wrap(<OwnFacts ins={full} />);
    const facts = [...container.querySelectorAll(".ow-fact")].map((f) => f.textContent);
    expect(facts).toEqual(["Shareholders50.7 lakh+15% in a year", "Promoter shares pledged0.0%None pledged", "Shares outstanding1,353 croreUnchanged in a year", "Shares under lock-in0.0%No lock-in"]);
    const holders = [...container.querySelectorAll(".ow-holder")].map((h) => h.textContent);
    expect(holders[0]).toBe("Life Insurance Corporation of India6.94% →7.11%"); expect(holders).toHaveLength(4);
    expect(container.textContent).toContain("1% or more · a year ago → now");
  });
  it("says why each blank is blank when the premium part is missing", () => {
    const miss: OwnInsights = { ...full, facts: { ...full.facts, shareholders: null, promoter_pledged_pct: null, share_count_cr: null, locked_in_pct: null, top_holders: [] },
      premium: { state: "missing", reason: "These details come from the data provider and are fetched overnight for each company; they appear here after the next run.", has: { structure: false, holders: false } } };
    const { container } = wrap(<OwnFacts ins={miss} />);
    expect(container.querySelectorAll(".ow-fact")).toHaveLength(4);
    for (const f of container.querySelectorAll(".ow-fact")) { expect(f.textContent).toContain("–"); expect(f.textContent).toContain("fetched overnight"); }
    expect(container.querySelector(".ow-why")!.textContent).toContain("fetched overnight");
    expect(container.textContent).toContain("fetched overnight");
    expect(container.querySelectorAll(".ow-holder")).toHaveLength(0);
  });
  it("while the insights load, the blanks do not claim a reason", () => {
    const { container } = wrap(<OwnFacts />);
    expect(container.querySelectorAll(".ow-fact")).toHaveLength(4);
  });
});
