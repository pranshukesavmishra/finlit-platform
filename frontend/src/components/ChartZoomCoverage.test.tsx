// @vitest-environment jsdom
// Every chart in the platform either has the shared enlarge arrow (components/ChartZoom.tsx), has its own, or is exempt with a reason.
// The scan fails when a file that draws a chart is on none of the three lists, so a new chart cannot ship without a decision.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LineChart } from "../charts/LineChart";
import { MiniBars } from "../charts/MiniBars";
import { Radar } from "../charts/Radar";
import { Waterfall } from "../charts/Waterfall";
import { RoeLines } from "../charts/RoeLines";
import { Radar as FundRadar } from "../mf/Radar";

const SRC = join(process.cwd(), "src") + "/";

/** Files whose charts carry the shared arrow: each must use ChartZoom (or MiniBars' zoomLabel). */
const ZOOM = [
  // company page
  "charts/MiniBars.tsx", "charts/PriceChart.tsx", "charts/IntradayChart.tsx", "charts/FinChart.tsx", "charts/LineChart.tsx", "charts/RoeLines.tsx", "charts/Waterfall.tsx", "charts/Radar.tsx", "charts/OutlookChart.tsx",
  "stock/Sections.tsx", "stock/Sections2.tsx", "stock/Sections3.tsx", "stock/ChartLab.tsx", "stock/SegmentMix.tsx", "stock/ProfitReality.tsx", "stock/ProfitabilityRatios.tsx", "stock/RevenueCash.tsx",
  "stock/ScoreMoves.tsx", "stock/PrismHistory.tsx", "stock/MacroOutlook.tsx", "stock/Leadership.tsx", "stock/own/OwnCharts.tsx", "stock/own/OwnersToday.tsx", "components/prism/pzr/History.tsx", "components/prism/pzr/Parts.tsx",
  // markets, flows, macro, sectors
  "pages/Markets.tsx", "components/FlowsCharts.tsx", "pages/Macro.tsx", "components/sectors/BreadthChart.tsx", "components/rotation/RotationMap.tsx", "components/rotation/RotationCard.tsx", "pages/LeadershipLabel.tsx",
  // funds, MF, ETFs
  "mf/FundChart.tsx", "mf/H2HChart.tsx", "mf/Radar.tsx", "mf/ScoreHistory.tsx", "mf/ScoreCompare.tsx", "mf/screen/Graphics.tsx", "pages/FundInsights.tsx", "pages/Funds.tsx", "pages/MfPortfolio.tsx", "etf/EtfChart.tsx", "etf/Detail.tsx", "etf/Compare.tsx",
  // portfolio, dashboard, calculators, tools
  "pages/Portfolio.tsx", "holdings/HoldingsSection.tsx", "portfolio/Risk.tsx", "portfolio/Together.tsx", "components/dashboard/MarketToday.tsx", "pages/SipCalculator.tsx", "pages/EpsCalculator.tsx", "pages/Dcf.tsx",
  "pages/Fundamentals.tsx", "pages/OptionChain.tsx", "pages/Ipo.tsx", "components/AdvScatter.tsx", "components/QrGrowth.tsx",
];

/** Charts that already had their own enlarge arrow before the shared one: the file must still carry it. */
const OWN: { file: string; needle: RegExp; why: string }[] = [
  { file: "pages/GraphStudio.tsx", needle: /Enlarge chart \$\{i \+ 1\}|ZoomGlyph/, why: "chart builder cells: .gx-zoom enlarges a cell over the page (now drawn with the shared glyph)" },
  { file: "stock/Sections4.tsx", needle: /Expand \$\{c\.title\}/, why: "Trends cards: .tr-x grows a card to the full row" },
];

/** Drawings with nothing to enlarge: sparklines, gauges and rings that show one figure, decorative art, icons, tiny inline bars. */
const EXEMPT: Record<string, string> = {
  "components/ChartSays.tsx": "The collapsible reading under a chart: it has a small caret icon, not a chart.",
  "charts/Dial.tsx": "score dial: one figure, drawn as a ring",
  "charts/Small.tsx": "sparklines, the RSI gauge and a small donut (the donut is wrapped where it is a chart: Fundamentals)",
  "charts/Atlas.tsx": "chart primitives; the arrow is on the card that holds them (Chart lab cards, Fundamentals, fund portfolio mix)",
  "components/GraphCharts.tsx": "chart builder primitives; the builder's cells have their own arrow (GraphStudio)",
  "components/DrawLayer.tsx": "drawing tool layer, not a chart",
  "components/Art.tsx": "decorative art", "components/BlogArt.tsx": "decorative art", "components/PageArt.tsx": "decorative art", "components/PageHeaderArt.tsx": "decorative art",
  "components/LogoLoader.tsx": "logo animation", "components/TierEmblem.tsx": "plan emblem", "components/ToolIcon.tsx": "icon", "lib/icons.tsx": "icons",
  "components/AppShell.tsx": "icons", "components/Layout.tsx": "icons", "components/PageFaqs.tsx": "icon", "components/QueryRules.tsx": "icons", "components/SearchFilters.tsx": "icons",
  "components/SplitDivider.tsx": "panel divider handle", "components/screener/FilterGroup.tsx": "icons", "components/screener/PageParts.tsx": "small completeness ring in a summary strip",
  "components/search/SearchOverlay.tsx": "icons", "components/search/parts.tsx": "sparklines and icons in search rows", "components/search/prismParts.tsx": "score ring in a search row",
  "components/prism/pzr/Hero.tsx": "score ring and scale: one figure", "components/prism/pzr/Landing.tsx": "decorative mark", "components/prism/shared/PartTile.tsx": "score tile ring",
  "components/prism/shared/PrismGlyph.tsx": "glyph", "components/rotation/Parts.tsx": "corner glyphs and a sparkline in a table row",
  "mf/ScoreCard.tsx": "score ring: one figure", "pages/Blog.tsx": "icons", "pages/Compare.tsx": "score ring; its radar charts carry the arrow (charts/Radar.tsx)", "pages/FundScoreScreener.tsx": "score ring",
  "pages/Home.tsx": "FinLit IQ dial: one figure", "pages/Plans.tsx": "icons", "stock/Hero.tsx": "price sparkline in the header", "stock/PlFlagsLayer.tsx": "icons and small revenue-against-profit gap bars",
  "stock/PrismCardView.tsx": "score rings, scale bar and info icon", "components/prism/pzr/Technical.tsx": "technical gauges: one figure each",
  "components/dashboard/Legacy.tsx": "six-bar spark inside a link card", "components/dashboard/Snapshot.tsx": "one breadth bar", "components/FlowsPanel.tsx": "46px bars under two figures (the full charts are on the FII/DII page)",
  "pages/ScreenerPro.tsx": "small distribution histogram inside a filter and a completeness ring", "pages/ScoreScreener.tsx": "completeness ring", "pages/AdvancedScoreScreener.tsx": "completeness ring",
  "pages/Watchlist.tsx": "one stacked industry strip", "stock/DuPont.tsx": "per-factor mini bars inside a table", "stock/CompanyBrief.tsx": "inline progress bars", "pages/PremiumReport.tsx": "inline score bars",
  "portfolio/Summary.tsx": "one score scale", "components/sectors/Parts.tsx": "three small bars inside a table cell", "etf/common.tsx": "sparklines in list rows", "pages/Fundamentals.tsx.exempt": "",
};
delete EXEMPT["pages/Fundamentals.tsx.exempt"];

const files = (() => {
  const out: string[] = [];
  const walk = (d: string) => { for (const n of readdirSync(d)) { const p = join(d, n); if (statSync(p).isDirectory()) { if (n !== "content") walk(p); } else if (/\.tsx$/.test(n) && !/\.test\.tsx$/.test(n)) out.push(relative(SRC, p)); } };
  walk(SRC);
  return out;
})();
const text = (f: string) => readFileSync(join(SRC, f), "utf8");
/** A file that draws a chart: a chart hook, a labelled SVG, or a marked list or grid of bars. */
const DRAWS = /useChart\(|<svg[^>]*role="(?:img|group)"|<svg[^>]*viewBox|data-chart/;

describe("every chart has the enlarge arrow, or a reason not to", () => {
  it("each file on the list uses the shared wrapper", () => {
    for (const f of ZOOM) expect(/ChartZoom|zoomLabel=/.test(text(f)), `${f} should use ChartZoom`).toBe(true);
  });

  it("charts that kept their own arrow still have it", () => {
    for (const o of OWN) expect(o.needle.test(text(o.file)), `${o.file}: ${o.why}`).toBe(true);
  });

  it("every exemption names its reason and points at a real file", () => {
    for (const [f, why] of Object.entries(EXEMPT)) { expect(why.length, f).toBeGreaterThan(3); expect(files.includes(f), `${f} does not exist`).toBe(true); }
  });

  it("no file is both exempt and on the list", () => {
    for (const f of Object.keys(EXEMPT)) expect(ZOOM.includes(f), f).toBe(false);
  });

  it("no chart file is missing from the inventory", () => {
    const known = new Set([...ZOOM, ...OWN.map((o) => o.file), ...Object.keys(EXEMPT), "components/ChartZoom.tsx"]);
    const unknown = files.filter((f) => DRAWS.test(text(f)) && !known.has(f));
    expect(unknown, "A file draws a chart but is on no list in ChartZoomCoverage.test.tsx: wrap it in <ChartZoom>, or exempt it with a reason.").toEqual([]);
  });
});

describe("the chart components render the arrow", () => {
  beforeEach(() => vi.stubGlobal("ResizeObserver", class { observe() {} unobserve() {} disconnect() {} }));
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
  const arrows = () => screen.queryAllByRole("button", { name: /^Enlarge chart/ });

  it("line chart", () => {
    render(<LineChart periods={["2023", "2024", "2025"]} series={[{ key: "a", label: "Margin", color: "red", values: [1, 2, 3] }]} fmt={(v) => String(v)} />);
    expect(arrows().map((b) => b.getAttribute("aria-label"))).toEqual(["Enlarge chart: Margin"]);
  });

  it("bar chart: only when it is asked for, so small tiles stay plain", () => {
    const props = { labels: ["a", "b"], series: [{ key: "x", label: "X", color: "red", values: [1, 2] }], fmt: (v: number) => String(v) };
    const { unmount } = render(<MiniBars {...props} />);
    expect(arrows()).toHaveLength(0);
    unmount();
    render(<MiniBars {...props} zoomLabel="Revenue by period" />);
    expect(arrows()).toHaveLength(1);
  });

  it("radar, fund radar, bridge and ROE lines", () => {
    render(<Radar axes={["A", "B", "C"]} series={[{ key: "s", label: "S", cls: "k0", values: [10, 20, 30] }]} />);
    render(<FundRadar label="Fund parts" series={[{ name: "Fund", values: [10, 20, 30, 40], color: "red" }]} />);
    render(<Waterfall ariaLabel="Bridge" bars={[{ key: "s", label: ["2025", "ROE"], value: 10, kind: "total" }, { key: "t", label: ["Tax", ""], value: 2, kind: "delta" }]} />);
    render(<RoeLines labels={["2024", "2025"]} series={[{ key: "r", label: "ROE", values: [10, 12], color: "red", marker: "circle" }]} fmt={(v) => String(v)} ariaLabel="ROE" />);
    expect(arrows()).toHaveLength(4);
  });
});
