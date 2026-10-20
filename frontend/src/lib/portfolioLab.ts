// Pure engine behind the Portfolio lab: what-if swaps, gaps, stress view and the printable report.
// Everything is computed from the scores already loaded in the browser. Nothing is stored and no history is invented.
import type { Row } from "./screener";

export type Holding = { symbol: string; name?: string | null; row?: Row };
export type PillarKey = "pillar_quality" | "pillar_growth" | "pillar_profitability" | "pillar_balance" | "pillar_technical";
export const PILLAR_LIST: [PillarKey, string][] = [["pillar_quality", "Quality"], ["pillar_growth", "Growth"], ["pillar_profitability", "Profitability"], ["pillar_balance", "Balance sheet"], ["pillar_technical", "Technical"]];
export const BAND_NAMES: Record<string, string> = { strong: "Strong", healthy: "Healthy", mixed: "Mixed", watch: "Watch", none: "Not scored yet" };

export const MIN_GAIN = 8;          // a suggestion must beat the holding by at least this many points
export const SOUND = 62;            // Balance and Quality at or above this count as "resilient"
export const WEAK_PILLAR = 50;      // a portfolio pillar average below this is called out as a gap
export const NOT_LOADED = "Not yet loaded";

const fin = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
export const scoreOf = (h: Holding): number | null => (fin(h.row?.overall) ? (h.row!.overall as number) : null);
export const bandOf = (s: number | null | undefined): "strong" | "healthy" | "mixed" | "watch" | "none" =>
  !fin(s) ? "none" : s >= 78 ? "strong" : s >= 62 ? "healthy" : s >= 45 ? "mixed" : "watch";

/** Market-cap tier (₹ Cr): 0 small, 1 mid, 2 large, 3 very large. -1 when unknown. */
export function capTier(mc: number | null | undefined): number {
  if (!fin(mc) || mc <= 0) return -1;
  return mc < 5_000 ? 0 : mc < 20_000 ? 1 : mc < 100_000 ? 2 : 3;
}

/** Remove duplicate symbols, keep first. */
export function uniqueHoldings(lines: Holding[]): Holding[] {
  const seen = new Set<string>();
  return (lines || []).filter((l) => l && l.symbol && !seen.has(l.symbol) && (seen.add(l.symbol), true));
}

export type Stats = {
  count: number; scored: number; unscored: number;
  avg: number | null;        // raw average of overall
  score: number | null;      // Math.round(avg)
  band: Record<string, number>;   // % of all holdings, keys strong/healthy/mixed/watch/none
  sectors: { name: string; pct: number }[]; // % of all holdings, largest first
  pillars: { key: PillarKey; label: string; avg: number | null }[];
};

export function statsOf(items: Holding[]): Stats {
  const list = uniqueHoldings(items), n = list.length;
  const sc = list.filter((h) => scoreOf(h) != null);
  const avg = sc.length ? sc.reduce((a, h) => a + (scoreOf(h) as number), 0) / sc.length : null;
  const band: Record<string, number> = { strong: 0, healthy: 0, mixed: 0, watch: 0, none: 0 };
  const sec = new Map<string, number>();
  list.forEach((h) => {
    band[bandOf(scoreOf(h))] += n ? 100 / n : 0;
    const k = h.row?.sector?.trim() || NOT_LOADED;
    sec.set(k, (sec.get(k) || 0) + (n ? 100 / n : 0));
  });
  const pillars = PILLAR_LIST.map(([key, label]) => {
    const v = sc.map((h) => h.row![key]).filter(fin);
    return { key, label, avg: v.length ? v.reduce((a, b) => a + b, 0) / v.length : null };
  });
  return { count: n, scored: sc.length, unscored: n - sc.length, avg, score: avg == null ? null : Math.round(avg), band,
    sectors: [...sec.entries()].map(([name, pct]) => ({ name, pct })).sort((a, b) => b.pct - a.pct || a.name.localeCompare(b.name)), pillars };
}

/* ------------------------------------------------------------------ what-if swaps */


/* ------------------------------------------------------------------ gaps */

export type Gap = { id: string; kind: "sector" | "pillar"; label: string; reason: string; pick: Row | null };
const GROUPS: { id: string; label: string; test: RegExp; why: string }[] = [
  { id: "financials", label: "Financials", test: /financ|bank|insur|nbfc/i, why: "No bank, lender or insurer in this list." },
  { id: "defensive", label: "Defensive sectors", test: /fmcg|fast moving|staple|health|pharma|utilit|power|telecom|food/i, why: "Nothing from everyday-demand sectors such as consumer staples, healthcare, utilities or telecom." },
  { id: "technology", label: "Technology", test: /information tech|software|\bit\b|technolog/i, why: "No technology or software company in this list." },
  { id: "industrials", label: "Industrials", test: /industr|capital goods|construction|infra|engineering/i, why: "No industrial, engineering or infrastructure company in this list." },
];
const better = (a: Row, b: Row) => (b.overall as number) - (a.overall as number) || (b.pillar_balance ?? 0) - (a.pillar_balance ?? 0) || a.symbol.localeCompare(b.symbol);

export function findGaps(lines: Holding[], universe: Row[]): Gap[] {
  const list = uniqueHoldings(lines), st = statsOf(list);
  if (!st.scored) return [];
  const held = new Set(list.map((h) => h.symbol));
  const pool = (universe || []).filter((r) => r && fin(r.overall) && !held.has(r.symbol));
  const secs = list.map((h) => h.row?.sector || "");
  const out: Gap[] = [];
  GROUPS.forEach((g) => {
    if (secs.some((s) => g.test.test(s))) return;
    const pick = pool.filter((r) => g.test.test(r.sector || "")).sort(better)[0] || null;
    if (pick || (universe || []).some((r) => g.test.test(r?.sector || ""))) out.push({ id: g.id, kind: "sector", label: g.label, reason: g.why, pick });
  });
  st.pillars.forEach((p) => {
    if (p.avg == null || p.avg >= WEAK_PILLAR) return;
    const pick = pool.filter((r) => fin(r[p.key]) && (r.overall as number) >= 62).sort((a, b) => (b[p.key] as number) - (a[p.key] as number) || a.symbol.localeCompare(b.symbol))[0] || null;
    out.push({ id: p.key, kind: "pillar", label: `${p.label} pillar`, reason: `Average ${p.label} score is ${Math.round(p.avg)}, which is on the low side.`, pick });
  });
  return out;
}

/* ------------------------------------------------------------------ stress view */

export type Stress = { eligible: boolean; need: number; removed: Row[]; removedSymbols: string[]; before: number | null; after: number | null; delta: number | null };
/** Remove the weakest 25% (rounded up) by Balance sheet score and re-average. Needs at least 4 holdings with a Balance score. */
export function stressView(lines: Holding[]): Stress {
  const withB = uniqueHoldings(lines).filter((h) => scoreOf(h) != null && fin(h.row?.pillar_balance));
  const need = 4;
  const before = statsOf(withB).score;
  if (withB.length < need) return { eligible: false, need, removed: [], removedSymbols: [], before, after: null, delta: null };
  const k = Math.ceil(withB.length * 0.25);
  const sorted = [...withB].sort((a, b) => (a.row!.pillar_balance as number) - (b.row!.pillar_balance as number) || a.symbol.localeCompare(b.symbol));
  const gone = sorted.slice(0, k), keep = new Set(sorted.slice(k).map((h) => h.symbol));
  const after = statsOf(withB.filter((h) => keep.has(h.symbol))).score;
  return { eligible: true, need, removed: gone.map((h) => h.row!), removedSymbols: gone.map((h) => h.symbol), before, after, delta: before != null && after != null ? after - before : null };
}

export type Resilience = { pct: number | null; sound: number; total: number; label: string };
/** Share of scored holdings with Balance >= 62 and Quality >= 62. */
export function resilience(lines: Holding[]): Resilience {
  const sc = uniqueHoldings(lines).filter((h) => scoreOf(h) != null);
  if (!sc.length) return { pct: null, sound: 0, total: 0, label: "Not enough scores yet" };
  const sound = sc.filter((h) => (h.row!.pillar_balance ?? -1) >= SOUND && (h.row!.pillar_quality ?? -1) >= SOUND).length;
  const pct = Math.round((sound / sc.length) * 100);
  return { pct, sound, total: sc.length, label: pct >= 70 ? "Most holdings have a sturdy balance sheet and quality" : pct >= 40 ? "About half the holdings are sturdy on both" : "Few holdings are sturdy on both" };
}

/* ------------------------------------------------------------------ report */

export const DISCLAIMER = "Information only, not investment advice";
const esc = (v: unknown) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] as string));
const num = (v: number | null | undefined) => (fin(v) ? String(Math.round(v)) : "—");

export function buildReportHtml(lines: Holding[], when: Date = new Date()): string {
  const list = uniqueHoldings(lines), st = statsOf(list), rs = resilience(list);
  const date = Number.isNaN(when.getTime()) ? "" : when.toISOString().slice(0, 10);
  const sorted = [...list].sort((a, b) => (scoreOf(b) ?? -1) - (scoreOf(a) ?? -1) || a.symbol.localeCompare(b.symbol));
  const rows = sorted.map((h) => `<tr><td><b>${esc(h.symbol)}</b><br><small>${esc(h.name || "")}</small></td><td>${esc(h.row?.sector || "—")}</td><td class="n">${num(scoreOf(h))}</td><td>${esc(BAND_NAMES[bandOf(scoreOf(h))])}</td>${PILLAR_LIST.map(([k]) => `<td class="n">${num(h.row?.[k])}</td>`).join("")}</tr>`).join("");
  const bands = (["strong", "healthy", "mixed", "watch", "none"] as const).filter((b) => st.band[b] > 0).map((b) => `<li>${esc(BAND_NAMES[b])}: ${Math.round(st.band[b])}%</li>`).join("");
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>FinLit portfolio report</title>
<style>body{font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;color:#14130f;margin:32px auto;max-width:900px;padding:0 16px}h1{font-size:24px;margin:0}h2{font-size:15px;margin:26px 0 8px;border-bottom:1px solid #cfcbbe;padding-bottom:4px}
.big{font-size:44px;font-weight:700}table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid #e7e5de}th{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#46443c}td.n,th.n{text-align:right}small{color:#6a675c}ul{margin:0;padding-left:18px;columns:2}.d{margin-top:28px;padding:10px 12px;border:1px solid #cfcbbe;border-radius:6px;font-size:12.5px}@media print{body{margin:0}}</style></head><body>
<h1>FinLit portfolio report</h1><small>${esc(date)} · ${st.count} ${st.count === 1 ? "share" : "shares"}, equal weight</small>
<h2>Portfolio FinLit score</h2><div class="big">${num(st.score)}<small> / 100</small></div><small>Average of ${st.scored} scored ${st.scored === 1 ? "share" : "shares"}${st.unscored ? `; ${st.unscored} not scored yet` : ""}.${rs.pct != null ? ` Share with Balance sheet and Quality both at ${SOUND} or more: ${rs.pct}%.` : ""}</small>
<h2>Average by pillar</h2><table><tbody>${st.pillars.map((p) => `<tr><td>${esc(p.label)}</td><td class="n">${num(p.avg)}</td></tr>`).join("")}</tbody></table>
<h2>FinLit bands</h2><ul>${bands || "<li>—</li>"}</ul>
<h2>Sector split</h2><ul>${st.sectors.map((s) => `<li>${esc(s.name)}: ${Math.round(s.pct)}%</li>`).join("") || "<li>—</li>"}</ul>
<h2>Each holding</h2><table><thead><tr><th>Share</th><th>Sector</th><th class="n">Score</th><th>Band</th>${PILLAR_LIST.map(([, l]) => `<th class="n">${esc(l)}</th>`).join("")}</tr></thead><tbody>${rows || `<tr><td colspan="9">No shares added.</td></tr>`}</tbody></table>
<div class="d"><b>${DISCLAIMER}.</b> Scores describe company data and are not a recommendation to buy, sell or hold anything. Weights are equal and no quantities or prices are used.</div></body></html>`;
}
