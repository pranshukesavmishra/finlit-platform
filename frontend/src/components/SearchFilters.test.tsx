// Rendered markup (no browser) of the shared filter controls and of two places that use them: the alert company picker and the Ctrl K palette.
import { renderToStaticMarkup } from "react-dom/server";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StaticRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import type { SearchIndex } from "../lib/api";
import { NO_FILTER, facetsOf, indexFacets } from "../lib/searchFilters";

const INDEX: SearchIndex = {
  fields: ["symbol", "name", "bse", "ready", "nse"],
  rows: [["AAA", "Alpha Infotech Ltd", "1", 0], ["BBB", "Beta Bank Ltd", "2", 0], ["CCC", "Gamma Soft Ltd", "3", 0]],
  sectors: ["Information Technology", "Financial Services"], sec: [0, 1, 0], mc: [250000, 90000, 2000],
};
vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  useSearchIndex: () => ({ data: INDEX, isLoading: false, isError: false, isPending: false }),
  useSearchQuotes: () => ({ data: undefined }),
  useSummary: () => ({ data: undefined }),
  prefetchStock: () => undefined,
}));
vi.mock("../lib/screener", () => ({ useUniverse: () => ({ data: undefined }) }));
vi.mock("../lib/mycompanies", () => ({ useMyCompanies: () => ({ symbols: [] }) }));

import { FilterNote, SearchFilters } from "./SearchFilters";
import { StockPicker } from "./AlertComposer";
import { SearchOverlay } from "./search/SearchOverlay";

const text = (html: string) => html.replace(/<[^>]+>/g, " ").replace(/&amp;/g, "&").replace(/&quot;/g, '"').replace(/\s+/g, " ");
const facets = indexFacets(INDEX);

describe("SearchFilters", () => {
  it("bar: two dropdowns that show the active choice, collapsed, with a clear-all only when something is chosen", () => {
    const off = renderToStaticMarkup(<SearchFilters facets={facets} value={NO_FILTER} onChange={() => undefined} />);
    expect(off).toContain("Sector"); expect(off).toContain("Market cap"); expect(off).toContain('aria-haspopup="listbox"'); expect(off).toContain('aria-expanded="false"');
    expect(off).not.toContain("Clear filters");
    const on = renderToStaticMarkup(<SearchFilters facets={facets} value={{ sector: "Information Technology", cap: "mega" }} onChange={() => undefined} />);
    expect(text(on)).toContain("Sector Information Technology"); expect(text(on)).toContain("Market cap Mega-cap"); expect(on).toContain("Clear filters");
  });
  it("bar: an open list offers Clear first, the real sectors with counts, and the honest left-out note", () => {
    const html = renderToStaticMarkup(<SearchFilters facets={facetsOf([{ sector: "Power", cap: 300 }, { sector: "Power", cap: null }, { sector: null, cap: 9000 }])} value={{ sector: "Power", cap: null }} onChange={() => undefined} menu="sector" />);
    const t = text(html);
    expect(t).toContain("Clear sector"); expect(t).toContain("Power 2"); expect(t).toContain("1 companies with no sector on file are left out");
    expect(html).toContain('role="listbox"'); expect(html).toContain('aria-selected="true"');
  });
  it("market-cap list shows the six bands with the portfolio checker's ranges", () => {
    const t = text(renderToStaticMarkup(<SearchFilters facets={facets} value={NO_FILTER} onChange={() => undefined} menu="cap" />));
    for (const w of ["Mega-cap", "Above ₹2,00,000 Cr", "Large-cap", "₹50,000–2,00,000 Cr", "Mid-cap", "Small-cap", "Micro-cap", "Nano-cap", "Below ₹500 Cr"]) expect(t).toContain(w);
  });
  it("renders nothing when the data carries no sector or market value", () => {
    expect(renderToStaticMarkup(<SearchFilters facets={facetsOf([])} value={NO_FILTER} onChange={() => undefined} />)).toBe("");
  });
  it("panel: one Filters button with the active count in its name", () => {
    const off = renderToStaticMarkup(<SearchFilters variant="panel" facets={facets} value={NO_FILTER} onChange={() => undefined} />);
    expect(off).toContain('aria-label="Filters"'); expect(off).toContain('aria-expanded="false"');
    const on = renderToStaticMarkup(<SearchFilters variant="panel" facets={facets} value={{ sector: "Financial Services", cap: null }} onChange={() => undefined} />);
    expect(on).toContain('aria-label="Filters, 1 active"');
  });
  it("empty note says what is empty and offers Clear", () => {
    const t = text(renderToStaticMarkup(<FilterNote filter={{ sector: "Information Technology", cap: "mega" }} q="zzz" onChange={() => undefined} />));
    expect(t).toContain("No Mega-cap Information Technology companies match “zzz”."); expect(t).toContain("Clear filters");
    expect(text(renderToStaticMarkup(<FilterNote filter={{ sector: null, cap: "nano" }} onChange={() => undefined} />))).toContain("No Nano-cap companies in the list.");
  });
});

describe("pickers that use it", () => {
  it("alert company picker: the search box and the Filters button", () => {
    const html = renderToStaticMarkup(<QueryClientProvider client={new QueryClient()}><StockPicker value="" onChange={() => undefined} /></QueryClientProvider>);
    expect(html).toContain('role="combobox"'); expect(html).toContain('aria-label="Filters"'); expect(html).toContain("sf-host");
  });
  it("palette: Sector and Market cap controls under the tabs, with the unfiltered footer count", () => {
    const html = renderToStaticMarkup(<QueryClientProvider client={new QueryClient()}><StaticRouter location="/"><SearchOverlay open onClose={() => undefined} /></StaticRouter></QueryClientProvider>);
    const t = text(html);
    expect(html.indexOf("gs-tabs")).toBeLessThan(html.indexOf("sf-bar"));
    expect(t).toContain("Sector All"); expect(t).toContain("Market cap All"); expect(t).toContain("3 listed companies");
    for (const bad of [/\bbuy\b/i, /\bsell\b/i, /\bhold\b/i, /target price/i]) expect(t).not.toMatch(bad);
  });
});
