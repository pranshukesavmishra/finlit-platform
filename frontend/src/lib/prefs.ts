// Appearance and dashboard layout. Kept in this browser for everyone and mirrored to the account when signed in,
// so the same choices follow a member to a new device (and later to the mobile app).
import { useSyncExternalStore } from "react";
import { isPalette, type PaletteId } from "./palettes";

export type Density = "comfortable" | "compact";
export type WidgetSize = "third" | "half" | "full";
export type WidgetPref = { id: string; on: boolean; size: WidgetSize };
export type Prefs = { palette: PaletteId; density: Density; alerts: boolean; screenAlerts: boolean; profitGap: boolean; rotationCorner: boolean; rotationRank: boolean; digest: boolean; dashboard: WidgetPref[] };

/** The phone's three tabs, each holding some of the blocks. */
export type DashTab = "stocks" | "market" | "news";
export const DASH_TABS: { id: DashTab; label: string }[] = [{ id: "stocks", label: "My stocks" }, { id: "market", label: "Market" }, { id: "news", label: "News" }];

/** Everything the dashboard can show, in the default order. `min` is the plan a widget needs (its data is gated on the server too); `off` blocks are in Customise but not in the
 *  default layout (the Gold & silver card needs a licensed price source; the DCF promo is already in the menu; the quarter-results cards are now part of "Your stocks today").
 *  Ids are lower-case letters and digits: the server stores them as written. */
export const WIDGETS: { id: string; label: string; blurb: string; min: "basic" | "silver" | "gold"; size: WidgetSize; tab: DashTab; off?: boolean }[] = [
  { id: "mystocks", label: "Your stocks today", blurb: "Price, today's move, FinLit IQ, latest results and alert for each stock you follow.", min: "basic", size: "full", tab: "stocks" },
  { id: "market", label: "Market today", blurb: "Index levels, the Nifty 50 / Sensex chart, and the prices and rates that move company profits.", min: "basic", size: "full", tab: "market" },
  { id: "snapshot", label: "Market snapshot", blurb: "How many stocks rose and fell, and the biggest movers of Nifty 50, Nifty 500 or all stocks.", min: "basic", size: "half", tab: "market" },
  { id: "sectors", label: "Sectors today", blurb: "Every sector's move today, ranked.", min: "basic", size: "half", tab: "market" },
  { id: "flows", label: "FII / DII flows", blurb: "Net buying and selling by foreign and domestic institutions.", min: "basic", size: "half", tab: "market" },
  { id: "stress", label: "Stress Lab: today's conditions", blurb: "How today's crude, rupee, inflation and rate conditions would touch the stocks you follow.", min: "basic", size: "half", tab: "stocks" },
  { id: "heatmap", label: "Index heatmap", blurb: "Stocks of an index as a map or a list, coloured by today's move.", min: "basic", size: "full", tab: "market" },
  { id: "resultstoday", label: "Results today", blurb: "Companies that have filed, or are due to report, results.", min: "basic", size: "half", tab: "news" },
  { id: "filings", label: "Filings and news", blurb: "The latest exchange filings, tagged and shortened to one line.", min: "basic", size: "half", tab: "news" },
  { id: "ipos", label: "IPOs open now", blurb: "Issues open now or opening soon, with price band and close date.", min: "basic", size: "third", tab: "news" },
  { id: "alerts", label: "Alerts and saved screens", blurb: "Your active and triggered alerts, and your saved screens.", min: "basic", size: "third", tab: "stocks" },
  { id: "learn", label: "Term of the day", blurb: "One plain-words finance term, every day.", min: "basic", size: "third", tab: "news" },
  { id: "results", label: "Latest quarter results", blurb: "Newest quarter for your stocks: year-on-year and quarter-on-quarter, with a chart.", min: "basic", size: "full", tab: "stocks", off: true },
  { id: "movers", label: "Watchlist movers", blurb: "Biggest moves among the stocks you follow.", min: "silver", size: "half", tab: "stocks", off: true },
  { id: "second", label: "Worth a second look", blurb: "Strong FinLit IQs trading below their usual valuation.", min: "silver", size: "half", tab: "stocks", off: true },
  { id: "buckets", label: "Watchlist by band", blurb: "How your watchlist splits across FinLit IQ bands.", min: "gold", size: "half", tab: "stocks", off: true },
  { id: "dcf", label: "DCF calculator", blurb: "Your saved DCF scenarios: intrinsic value, margin-of-safety price and status.", min: "gold", size: "half", tab: "stocks", off: true },
  { id: "commodities", label: "Gold & silver today", blurb: "MCX gold, silver and crude oil with the day change. Off until a licensed price source is connected.", min: "basic", size: "half", tab: "market", off: true },
];
const defaultLayout = (): WidgetPref[] => WIDGETS.map((w) => ({ id: w.id, on: !w.off, size: w.size }));
const DEFAULTS: Prefs = { palette: "gold", density: "comfortable", alerts: true, screenAlerts: true, profitGap: true, rotationCorner: true, rotationRank: false, digest: false, dashboard: defaultLayout() };

const KEY = "finlit-prefs-v1";
/** A saved layout, cleaned: only known blocks, each once, every block present. A layout saved before the refreshed dashboard (it has no "Your stocks today") is replaced by the new default. */
export function normaliseLayout(saved: WidgetPref[] | undefined | null): WidgetPref[] {
  const known = new Map(WIDGETS.map((w) => [w.id, w]));
  if (!(saved ?? []).some((w) => w?.id === "mystocks")) return defaultLayout();
  const seen = new Set<string>();
  const dash: WidgetPref[] = [];
  for (const w of saved ?? []) if (w && known.has(w.id) && !seen.has(w.id)) { seen.add(w.id); dash.push({ id: w.id, on: !!w.on, size: w.size === "full" ? "full" : w.size === "third" ? "third" : "half" }); }
  for (const w of WIDGETS) if (!seen.has(w.id)) dash.push({ id: w.id, on: !w.off, size: w.size }); // new blocks appear for existing members
  return dash;
}
function normalise(raw: Partial<Prefs> | null | undefined): Prefs {
  return { palette: isPalette(raw?.palette) ? raw!.palette! : "gold", density: raw?.density === "compact" ? "compact" : "comfortable", alerts: raw?.alerts !== false, screenAlerts: raw?.screenAlerts !== false, profitGap: raw?.profitGap !== false, rotationCorner: raw?.rotationCorner !== false, rotationRank: raw?.rotationRank === true, digest: raw?.digest === true, dashboard: normaliseLayout(raw?.dashboard) };
}
function read(): Prefs { try { return normalise(JSON.parse(localStorage.getItem(KEY) || "null")); } catch { return normalise(null); } }

let state = typeof localStorage === "undefined" ? DEFAULTS : read();
const subs = new Set<() => void>();
type Listener = (p: Prefs) => void;
let onChange: Listener | null = null;

export const prefs = {
  get: () => state,
  subscribe: (f: () => void) => { subs.add(f); return () => subs.delete(f); },
  /** The account layer registers here to save changes. */
  onSave: (f: Listener | null) => { onChange = f; },
  set(patch: Partial<Prefs>, fromServer = false) {
    state = normalise({ ...state, ...patch });
    try { localStorage.setItem(KEY, JSON.stringify(state)); } catch { /* private mode */ }
    subs.forEach((f) => f());
    if (!fromServer) onChange?.(state);
  },
  reset: () => prefs.set({ ...DEFAULTS, dashboard: defaultLayout() }),
};
export const usePrefs = () => useSyncExternalStore(prefs.subscribe, prefs.get, prefs.get);
