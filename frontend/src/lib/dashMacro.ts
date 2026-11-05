// The six "prices and rates" tiles of the dashboard's Market today block, worked out from /api/macro. A tile with no number carries the reason instead; nothing is estimated.
import type { Macro, Pt } from "./macro";
import { MINUS, nf } from "./format";
import { dayMonth, monthName } from "./dashboard";

export type RateTile = { key: string; name: string; value: string | null; note: string; tone?: "up" | "down" };
const last = (m: Macro | undefined, key: string): Pt | null => { const p = m?.series?.[key]?.points; return p && p.length ? p[p.length - 1] : null; };
const signed = (v: number, d = 1) => (v > 0 ? "+" : v < 0 ? MINUS : "") + nf(Math.abs(v), d);

export function rateTiles(m: Macro | undefined): RateTile[] {
  const b = m?.brent, cpi = last(m, "cpi"), wpi = last(m, "wpi"), repo = last(m, "repo");
  const fx = m?.rates?.fx?.usdinr ?? null, dec = m?.decisions?.length ? [...m.decisions].sort((a, c) => a.date.localeCompare(c.date)).pop()! : null;
  const repoNow = m?.rates?.rates?.repo ?? repo?.[1] ?? null;
  return [
    b && b.value != null
      ? { key: "brent", name: "Brent crude", value: "US$" + nf(b.value), note: b.vsAvgPct != null ? `${signed(b.vsAvgPct)}% vs 4-quarter average` : (b.reason || "4-quarter average not available"), tone: b.vsAvgPct == null ? undefined : b.vsAvgPct >= 0 ? "up" : "down" }
      : { key: "brent", name: "Brent crude", value: null, note: b?.reason || "Brent: no prices loaded yet" },
    fx != null ? { key: "usdinr", name: "USD / INR", value: nf(fx), note: m?.rates?.fxAsOf ? `FBIL, ${dayMonth(m.rates.fxAsOf)}` : "FBIL reference rate" } : { key: "usdinr", name: "USD / INR", value: null, note: "FBIL rate not loaded yet" },
    repoNow != null ? { key: "repo", name: "Repo rate", value: nf(repoNow) + "%", note: dec ? `${dec.bp > 0 ? "+" : dec.bp < 0 ? MINUS : ""}${Math.abs(dec.bp)} bp on ${dayMonth(dec.date)}` : "RBI policy rate" } : { key: "repo", name: "Repo rate", value: null, note: "RBI rate not loaded yet" },
    cpi ? { key: "cpi", name: "CPI inflation", value: nf(cpi[1]) + "%", note: monthName(cpi[0]) } : { key: "cpi", name: "CPI inflation", value: null, note: "MoSPI figure not loaded yet" },
    wpi ? { key: "wpi", name: "WPI inflation", value: nf(wpi[1]) + "%", note: monthName(wpi[0]) } : { key: "wpi", name: "WPI inflation", value: null, note: "MoSPI figure not loaded yet" },
    { key: "gsec", name: "10-year G-sec", value: null, note: "No free public yield feed is connected yet" },
  ];
}
