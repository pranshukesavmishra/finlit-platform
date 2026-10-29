import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import fx from "../lib/__fixtures__/leadershipList.json";
import { groupSourceLine, sectorBench, type LeadPeer, type LeadershipOn } from "../lib/leadership";
import { PeerRanking, RankingStatus } from "./Leadership";

// The fixture is an /api/stocks/TCS/leadership answer for a stock on the indicator's IT list; its figures come from the team's package
// (docs/technicals/make_leadership_fixture.py). Nothing here is a real company's figure.
const LEAD = fx as unknown as LeadershipOn;
const strip = (h: string) => h.replace(/<[^>]+>/g, " ").replace(/&#x27;/g, "'").replace(/&amp;/g, "&").replace(/\s+/g, " ").replace(/ ([;,.])/g, "$1");
const ADVICE = /\b(buy|sell|hold|holds|holding|accumulate|target|entry|exit|stop|avoid|reduce)\w*\b/i;
const draw = (lead: LeadershipOn, extras: { symbol: string; name: string | null }[] = []) =>
  renderToStaticMarkup(<MemoryRouter><PeerRanking lead={lead} self="TCS" extras={extras} /></MemoryRouter>);
const many = (n: number): LeadPeer[] => Array.from({ length: n }, (_, i) => ({ symbol: i === 5 ? "TCS" : `P${i}`, name: i === 5 ? "Tata Consultancy Services" : `Peer ${i}`, rank: i + 1, label: i < 3 ? "leader" : i >= n - 3 ? "laggard" : "in_line", rawLabel: null, direction: null, rel13: 0.01, rel52: 0.1 - i * 0.005, rel52Market: 0.02, marketCap: null }));

describe("the ranking table on the stock page (the indicator's peer list)", () => {
  const h = draw(LEAD, [{ symbol: "PROVIDER", name: "Provider peer" }]), t = strip(h);
  it("header, status sentence and what the figures are measured against", () => {
    expect(t).toContain("How it ranks among 11 IT peers");
    expect(t).toContain("12-month return against Nifty IT");
    expect(t).toContain("6th of 11 IT peers · +14.0 pts vs Nifty IT · −6.8 pts vs Nifty 50 (12 months) · gaining over 3 months");
    expect(t).toContain("The 12-month and 3-month figures are against Nifty IT; the market figure is against Nifty 50.");
    expect(t).toContain("The top 4 of 11 can be Leaders (12-month figure above 0) and the bottom 4 Laggards (below 0); the rest are In line.");
  });
  it("this week's own answer is explained when it differs, and the label's age and run counts are shown", () => {
    expect(t).toContain("This week the ranking says In line. It becomes the label if the next weekly run says the same.");
    expect(t).toContain("This label has stood since 25 Aug 2025.");
    expect(t).toContain("Over the last 52 weeks (52 checks): Leader 52 · In line 0 · Laggard 0.");
    expect(t).toContain("Peer group: the IT list, as of 27 Oct 2026; 11 of the 14 names on the list are ranked.");
    expect((h.match(/This week: In line/g) || []).length).toBe(1);                         // only the row whose published label differs from its own answer
  });
  it("columns, rows with the status chip and the arrow, and the companies that are not ranked with their reasons", () => {
    for (const c of ["#", "Company", "Status", "vs sector, 12M", "vs sector, 3M", "vs market, 12M"]) expect(t).toContain(c);
    expect(h).toContain("ld-chip leader"); expect(h).toContain("ld-chip laggard"); expect(h).toContain("ld-chip in_line");
    expect(t).toContain("Not ranked this week (3)");
    for (const w of ["Oracle Financial Services Software", "Too thinly traded", "Hexaware Technologies", "No price history stored here yet", "Birlasoft", "Under a year of prices"]) expect(t).toContain(w);
    expect(t).not.toContain("Provider peer");                                              // on the indicator's list the data provider's peers are not mixed in
  });
  it("no advice word anywhere on it", () => { expect(h).not.toMatch(ADVICE); expect(h).not.toMatch(/<(span|p|li)\b[^>]*\baria-label=/); });
});

describe("older answers and other kinds of group", () => {
  it("an answer from before the lists (no source, no counts, no not-ranked list) still renders, with the provider's peers added as before", () => {
    const old = JSON.parse(JSON.stringify(LEAD)) as Record<string, unknown>;
    delete old.notRanked; delete old.runs52;
    (old.peerGroup as Record<string, unknown>) = { id: "it-services", name: "IT services", short: "IT services", kind: "industry", ranked: 11 };
    (old.display as Record<string, unknown>).pending = undefined;
    for (const p of old.peers as Record<string, unknown>[]) delete p.rawLabel;
    const h = draw(old as unknown as LeadershipOn, [{ symbol: "PROVIDER", name: "Provider peer" }]), t = strip(h);
    expect(t).toContain("How it ranks among 11 IT services peers");
    expect(t).toContain("Provider peer"); expect(t).toContain("Not enough history");
    expect(t).toContain("Peer group: companies in the same industry (IT services), 11 ranked.");
    expect(t).not.toContain("Not ranked this week"); expect(t).not.toContain("Over the last 52 weeks"); expect(t).not.toContain("This week:");
    expect(h).not.toMatch(ADVICE);
  });
  it("no sector index: says the peers' average stands in, and 'Show all N companies' opens a long table", () => {
    const lead = { ...LEAD, benchmarks: { sector: { code: null, name: "peer average", kind: "peer_average", ret52: null }, market: LEAD.benchmarks.market }, peers: many(30), peerGroup: { ...LEAD.peerGroup, ranked: 30, listed: 30, leaderSlots: 9 } } as unknown as LeadershipOn;
    const t = strip(draw(lead));
    expect(t).toContain("12-month return against the average of its ranked peers");
    expect(t).toContain("against the average of its ranked peers, because there is no matching sector index");
    expect(t).toContain("Show all 30 companies");
    expect(t).toContain("Peer group: the IT list, as of 27 Oct 2026; all 30 names on the list are ranked.");
  });
  it("words for the benchmark and the source line", () => {
    expect(sectorBench(LEAD)).toBe("Nifty IT");
    expect(groupSourceLine({ peerGroup: { ...LEAD.peerGroup, source: "industry", kind: "sector", name: "Finance", ranked: 20 } })).toBe("Peer group: companies in the same sector (Finance), 20 ranked.");
  });
  it("the status block alone", () => { expect(strip(renderToStaticMarkup(<MemoryRouter><RankingStatus lead={LEAD} /></MemoryRouter>))).toContain("Leader 6th of 11 IT peers"); });
});
