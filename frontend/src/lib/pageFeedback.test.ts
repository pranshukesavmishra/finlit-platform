import { describe, expect, it } from "vitest";
import { draftProblem, pageTag } from "./pageFeedback";
import { pageNameFor } from "./pageHeader";

const doc = (title: string, h1 = "") => ({ title, querySelector: (s: string) => (s === "h1" && h1 ? ({ textContent: h1 } as Element) : null) }) as unknown as Document;

describe("pageNameFor", () => {
  it("names pages the way the menus do, and company, fund and report pages by what they are", () => {
    expect(pageNameFor("/")).toBe("Home");
    expect(pageNameFor("/score-screener")).toBe("Basic score screener");
    expect(pageNameFor("/dcf")).toBe("DCF valuation calculator");
    expect(pageNameFor("/stocks/RELIANCE")).toBe("Company report");
    expect(pageNameFor("/stocks/RELIANCE/")).toBe("Company report");
    expect(pageNameFor("/prism/TCS")).toBe("Prism report");
    expect(pageNameFor("/funds/119551")).toBe("Fund page");
    expect(pageNameFor("/forum/c/RELIANCE")).toBe("Discussion forum");
    expect(pageNameFor("/no/such/page")).toBe("");
  });
});

describe("pageTag", () => {
  it("tags the address without query string or fragment, the page's name, the company symbol and the screen size", () => {
    const t = pageTag("/stocks/RELIANCE?tab=x#a", "gold", doc("Reliance Industries Ltd | FinLit", "Reliance Industries Ltd"), 1440);
    expect(t.page).toBe("/stocks/RELIANCE");
    expect(t.pageName).toBe("Company report");
    expect(t.context).toEqual({ symbol: "RELIANCE", title: "Reliance Industries Ltd", plan: "gold", screen: "desktop" });
  });
  it("falls back to the page's own heading or title for a page the site map does not know, and names the screen", () => {
    expect(pageTag("/brand-new", null, doc("Brand new tool | FinLit", "A new tool"), 390).pageName).toBe("A new tool");
    expect(pageTag("/brand-new", null, doc("Brand new tool | FinLit", ""), 390).pageName).toBe("Brand new tool");
    expect(pageTag("/brand-new", null, doc("", ""), 800).pageName).toBe("/brand-new");
    expect(pageTag("/dcf", null, doc("", ""), 800).context.screen).toBe("tablet");
    expect(pageTag("dcf//", null, null, 1200).page).toBe("/dcf");
  });
});

describe("draftProblem", () => {
  const base = { kind: "query" as const, message: "How is the Sector filter counted with Market cap?", rating: 0, email: "" };
  it("a visitor needs an email; a member does not", () => {
    expect(draftProblem(base, false)).toMatch(/email/);
    expect(draftProblem({ ...base, email: "a@b.co" }, false)).toBe("");
    expect(draftProblem(base, true)).toBe("");
  });
  it("a query needs a few words; feedback needs a rating or words", () => {
    expect(draftProblem({ ...base, message: "too short" }, true)).toMatch(/at least 10/);
    expect(draftProblem({ kind: "feedback", message: "", rating: 0, email: "" }, true)).toMatch(/rating or write/);
    expect(draftProblem({ kind: "feedback", message: "", rating: 4, email: "" }, true)).toBe("");
    expect(draftProblem({ kind: "feedback", message: "ok", rating: 0, email: "" }, true)).toMatch(/few more words/);
    expect(draftProblem({ ...base, message: "x".repeat(2001) }, true)).toMatch(/under 2000/);
  });
});
