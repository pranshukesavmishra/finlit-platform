import { useQuery } from "@tanstack/react-query";
import { apiGet, type ApiError } from "./api";

/** Commodity prices from /api/commodity-prices (public). Every price is text already rounded by the server to the digits shown:
 *  this file only groups digits and writes dates, it never computes or rounds a price. */
export type McxState = "live" | "recent" | "delayed" | "closed" | "waiting" | "none" | "off";
export type IntlState = "fresh" | "stale" | "closed" | "unavailable" | "none" | "off";
export type CommodityMcx = {
  state: McxState; label: string; contract: string | null; expiry: string | null; unit: string; price: { value: string; unit: string } | null;
  extra: { label: string; value: string; unit: string }[]; change: { pct: string; abs: string; absUnit: string } | null; asOf: string | null; note: string | null;
};
export type CommodityIntl = { key: string; label: string; unit: string; state: IntlState; usd: string | null; changePct: string | null; asOf: string | null; vendor: string | null; note: string | null };
export type CommodityParity = {
  state: "ok" | "hidden"; reason: string | null; perGram?: string; per10g?: string; perKg?: string; withGst?: string; usdinr?: string; asOf?: string;
  duty?: { bcd: string; aidc: string; total: string; gst: string; effectiveFrom: string; checkedOn: string }; premiumPct?: string | null; premiumBasis?: string;
};
export type CommodityItem = {
  code: string; name: string; group: "precious" | "energy" | "industrial"; mcx: CommodityMcx | null; intl: CommodityIntl[]; parity: CommodityParity | null; notes: string[];
};
export type Commodities = {
  asOf: string; status: "ok" | "waiting";
  market: { mcx: { open: boolean; opens: string; closes: string; hoursConfirmed: boolean; why: string | null }; global: { open: boolean } };
  sources: { mcx: { connected: boolean; label: string; error: string | null }; intl: { connected: boolean; metals: string | null; energy: string | null; errors: Record<string, string> } };
  fx: { state: "fresh" | "stale" | "closed" | "unavailable" | "none" | "off"; usdinr: string | null; asOf: string | null; vendor: string | null };
  assumptions: { k22: string; mcxGoldFineness: string; fineFineness: string; parity: string };
  ratio: { goldSilver: string | null }; items: CommodityItem[]; worker: { ageSeconds: number | null };
};

/** Every 15 seconds while MCX trades (only while the tab is visible), every 5 minutes otherwise. */
export const useCommodities = () =>
  useQuery<Commodities, ApiError>({
    queryKey: ["commodities"], queryFn: () => apiGet("/api/commodity-prices"), staleTime: 10_000, retry: 1,
    refetchInterval: (q) => (q.state.data?.market.mcx.open ? 15_000 : 300_000),
  });

// ------------------------------------------------------------------------------------------------------------- text formatting (no floats)
const grp = (d: string, lakh: boolean) =>
  lakh && d.length > 3 ? d.slice(0, -3).replace(/\B(?=(\d{2})+(?!\d))/g, ",") + "," + d.slice(-3) : d.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
/** "14163329.50" -> "1,41,63,329.50" (Indian grouping) or "14,163,329.50"; keeps the digits as given, so nothing is rounded again. */
export function group(v: string | null | undefined, lakh = true): string {
  if (v == null || !/^-?\d+(\.\d+)?$/.test(v)) return "—";
  const neg = v.startsWith("-");
  const [i, f] = (neg ? v.slice(1) : v).split(".");
  return (neg ? "−" : "") + grp(i, lakh) + (f != null ? "." + f : "");
}
const money = (v: string | null | undefined, sym: string, lakh: boolean) =>
  v == null || !/^-?\d+(\.\d+)?$/.test(v) ? "—" : (v.startsWith("-") ? "−" : "") + sym + group(v.replace(/^-/, ""), lakh);
export const inr = (v: string | null | undefined) => money(v, "₹", true);
export const usd = (v: string | null | undefined) => money(v, "$", false);
/** "0.62" -> "▲ +0.62%", "-0.4" -> "▼ −0.4%", zero -> "0.00%" with no arrow. */
export function signedPct(v: string | null | undefined): string {
  if (v == null || !/^-?\d+(\.\d+)?$/.test(v)) return "—";
  if (/^-?0+(\.0+)?$/.test(v)) return v.replace("-", "") + "%";
  return v.startsWith("-") ? `▼ −${v.slice(1)}%` : `▲ +${v}%`;
}
export const direction = (v: string | null | undefined): "up" | "down" | "flat" => (v == null || /^-?0+(\.0+)?$/.test(v) ? "flat" : v.startsWith("-") ? "down" : "up");

const IST = "Asia/Kolkata";
/** 21:41:58 in Indian time, from an ISO time. */
export const istTime = (iso: string | null | undefined) => {
  const d = iso ? new Date(iso) : null;
  return d && !Number.isNaN(d.getTime()) ? d.toLocaleTimeString("en-GB", { timeZone: IST, hour12: false }) : "—";
};
/** "Fri 23 Oct, 21:41" in Indian time. */
export const istStamp = (iso: string | null | undefined) => {
  const d = iso ? new Date(iso) : null;
  return d && !Number.isNaN(d.getTime())
    ? d.toLocaleDateString("en-GB", { timeZone: IST, weekday: "short", day: "numeric", month: "short" }) + ", " + d.toLocaleTimeString("en-GB", { timeZone: IST, hour12: false, hour: "2-digit", minute: "2-digit" })
    : "—";
};
export const dayMonthYear = (isoDay: string | null | undefined) => {
  const d = isoDay ? new Date(isoDay + "T00:00:00Z") : null;
  return d && !Number.isNaN(d.getTime()) ? d.toLocaleDateString("en-GB", { timeZone: "UTC", day: "numeric", month: "short", year: "numeric" }) : "—";
};

// ------------------------------------------------------------------------------------------------------------- unit converter (exact)
/** Every unit as a whole number of 1e-7 gram, so the arithmetic is exact in BigInt: the grain is exactly 0.06479891 g, a troy ounce 480 grains, a tola 180. */
export const UNITS = [
  { id: "g", label: "Gram", scaled: 10_000_000n },
  { id: "g8", label: "8 g (sovereign)", scaled: 80_000_000n },
  { id: "g10", label: "10 grams", scaled: 100_000_000n },
  { id: "tola", label: "Tola (11.6638038 g)", scaled: 116_638_038n },
  { id: "kg", label: "Kilogram", scaled: 10_000_000_000n },
  { id: "toz", label: "Troy ounce (31.1034768 g)", scaled: 311_034_768n },
] as const;
export type UnitId = (typeof UNITS)[number]["id"];

/** value (text, at most 12 decimals) of one unit in another, to `dp` places, rounded half up; null for an empty or invalid number. */
export function convert(value: string, from: UnitId, to: UnitId, dp = 4): string | null {
  const t = value.trim().replace(/,/g, "");
  const m = /^(\d{1,15})(?:\.(\d{1,12}))?$/.exec(t);
  if (!m) return null;
  const frac = m[2] ?? "";
  const num = BigInt(m[1] + frac);
  const f = UNITS.find((u) => u.id === from)!.scaled, g = UNITS.find((u) => u.id === to)!.scaled;
  const den = 10n ** BigInt(frac.length) * g;
  const scale = 10n ** BigInt(dp);
  const r = (num * f * scale * 2n + den) / (den * 2n);          // half up
  const s = r.toString().padStart(dp + 1, "0");
  return dp ? `${s.slice(0, -dp)}.${s.slice(-dp)}` : s;
}
