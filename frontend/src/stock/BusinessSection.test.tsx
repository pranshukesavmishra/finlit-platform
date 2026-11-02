import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import type { Summary } from "../lib/api";
import { BusinessSection } from "./Sections2";

const mk = (profile: Record<string, unknown>, secondarySource?: Record<string, string>) =>
  ({ profile: { symbol: "SPICY", name: "Spicy Media Ltd", nse: "SPICY", bse: "540084", sector: "Media", industry: null, marketCapCr: 120, employees: null, website: null, ...profile },
     dataQuality: { secondarySource } } as unknown as Summary);
const html = (s: Summary) => renderToStaticMarkup(<MemoryRouter><BusinessSection s={s} /></MemoryRouter>);

describe("company overview", () => {
  it("links the company's NSE and BSE pages, as the exchanges publish them", () => {
    const out = html(mk({ description: "Makes films." }));
    expect(out).toContain('href="https://www.nseindia.com/get-quotes/equity?symbol=SPICY"');
    expect(out).toContain('href="https://www.bseindia.com/stock-share-price/x/x/540084/"');
    expect(out).not.toContain("Upstox");                       // the provider's own text: no second-source note
  });
  it("says where the description came from when the second source supplied it", () => {
    expect(html(mk({ description: "Makes films." }, { profile: "upstox" }))).toContain("Description from the company profile at Upstox");
  });
  it("says why there is no description instead of a blank, and never links a malformed code", () => {
    const out = html(mk({ description: null, nse: "bad code!", bse: "12" }, { profile: "upstox" }));
    expect(out).toContain("Neither of our data sources holds a description");
    expect(out).not.toContain("nseindia.com"); expect(out).not.toContain("bseindia.com"); expect(out).not.toContain("Description from");
  });
});
