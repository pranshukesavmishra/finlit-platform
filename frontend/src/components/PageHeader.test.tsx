// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PageHeader } from "./PageHeader";
import { PH_ART_KINDS, PageArt } from "./PageHeaderArt";
import { TitleCard } from "./screener/PageParts";
import { SECTIONS, MORE, PRICING } from "../lib/nav";
import { realValue, resolveLink, resolveLinks } from "../lib/pageHeader";

afterEach(cleanup);
const wrap = (ui: React.ReactElement, at = "/screener") => render(<MemoryRouter initialEntries={[at]}>{ui}</MemoryRouter>);

describe("PageHeader", () => {
  it("has one h1 inside a labelled region, with the plan badge and the description", () => {
    wrap(<PageHeader plan="gold" title="Stock screener" description={<>Screen <b>5,816</b> companies.</>} />);
    const region = screen.getByRole("region", { name: "Stock screener" });
    expect(within(region).getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(region.querySelector(".ph-plan")?.textContent).toBe("Gold");
    expect(region.querySelector(".ph-desc b")?.textContent).toBe("5,816");
  });
  it("names every plan, and shows no badge when the page has none", () => {
    const names: [Parameters<typeof PageHeader>[0]["plan"], string][] = [["free", "Free"], ["basic", "Free"], ["silver", "Silver"], ["gold", "Gold"]];
    for (const [plan, text] of names) { const { container, unmount } = wrap(<PageHeader plan={plan} title="T" />); expect(container.querySelector(".ph-plan")?.textContent).toBe(text); unmount(); }
    const { container } = wrap(<PageHeader title="T" />);
    expect(container.querySelector(".ph-plan")).toBeNull();
  });
  it("draws no stat tiles (the props are accepted so no page has to change)", () => {
    const { container } = wrap(<PageHeader title="T" stats={[
      { icon: "building", value: "5,816", label: "Companies" }, { icon: "table", value: null, label: "Filters" }, { icon: "layers", value: NaN, label: "Sectors" },
      { icon: "layers", value: "—", label: "Dash" }, { icon: "layers", value: undefined, label: "Missing" }, { icon: "layers", value: "", label: "Empty" }, { icon: "layers", value: 0, label: "Zero" }, { icon: "layers", value: 7, label: "Fourth" },
    ]} />);
    expect(container.querySelector(".ph-stat")).toBeNull();      // the figure tiles are no longer drawn on any page
  });
  it("shows no stats list at all when every value is missing", () => {
    const { container } = wrap(<PageHeader title="T" stats={[{ icon: "building", value: null, label: "Companies" }]} />);
    expect(container.querySelector(".ph-stats")).toBeNull();
    expect(container.querySelector(".ph-solo")).not.toBeNull();
  });
  it("takes quick-link names and addresses from the site map, and drops links the site does not have", () => {
    wrap(<PageHeader title="T" links={["/score-screener", { to: "/advanced-score-screener", primary: true }, "/query-builder", "/no-such-page", "/dcf", "/news"]} />);
    const nav = screen.getByRole("navigation", { name: "Related pages" });
    const links = within(nav).getAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["/score-screener", "/advanced-score-screener", "/query-builder", "/dcf"]);   // 4 at most, the unknown one gone
    expect(links.map((a) => a.textContent)).toEqual(["Basic Screener→", "Advanced Screener→", "Query Builder→", "DCF Calculator→"]);
    expect(links[1].className).toContain("primary");
    expect(links[0].className).not.toContain("primary");
  });
  it("renders the learn-more link in each of its forms", () => {
    const fn = vi.fn();
    const a = wrap(<PageHeader title="T" learn={{ to: "/methodology/mf-score", label: "How it works" }} />);
    expect(screen.getByRole("link", { name: "How it works" }).getAttribute("href")).toBe("/methodology/mf-score"); a.unmount();
    const b = wrap(<PageHeader title="T" learn={{ onClick: fn }} />);
    screen.getByRole("button", { name: "Learn more" }).click(); expect(fn).toHaveBeenCalledTimes(1); b.unmount();
    const c = wrap(<PageHeader title="T" learn />, "/screener");   // /screener has a question set: scrolls to #faq
    expect(screen.getByRole("link", { name: "Learn more" }).getAttribute("href")).toBe("#faq"); c.unmount();
    const d = wrap(<PageHeader title="T" learn />, "/no-such-page");
    expect(d.container.querySelector(".ph-learn")).toBeNull();
  });
  it("draws no illustration and keeps the header usable without a router", () => {
    const { container } = render(<PageHeader plan="silver" title="T" art="chart" links={["/screener"]} />);
    expect(container.querySelector("svg.ph-art")).toBeNull();      // the line illustration is no longer drawn on any page
    expect(container.querySelector("a.ph-lk")?.getAttribute("href")).toBe("/screener");
  });
  it("keeps back links, notes and extra actions, and wraps in the page container on request", () => {
    const { container } = wrap(<PageHeader wrap title="T" back={<a href="/x">Back</a>} meta="Updated today" actions={<button type="button">Act</button>}><p>Tabs here</p></PageHeader>);
    expect(container.querySelector(".wrap.ph-wrap .ph")).not.toBeNull();
    expect(screen.getByText("Back")).toBeTruthy(); expect(screen.getByText("Updated today")).toBeTruthy(); expect(screen.getByRole("button", { name: "Act" })).toBeTruthy(); expect(screen.getByText("Tabs here")).toBeTruthy();
  });
  it("is what the screeners' TitleCard now renders, with its props still working", () => {
    const fn = vi.fn();
    const { container } = wrap(<TitleCard tier="gold" title="Fund score screener" sub="Every fund." onLearn={fn} learnLabel="Read" stats={[{ icon: "layers", value: "12", label: "Categories" }]} />);
    expect(container.querySelector(".ph h1")?.textContent).toBe("Fund score screener");
    expect(container.querySelector(".ph-plan")?.textContent).toBe("Gold");
    screen.getByRole("button", { name: "Read" }).click(); expect(fn).toHaveBeenCalled();
    expect(container.querySelector(".ph-stat")).toBeNull();
  });
});

describe("page header helpers", () => {
  it("ships twelve distinct line illustrations that draw with currentColor", () => {
    expect(PH_ART_KINDS).toHaveLength(12);
    const shapes = new Set<string>();
    for (const k of PH_ART_KINDS) {
      const { container, unmount } = render(<PageArt kind={k} />);
      const svg = container.querySelector("svg")!;
      expect(svg.getAttribute("stroke")).toBe("currentColor"); expect(svg.getAttribute("fill")).toBe("none"); expect(svg.getAttribute("aria-hidden")).toBe("true");
      expect(svg.innerHTML).not.toMatch(/#[0-9a-f]{3,6}\b/i);   // no hard-coded colours: theme tokens only
      shapes.add(svg.innerHTML); unmount();
    }
    expect(shapes.size).toBe(12);
  });
  it("resolves links only to real pages", () => {
    const all = [...SECTIONS, MORE].flatMap((s) => s.groups.flatMap((g) => g.items)).concat(PRICING);
    for (const it of all) expect(resolveLink(it.to), it.to).not.toBeNull();
    expect(resolveLink("/nope")).toBeNull();
    expect(resolveLink("/stocks/ABC")).toBeNull();   // a company page needs a label from the caller
    expect(resolveLink({ to: "/stocks/ABC", label: "Company report" })?.label).toBe("Company report");
    expect(resolveLinks(["/screener", "/macro", "/ipo", "/news", "/dcf"])).toHaveLength(4);
  });
  it("tells real values from placeholders", () => {
    for (const v of ["1", 0, "₹ 5 cr", "12%"]) expect(realValue(v)).toBe(true);
    for (const v of [null, undefined, "", " ", NaN, Infinity, "—", "-", "NaN", "undefined", "n/a"]) expect(realValue(v)).toBe(false);
  });
});
