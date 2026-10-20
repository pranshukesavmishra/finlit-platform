// Pure engine behind the "Portfolio insights" panel. Holdings are treated as EQUAL-WEIGHT (no quantities are held).
// Everything here is descriptive and informational; it never recommends buying or selling.
import type { Row } from "./screener";

export type InsightLine = { symbol: string; name: string; row?: Row };
export type PillarKey = "pillar_quality" | "pillar_growth" | "pillar_profitability" | "pillar_balance" | "pillar_technical";
export const PILLAR_KEYS: { key: PillarKey; label: string; short: string }[] = [
  { key: "pillar_quality", label: "Quality", short: "Quality" },
  { key: "pillar_growth", label: "Growth", short: "Growth" },
  { key: "pillar_profitability", label: "Profitability", short: "Profit." },
  { key: "pillar_balance", label: "Balance sheet", short: "Balance" },
  { key: "pillar_technical", label: "Technical (momentum)", short: "Technical" },
];

export type Band = "strong" | "healthy" | "mixed" | "watch";
export const bandOf = (v: number): Band => (v >= 78 ? "strong" : v >= 62 ? "healthy" : v >= 45 ? "mixed" : "watch");
export const BAND_NAME: Record<Band, string> = { strong: "Strong", healthy: "Healthy", mixed: "Mixed", watch: "Watch" };

const fin = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const mean = (a: number[]) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : null);
const r0 = (v: number) => Math.round(v);
const share = (k: number, n: number) => (n > 0 ? (k / n) * 100 : 0);
const pctTxt = (v: number) => `${r0(v)}%`;
const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

export type Scored = { symbol: string; name: string; score: number; band: Band; sector: string; cap: number | null; pillars: Record<PillarKey, number | null> };

export type SectorShare = { sector: string; count: number; share: number };
export type PillarAvg = { key: PillarKey; label: string; short: string; avg: number | null };
export type ShareNote = { symbol: string; name: string; score: number; band: Band; pillarLabel: string | null; pillarValue: number | null; note: string };
export type Priority = { symbol: string; name: string; title: string; why: string; severity: number };

export type Insights = {
  total: number; scored: number; preparing: number;
  empty: boolean; enough: boolean; // enough: at least 2 scored holdings, so comparisons are meaningful
  health: { score: number; band: Band; reading: string } | null;
  diversification: {
    sectors: SectorShare[]; sectorCount: number; top: SectorShare | null; unknownSector: number;
    hhi: number; label: "Concentrated" | "Moderate" | "Well spread"; flags: string[];
    caps: { large: number; mid: number; small: number; unknown: number; line: string };
    summary: string;
  } | null;
  strongest: ShareNote[]; weakest: ShareNote[];
  pillars: PillarAvg[]; strengthPillar: PillarAvg | null; weakPillar: PillarAvg | null; pillarSentence: string;
  risk: { watchCount: number; watchShare: number; weakBalanceCount: number; weakBalanceShare: number; momentumKnown: number; momentumPositive: number; momentumShare: number; lines: string[] } | null;
  priorities: Priority[];
  note: string; // honest framing, incl. how many are still being prepared
};

const WEAK_BALANCE = 45; // pillar below this reads as a stretched balance sheet (debt / liquidity)
const MOM_OK = 50;       // technical pillar at/above this counts as positive momentum

function toScored(l: InsightLine): Scored | null {
  const r = l.row;
  if (!r || !fin(r.overall)) return null;
  const p = (k: PillarKey) => (fin(r[k]) ? (r[k] as number) : null);
  return {
    symbol: l.symbol, name: (l.name || r.name || l.symbol).trim() || l.symbol, score: r.overall, band: bandOf(r.overall),
    sector: (r.sector || "").trim() || "Sector not available", cap: fin(r.market_cap) ? r.market_cap : null,
    pillars: { pillar_quality: p("pillar_quality"), pillar_growth: p("pillar_growth"), pillar_profitability: p("pillar_profitability"), pillar_balance: p("pillar_balance"), pillar_technical: p("pillar_technical") },
  };
}

const labelOf = (k: PillarKey) => PILLAR_KEYS.find((p) => p.key === k)!.label;

/** The pillar that is highest (lead) or lowest (drag) for one holding; null when it has no pillar data. */
function extreme(s: Scored, dir: "hi" | "lo"): { key: PillarKey; v: number } | null {
  let best: { key: PillarKey; v: number } | null = null;
  for (const { key } of PILLAR_KEYS) {
    const v = s.pillars[key];
    if (v == null) continue;
    if (!best || (dir === "hi" ? v > best.v : v < best.v)) best = { key, v };
  }
  return best;
}

function shareNote(s: Scored, dir: "hi" | "lo"): ShareNote {
  const e = extreme(s, dir);
  const note = e
    ? dir === "hi" ? `Led by ${labelOf(e.key)} (${r0(e.v)}).` : `Held back by ${labelOf(e.key)} (${r0(e.v)}).`
    : "Pillar detail is not available yet.";
  return { symbol: s.symbol, name: s.name, score: s.score, band: s.band, pillarLabel: e ? labelOf(e.key) : null, pillarValue: e ? r0(e.v) : null, note };
}

function healthReading(band: Band, n: number): string {
  const who = n === 1 ? "this holding" : "the holdings together";
  switch (band) {
    case "strong": return `On average ${who} score Strong on the FinLit model: solid across most measures.`;
    case "healthy": return `On average ${who} score Healthy: generally sound, with some room to improve.`;
    case "mixed": return `On average ${who} score Mixed: some strengths alongside real weak spots.`;
    default: return `On average ${who} score in the Watch range: several measures are weak and deserve a closer read.`;
  }
}

export function portfolioInsights(lines: InsightLine[]): Insights {
  const seen = new Set<string>();
  const uniq = (lines || []).filter((l) => l && l.symbol && !seen.has(l.symbol) && !!seen.add(l.symbol));
  const total = uniq.length;
  const sc = uniq.map(toScored).filter((s): s is Scored => s !== null);
  const scored = sc.length, preparing = total - scored;
  const prepNote = preparing > 0 ? `${plural(preparing, "holding is", "holdings are")} still being prepared and left out for now.` : "";
  const base = {
    total, scored, preparing, empty: total === 0, enough: scored >= 2,
    health: null, diversification: null, strongest: [], weakest: [], pillars: PILLAR_KEYS.map((p) => ({ ...p, avg: null })) as PillarAvg[],
    strengthPillar: null, weakPillar: null, pillarSentence: "", risk: null, priorities: [], note: "",
  } satisfies Insights;
  if (total === 0) return { ...base, note: "Add the shares you hold to see how the portfolio is balanced." };
  if (scored === 0) return { ...base, pillarSentence: "Pillar averages appear once the scores are ready.", note: prepNote || "Scores are being prepared." };

  const avg = mean(sc.map((s) => s.score)) as number;
  const hBand = bandOf(avg);
  const health = { score: r0(avg), band: hBand, reading: healthReading(hBand, scored) };

  // --- diversification (equal weight)
  const bySector = new Map<string, number>();
  sc.forEach((s) => bySector.set(s.sector, (bySector.get(s.sector) || 0) + 1));
  const sectors: SectorShare[] = [...bySector.entries()].map(([sector, count]) => ({ sector, count, share: share(count, scored) }))
    .sort((a, b) => b.count - a.count || a.sector.localeCompare(b.sector));
  const unknownSector = bySector.get("Sector not available") || 0;
  const named = sectors.filter((s) => s.sector !== "Sector not available");
  const sectorCount = named.length;
  const top = named[0] || null;
  const hhi = Math.round(sectors.reduce((a, s) => a + (s.share / 100) ** 2, 0) * 10000);
  const label = hhi >= 2500 ? "Concentrated" : hhi >= 1500 ? "Moderate" : "Well spread";
  const flags: string[] = [];
  if (scored >= 2 && top && top.share > 40) flags.push(`${top.sector} makes up ${pctTxt(top.share)} of your holdings, more than 40% in one sector.`);
  if (scored >= 2 && sectorCount < 5) flags.push(`Your holdings cover ${plural(sectorCount, "sector", "sectors")}, fewer than 5.`);
  let large = 0, mid = 0, small = 0, unk = 0;
  sc.forEach((s) => { if (s.cap == null) unk++; else if (s.cap >= 100000) large++; else if (s.cap >= 30000) mid++; else small++; });
  const capParts = [large && `${pctTxt(share(large, scored))} large`, mid && `${pctTxt(share(mid, scored))} mid`, small && `${pctTxt(share(small, scored))} small`, unk && `${pctTxt(share(unk, scored))} size unknown`].filter(Boolean);
  const caps = { large, mid, small, unknown: unk, line: capParts.length ? `Company size: ${capParts.join(", ")}.` : "Company size is not available." };
  const summary = scored === 1 ? "With one holding, everything rides on a single company, so spread cannot be assessed."
    : `Equal-weighted, the portfolio reads as ${label.toLowerCase()} across ${plural(sectorCount, "sector", "sectors")}${top ? `; the largest is ${top.sector} at ${pctTxt(top.share)}` : ""}.`;

  // --- strongest / weakest
  const ranked = [...sc].sort((a, b) => b.score - a.score || a.symbol.localeCompare(b.symbol));
  const k = Math.min(3, Math.floor(scored / 2) || (scored === 1 ? 1 : 0));
  const strongest = (scored === 1 ? ranked : ranked.slice(0, k)).map((s) => shareNote(s, "hi"));
  const weakest = scored === 1 ? [] : ranked.slice(-k).reverse().map((s) => shareNote(s, "lo"));

  // --- pillars
  const pillars: PillarAvg[] = PILLAR_KEYS.map((p) => ({ ...p, avg: mean(sc.map((s) => s.pillars[p.key]).filter(fin)) }));
  const have = pillars.filter((p) => p.avg != null);
  let strengthPillar: PillarAvg | null = null, weakPillar: PillarAvg | null = null, pillarSentence = "Pillar detail is not available yet.";
  if (have.length) {
    strengthPillar = have.reduce((a, b) => ((b.avg as number) > (a.avg as number) ? b : a));
    weakPillar = have.reduce((a, b) => ((b.avg as number) < (a.avg as number) ? b : a));
    if (have.length === 1 || strengthPillar.key === weakPillar.key || (strengthPillar.avg as number) - (weakPillar.avg as number) < 3) {
      pillarSentence = `The pillars are fairly even, averaging about ${r0(mean(have.map((p) => p.avg as number)) as number)}.`;
      if (have.length === 1) { weakPillar = null; }
    } else {
      pillarSentence = `${strengthPillar.label} is the portfolio's strength (average ${r0(strengthPillar.avg as number)}); ${weakPillar.label} is its weakest link (average ${r0(weakPillar.avg as number)}).`;
    }
  }

  // --- risk
  const watchCount = sc.filter((s) => s.band === "watch").length;
  const bal = sc.map((s) => s.pillars.pillar_balance).filter(fin);
  const weakBalanceCount = bal.filter((v) => v < WEAK_BALANCE).length;
  const tech = sc.map((s) => s.pillars.pillar_technical).filter(fin);
  const momentumPositive = tech.filter((v) => v >= MOM_OK).length;
  const risk = {
    watchCount, watchShare: share(watchCount, scored),
    weakBalanceCount, weakBalanceShare: share(weakBalanceCount, bal.length),
    momentumKnown: tech.length, momentumPositive, momentumShare: share(momentumPositive, tech.length),
    lines: [
      watchCount ? `${plural(watchCount, "holding is", "holdings are")} in the Watch band (${pctTxt(share(watchCount, scored))}).` : "None of the holdings are in the Watch band.",
      bal.length ? (weakBalanceCount ? `${plural(weakBalanceCount, "holding has", "holdings have")} a weak Balance score, which points to heavier debt or thinner cover (${pctTxt(share(weakBalanceCount, bal.length))}).` : "No holding has a weak Balance score, so debt looks manageable across the board.") : "Balance sheet scores are not available yet.",
      tech.length ? `Momentum is positive for ${momentumPositive} of ${tech.length} (${pctTxt(share(momentumPositive, tech.length))}).` : "Momentum scores are not available yet.",
    ],
  };

  // --- what to look at first
  const pr: Priority[] = [];
  const add = (s: Scored, title: string, why: string, severity: number) => { pr.push({ symbol: s.symbol, name: s.name, title, why, severity }); };
  sc.forEach((s) => {
    const lo = extreme(s, "lo");
    if (s.band === "watch") add(s, `${s.symbol} scores in the Watch band`, `Score ${s.score}${lo ? `, held back by ${labelOf(lo.key)} (${r0(lo.v)})` : ""}. Worth reading its details.`, 100 - s.score + 50);
    const b = s.pillars.pillar_balance;
    if (b != null && b < WEAK_BALANCE && s.band !== "watch") add(s, `${s.symbol} has a weak balance sheet`, `Balance score ${r0(b)}, so debt or cover is worth checking.`, 90 - b);
    const t = s.pillars.pillar_technical;
    if (t != null && t < 30 && s.band !== "watch") add(s, `${s.symbol} has fading momentum`, `Technical score ${r0(t)}, so the price trend is weak.`, 60 - t);
  });
  if (top && scored >= 2 && top.share > 40) {
    const t = sc.filter((s) => s.sector === top.sector).sort((a, b) => a.score - b.score)[0];
    add(t, `${top.sector} is ${pctTxt(top.share)} of the portfolio`, `${t.symbol} is its lowest-scoring name here (${t.score}); a concentrated sector moves together.`, 45);
  }
  const seenSym = new Set<string>(); // one entry per symbol: keep the most severe
  const priorities = pr.sort((a, b) => b.severity - a.severity).filter((p) => !seenSym.has(p.symbol) && !!seenSym.add(p.symbol)).slice(0, 4);

  const note = [scored === 1 ? "Based on one scored holding." : `Based on ${scored} scored holdings, treated as equal-weight because quantities are not held.`, prepNote].filter(Boolean).join(" ");
  return {
    ...base, health, diversification: { sectors, sectorCount, top, unknownSector, hhi, label, flags, caps, summary },
    strongest, weakest, pillars, strengthPillar, weakPillar, pillarSentence, risk, priorities, note,
  };
}
