import type { Financials, Ratios, Summary, Table } from "../lib/api";
import { capSize } from "../lib/format";

export const PILLAR_COLOR: Record<string, string> = { quality: "--p-quality", growth: "--p-growth", profitability: "--p-profit", balance: "--p-balance", technical: "--p-tech" };
export const PILLAR_ICON: Record<string, string> = { quality: "quality", growth: "growth", profitability: "profit", balance: "balance", technical: "tech" };

export const metric = (s: Summary, key: string) => s.keyMetrics.find((m) => m.key === key);
export const ratio = (r: Ratios | undefined, key: string) => r?.latest[key];

export function yoy(series: (number | null)[]): number | null {
  const v = series.filter((x): x is number => x != null);
  if (v.length < 2 || v[v.length - 2] <= 0 || v[v.length - 1] <= 0) return null;
  return (v[v.length - 1] / v[v.length - 2] - 1) * 100;
}

export function finTiles(f: Financials) {
  const pl = f.yearly.pl, cf = f.yearly.cf, fy = pl.periods[pl.periods.length - 1];
  const rev = pl.rows.revenue || [], np = pl.rows.net_profit || [], op = cf.rows.operating || [];
  const margin = rev.map((r, i) => (r && np[i] != null ? ((np[i] as number) / r) * 100 : null));
  const last = <T,>(a: T[]) => a[a.length - 1];
  return [
    { k: "Revenue", fy, value: last(rev), unit: "cr" as const, delta: yoy(rev), series: rev, color: "--p-growth", icon: "rupee", suffix: "%" },
    { k: "Net profit", fy, value: last(np), unit: "cr" as const, delta: yoy(np), series: np, color: "--p-quality", icon: "growth", suffix: "%" },
    { k: "Operating cash", fy: cf.periods[cf.periods.length - 1], value: last(op), unit: "cr" as const, delta: yoy(op), series: op, color: "--p-balance", icon: "wallet", suffix: "%" },
    { k: "Net margin", fy, value: last(margin), unit: "pct" as const, delta: margin.length > 1 && last(margin) != null && margin[margin.length - 2] != null ? (last(margin) as number) - (margin[margin.length - 2] as number) : null, series: margin, color: "--p-profit", icon: "percent", suffix: " pts" },
  ];
}

export function buckets(s: Summary, r: Ratios | undefined, tech: { rsi14: number | null } | undefined) {
  const out: [string, string, string, string][] = [];
  const cap = capSize(s.profile.marketCapCr); if (cap) out.push(["cap", "Size", cap, "--p-growth"]);
  const pe = metric(s, "pe")?.value, pb = metric(s, "pb")?.value;
  if (pe != null) out.push(["tag", "Style", pe < 15 || (pb != null && pb < 1.5) ? "Value" : pe > 35 ? "Premium growth" : "Blend", "--p-quality"]);
  const dy = metric(s, "dividend_yield")?.value; if (dy != null) out.push(["coins", "Income", dy >= 3 ? "High dividend" : dy >= 1 ? "Moderate dividend" : "Low dividend", "--t-gold"]);
  if (s.profile.sector) out.push(["factory", "Theme", s.profile.sector, "--p-profit"]);
  if (s.profile.macroSector) out.push(["building", "Sector group", s.profile.macroSector, "--p-balance"]);
  const rsi = tech?.rsi14; if (rsi != null) out.push(["activity", "Momentum", rsi < 30 ? "Oversold" : rsi > 70 ? "Overbought" : "Neutral", "--p-tech"]);
  void r; return out;
}

export function ownershipSlices(latest: { key: string; value: number | null }[]) {
  const col: Record<string, string> = { promoters: "--c1", fii: "--c2", dii: "--c3", public: "--c4", government: "--c5", others: "--faint" };
  return latest.filter((l) => l.value != null).map((l) => ({ v: l.value as number, color: col[l.key] || "--faint" }));
}
export const OWN_COLOR: Record<string, string> = { promoters: "--c1", fii: "--c2", dii: "--c3", public: "--c4", government: "--c5", others: "--faint" };

export function csvOf(s: Summary, f: Financials | undefined, r: Ratios | undefined): string {
  const q = (v: unknown) => { let t = v == null ? "" : String(v); if (/^[=+\-@]/.test(t) && Number.isNaN(Number(t))) t = "'" + t; return /[",\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t; };
  const rows: unknown[][] = [[`FinLit research data · ${s.profile.name} (${s.profile.nse}) · ${s.meta.statement} · generated ${s.meta.generatedAt} · ₹ crore unless stated`], [],
    ["Research score", s.score.overall, s.score.band.label], ...s.score.pillars.map((p) => [p.label, p.score, p.band.label]), []];
  const table = (name: string, t: Table | undefined) => { if (t) rows.push([name, ...t.periods], ...Object.entries(t.rows).map(([k, v]) => [k, ...v]), []); };
  if (f) { table("Profit & loss", f.yearly.pl); table("Balance sheet", f.yearly.bs); table("Cash flow", f.yearly.cf); table("Quarterly P&L", f.quarterly.pl); }
  if (r) rows.push(["Ratio", "Value", "Unit", "Period"], ...Object.values(r.latest).map((e) => [e.label, e.value, e.unit, e.period]), []);
  rows.push(["Research summary, not a recommendation. " + "FinLit Ventures is not registered with SEBI or AMFI."]);
  return "﻿" + rows.map((row) => row.map(q).join(",")).join("\n");
}

export function saveFile(name: string, text: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a"); a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

const esc = (v: unknown) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] as string));

/** A single self-contained HTML file (no scripts, no external assets) that opens without internet. */
export function offlineHtml(s: Summary, f: Financials | undefined, r: Ratios | undefined): string {
  const t = (title: string, tb?: Table) => !tb ? "" : `<h2>${esc(title)}</h2><table><thead><tr><th>₹ Cr</th>${tb.periods.map((p) => `<th>${esc(p)}</th>`).join("")}</tr></thead><tbody>${Object.entries(tb.rows).map(([k, v]) => `<tr><td>${esc(k.replace(/_/g, " "))}</td>${v.map((x) => `<td>${x == null ? "—" : esc(x.toLocaleString("en-IN"))}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  const spark = s.sparkline.c; const mn = Math.min(...spark), mx = Math.max(...spark);
  const pts = spark.map((c, i) => `${(i / (spark.length - 1)) * 600},${80 - ((c - mn) / (mx - mn || 1)) * 70}`).join(" ");
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(s.profile.name)} · FinLit research</title>
<style>body{font:15px/1.55 system-ui,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;color:#232018}h1{font-weight:400}table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0 24px}th,td{padding:6px 8px;border-bottom:1px solid #ECEAE5;text-align:right}th:first-child,td:first-child{text-align:left}.n{font-size:56px;font-weight:300}.pill{display:inline-block;padding:3px 10px;border-radius:99px;background:#F3F2EE;margin-right:6px}small{color:#7C776B}</style></head><body>
<h1>${esc(s.profile.name)} <small>${esc(s.profile.nse)} · ${esc(s.meta.statement)}</small></h1>
<p>Price ₹${esc(s.quote.price)} · generated ${esc(s.meta.generatedAt)}</p>
<div class="n">${esc(s.score.overall ?? "—")}<small> / 100 · ${esc(s.score.band.label)}</small></div><p>${esc(s.thesis || "")}</p>
<p>${s.score.pillars.map((p) => `<span class="pill">${esc(p.label)} ${esc(p.score ?? "—")}</span>`).join("")}</p>
<svg viewBox="0 0 600 90" width="100%" height="90"><polyline fill="none" stroke="#8A6A25" stroke-width="2" points="${pts}"/></svg>
<h2>Strengths</h2><ul>${s.strengths.map((n) => `<li><b>${esc(n.title)}</b>: ${esc(n.text)}</li>`).join("")}</ul>
<h2>Watch-outs</h2><ul>${s.watchouts.map((n) => `<li><b>${esc(n.title)}</b>: ${esc(n.text)}</li>`).join("")}</ul>
${f ? t("Profit & loss", f.yearly.pl) + t("Balance sheet", f.yearly.bs) + t("Cash flow", f.yearly.cf) : ""}
${r ? `<h2>Ratios</h2><table><tbody>${Object.values(r.latest).map((e) => `<tr><td>${esc(e.label)}</td><td>${esc(e.value)} ${esc(e.unit || "")}</td><td>${esc(e.period)}</td></tr>`).join("")}</tbody></table>` : ""}
<p><small>Research summary, not a recommendation. FinLit Ventures is not registered with SEBI or AMFI. Data: company filings and market data.</small></p></body></html>`;
}
