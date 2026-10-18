// Alerts and the notification centre. Signed-in members use the server (alerts are evaluated by the worker, notifications are kept
// in the account). The demo, which has no server, keeps both in this browser and evaluates them against the sample universe.
import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiSend } from "./api";
import { useAuth } from "./auth";
import { useUI } from "./ui";
import { DEMO } from "./demo";
import { LIMITS, METRICS, describe, fmtValue, isEvent, type Op } from "./alertCatalog";
import type { Row } from "./screener";

export type Channel = "app" | "email" | "browser";
export type AlertRow = {
  id: string; symbol: string; metric: string; label: string; unit: string; op: Op; value: number | null; keyword: string | null; channels: Channel[];
  repeat: "once" | "every"; status: "active" | "paused" | "done"; note: string | null; lastValue: number | null; met: boolean | null;
  lastCheckedAt: string | null; lastFiredAt: string | null; firedCount: number; createdAt: string;
};
export type Notice = { id: number; alertId: string | null; symbol: string | null; kind: string; title: string; body: string; link: string | null; push: boolean; read: boolean; createdAt: string };
export type NewAlert = { symbol: string; metric: string; op: Op; value: number | null; keyword?: string; channels: Channel[]; repeat: "once" | "every"; note?: string };
export type Created = AlertRow & { alreadyMet?: boolean; current?: number | null };

// ---------------------------------------------------------------- demo store (this browser only)
type Demo = { alerts: AlertRow[]; notices: Notice[]; seq: number; seeded: boolean; drift: Record<string, number> };
const KEY = "finlit-alerts-demo-v1";
let demo: Demo = (() => { try { const s = JSON.parse(localStorage.getItem(KEY) || "null"); if (s?.alerts) return s; } catch { /* private mode */ } return { alerts: [], notices: [], seq: 1, seeded: false, drift: {} }; })();
const subs = new Set<() => void>();
const save = () => { demo = { ...demo }; try { localStorage.setItem(KEY, JSON.stringify(demo)); } catch { /* private mode */ } subs.forEach((f) => f()); };
const ago = (min: number) => new Date(Date.now() - min * 60_000).toISOString();
const hash = (s: string) => { let h = 2166136261; for (const c of s) h = Math.imul(h ^ c.charCodeAt(0), 16777619); return (h >>> 0) / 4294967295; };

/** Sample value of any metric for the demo. Columns the screener has are real sample data; the rest are steady made-up numbers per stock. */
export function demoValue(row: Row | undefined, symbol: string, metric: string): number | null {
  const r = (a: number, b: number) => a + (b - a) * hash(symbol + metric);
  const col = (row as unknown as Record<string, number | null> | undefined)?.[metric];
  let v: number | null;
  if (metric === "move_abs") v = row?.change_pct == null ? r(0, 4) : Math.abs(row.change_pct);
  else if (col !== undefined) v = col;
  else v = ({ rsi14: r(24, 74), ema50_gap: r(-8, 12), ema200_gap: r(-15, 30), volume_x: r(0.6, 3.4), from_high52: r(0, 35), from_low52: r(2, 120), q_net_profit: Math.round((row?.market_cap || 50000) * r(0.008, 0.018)),
    q_revenue: Math.round((row?.market_cap || 50000) * r(0.05, 0.12)), promoter_chg: r(-1.4, 1.4), fii_chg: r(-2, 2), price: 100 } as Record<string, number>)[metric] ?? null;
  if (v == null) return null;
  v = v + (demo.drift[symbol + ":" + metric] || 0);
  return Math.round(v * 100) / 100;
}
const isMet = (op: Op, v: number, t: number) => (op === "above" ? v >= t : v <= t);

function demoNotice(a: AlertRow, v: number | null, minsAgo = 0): Notice {
  const title = isEvent(a.metric) ? `${a.symbol} – ${describe(a)}` : `${a.symbol} – ${a.label} is now ${fmtValue(a.metric, v)}, ${a.op === "above" ? "above" : "below"} your target of ${fmtValue(a.metric, a.value)}`;
  return { id: demo.seq++, alertId: a.id, symbol: a.symbol, kind: "alert", title, body: `Sample alert from the demo. ${describe(a)}.`, link: `/stocks/${a.symbol}`, push: a.channels.includes("browser"), read: false, createdAt: ago(minsAgo) };
}
/** Re-check every active demo alert against the sample data (what the worker does on the server). Returns how many fired. */
export function demoCheck(rows: Row[]): number {
  const by = new Map(rows.map((r) => [r.symbol, r]));
  let fired = 0;
  demo.alerts = demo.alerts.map((a) => {
    if (a.status !== "active" || isEvent(a.metric)) return a;
    const v = demoValue(by.get(a.symbol), a.symbol, a.metric); if (v == null || a.value == null) return a;
    const met = isMet(a.op, v, a.value), cross = met && a.met === false;
    if (cross) { demo.notices.unshift(demoNotice({ ...a }, v)); fired++; }
    return { ...a, lastValue: v, met, lastCheckedAt: new Date().toISOString(), ...(cross ? { firedCount: a.firedCount + 1, lastFiredAt: new Date().toISOString(), status: a.repeat === "once" ? "done" as const : a.status } : {}) };
  });
  if (fired) save();
  return fired;
}
/** Demo only: push every active alert's metric just past its target so the next check fires it. */
export function demoNudge(rows: Row[]) {
  const by = new Map(rows.map((r) => [r.symbol, r]));
  for (const a of demo.alerts) {
    if (a.status !== "active" || a.value == null || isEvent(a.metric)) continue;
    const base = demoValue(by.get(a.symbol), a.symbol, a.metric) ?? 0, k = a.symbol + ":" + a.metric, cur = demo.drift[k] || 0;
    const want = a.value + (a.op === "above" ? 1 : -1) * Math.max(Math.abs(a.value) * 0.02, 0.1);
    demo.drift[k] = cur + (want - base);
  }
  save();
}
export function demoReset() { demo = { alerts: [], notices: [], seq: 1, seeded: true, drift: {} }; save(); }
function demoSeed(rows: Row[]) {
  if (demo.seeded || !rows.length) return;
  demo.seeded = true;
  const sym = rows.find((r) => r.symbol === "RELIANCE") ? "RELIANCE" : rows[0].symbol;
  const mk = (metric: string, op: Op, value: number | null, extra: Partial<AlertRow> = {}): AlertRow => ({ id: "d" + demo.seq++, symbol: sym, metric, label: METRICS[metric].label, unit: METRICS[metric].unit, op, value, keyword: null,
    channels: ["app", "email"], repeat: "every", status: "active", note: null, lastValue: null, met: false, lastCheckedAt: ago(4), lastFiredAt: null, firedCount: 0, createdAt: ago(60 * 24 * 3), ...extra });
  const by = rows.find((r) => r.symbol === sym);
  const price = by?.price ?? 1000;
  demo.alerts = [
    mk("rsi14", "below", 30, { lastValue: demoValue(by, sym, "rsi14"), firedCount: 1, lastFiredAt: ago(2), met: true }),
    mk("price", "above", Math.round(price * 1.06), { lastValue: price }),
    mk("volume_x", "above", 3, { lastValue: demoValue(by, sym, "volume_x"), channels: ["app", "browser"] }),
    mk("news_keyword", "event", null, { keyword: "dividend", lastValue: null }),
  ];
  demo.notices = [
    { id: demo.seq++, alertId: demo.alerts[0].id, symbol: sym, kind: "alert", title: `${sym} – RSI (14) is now 29.4, below your target of 30`, body: "Sample alert from the demo. RSI (14) falls to or below 30.", link: `/stocks/${sym}`, push: false, read: false, createdAt: ago(2) },
    { id: demo.seq++, alertId: null, symbol: sym, kind: "alert", title: `${sym} – Volume is now 3.4×, above your target of 3×`, body: "Sample alert from the demo.", link: `/stocks/${sym}`, push: false, read: true, createdAt: ago(60 * 26) },
  ];
  save();
}
const demoStore = { subscribe: (f: () => void) => { subs.add(f); return () => subs.delete(f); }, get: () => demo };
/** Demo only: re-renders when the browser-held store changes. */
export const useDemoStore = () => useSyncExternalStore(demoStore.subscribe, demoStore.get, demoStore.get);

const wrongPlan = (plan: string, metric: string) => METRICS[metric].tier === "silver" && plan === "basic";
function demoCreate(plan: string, rows: Row[], b: NewAlert): Created {
  const err = (status: string, detail: string, extra: Record<string, unknown> = {}) => Object.assign(new Error(detail), { body: { status, detail, ...extra } });
  if (wrongPlan(plan, b.metric)) throw err("plan_required", `${METRICS[b.metric].label} alerts are part of the Silver plan.`, { plan: "silver" });
  const cap = LIMITS[plan] ?? 3;
  if (demo.alerts.filter((a) => a.status !== "done").length >= cap) throw err("plan_limit", `Your plan includes ${cap} alerts at a time. Remove one that has finished, or upgrade.`);
  const kw = (b.keyword || "").trim().toLowerCase() || null;
  if (demo.alerts.some((a) => a.status !== "done" && a.symbol === b.symbol && a.metric === b.metric && a.op === b.op && a.value === b.value && a.keyword === kw)) throw err("duplicate", "You already have this alert.");
  const row = rows.find((r) => r.symbol === b.symbol);
  const current = isEvent(b.metric) ? null : demoValue(row, b.symbol, b.metric);
  const met = current != null && b.value != null && !isEvent(b.metric) ? isMet(b.op, current, b.value) : false;
  const a: AlertRow = { id: "d" + demo.seq++, symbol: b.symbol, metric: b.metric, label: METRICS[b.metric].label, unit: METRICS[b.metric].unit, op: b.op, value: b.value, keyword: b.metric === "news_keyword" ? kw : null,
    channels: ["app", ...b.channels.filter((c) => c !== "app")] as Channel[], repeat: b.repeat, status: "active", note: b.note?.trim() || null, lastValue: current, met, lastCheckedAt: new Date().toISOString(), lastFiredAt: null, firedCount: 0, createdAt: new Date().toISOString() };
  demo.alerts.unshift(a); save();
  return { ...a, alreadyMet: met, current };
}

// ---------------------------------------------------------------- server calls
const POLL = 45_000;
export const alertKeys = { alerts: ["alerts"], notices: ["notices"], value: (s: string, m: string) => ["alert-value", s, m] };

export function useAlerts(rows?: Row[]) {
  const { user } = useAuth();
  const { plan } = useUI();
  const qc = useQueryClient();
  const d = useDemoStore();
  const q = useQuery({
    queryKey: alertKeys.alerts, enabled: !!user && !DEMO, staleTime: 15_000, retry: 1,
    queryFn: () => apiGet<{ alerts: AlertRow[]; limit: number }>("/api/alerts", { cache: "reload" }),
  });
  useEffect(() => { if (DEMO && rows?.length) demoSeed(rows); }, [rows]);
  const refresh = () => { qc.invalidateQueries({ queryKey: alertKeys.alerts }); qc.invalidateQueries({ queryKey: alertKeys.notices }); };
  const create = useMutation({
    mutationFn: (b: NewAlert): Promise<Created> => DEMO ? Promise.resolve().then(() => demoCreate(plan, rows || [], b)) : apiSend<Created>("POST", "/api/alerts", b),
    onSuccess: refresh,
  });
  const patch = useMutation({
    mutationFn: ({ id, ...p }: { id: string; status?: "active" | "paused"; value?: number; repeat?: "once" | "every"; channels?: Channel[]; note?: string }) => {
      if (DEMO) { demo.alerts = demo.alerts.map((a) => a.id === id ? { ...a, ...p, met: p.status === "active" || p.value !== undefined ? null : a.met, ...(p.status === "active" && a.status === "done" ? { firedCount: 0 } : {}) } : a); demo.alerts = demo.alerts.map((a) => a.id === id && a.met === null && a.value != null && !isEvent(a.metric) ? { ...a, met: isMet(a.op, a.lastValue ?? demoValue(rows?.find((r) => r.symbol === a.symbol), a.symbol, a.metric) ?? 0, a.value) } : a); save(); return Promise.resolve(null); }
      return apiSend("PATCH", `/api/alerts/${id}`, p);
    },
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: string) => { if (DEMO) { demo.alerts = demo.alerts.filter((a) => a.id !== id); save(); return Promise.resolve(null); } return apiSend("DELETE", `/api/alerts/${id}`); },
    onSuccess: refresh,
  });
  const alerts = DEMO ? d.alerts : q.data?.alerts ?? NO_ALERTS;
  return { alerts, limit: DEMO ? LIMITS[plan] : q.data?.limit ?? LIMITS[plan], loading: !DEMO && q.isLoading, error: q.error, create, patch, remove };
}

const NO_NOTICES: Notice[] = [];
const NO_ALERTS: AlertRow[] = [];
export function useNotices() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const d = useDemoStore();
  const q = useQuery({
    queryKey: alertKeys.notices, enabled: !!user && !DEMO, refetchInterval: POLL, refetchOnWindowFocus: true, staleTime: 10_000, retry: 0,
    queryFn: () => apiGet<{ notifications: Notice[]; unread: number }>("/api/notifications?limit=50", { cache: "reload" }),
  });
  const items = DEMO ? d.notices : q.data?.notifications ?? NO_NOTICES;  // one shared empty list: a new [] every render would retrigger effects that depend on it
  const unread = DEMO ? d.notices.filter((n) => !n.read).length : q.data?.unread ?? 0;
  const markRead = useCallback(async (ids?: number[]) => {
    if (DEMO) { demo.notices = demo.notices.map((n) => (!ids || ids.includes(n.id) ? { ...n, read: true } : n)); save(); return; }
    qc.setQueryData<{ notifications: Notice[]; unread: number }>(alertKeys.notices, (o) => o && ({ notifications: o.notifications.map((n) => (!ids || ids.includes(n.id) ? { ...n, read: true } : n)), unread: ids ? Math.max(0, o.unread - ids.filter((i) => o.notifications.some((n) => n.id === i && !n.read)).length) : 0 }));
    try { await apiSend("POST", "/api/notifications/read", ids ? { ids } : {}); } catch { /* the next poll corrects the badge */ }
  }, [qc]);
  const clear = useCallback(async () => {
    if (DEMO) { demo.notices = []; save(); return; }
    qc.setQueryData(alertKeys.notices, { notifications: [], unread: 0 });
    try { await apiSend("DELETE", "/api/notifications"); } catch { /* ignore */ }
  }, [qc]);
  return { items, unread, markRead, clear, loading: !DEMO && q.isLoading };
}

/** The value a metric stands at right now (for "currently 31.2" in the form). */
export function useCurrentValue(symbol: string, metric: string, rows?: Row[]) {
  const { user } = useAuth();
  const d = useDemoStore();
  void d;
  const ev = !metric || isEvent(metric);
  const q = useQuery({
    queryKey: alertKeys.value(symbol, metric), enabled: !!symbol && !ev && !!user && !DEMO, staleTime: 60_000, retry: 0,
    queryFn: () => apiGet<{ value: number | null }>(`/api/alerts/value?symbol=${encodeURIComponent(symbol)}&metric=${encodeURIComponent(metric)}`, { cache: "reload" }).then((r) => r.value),
  });
  if (ev || !symbol) return null;
  if (DEMO) return demoValue(rows?.find((r) => r.symbol === symbol), symbol, metric);
  return q.data ?? null;
}

// ---------------------------------------------------------------- browser notifications
export const browserSupport = () => typeof Notification !== "undefined";
export const browserPermission = (): NotificationPermission | "unsupported" => (browserSupport() ? Notification.permission : "unsupported");
export async function askBrowserPermission(): Promise<NotificationPermission | "unsupported"> {
  if (!browserSupport()) return "unsupported";
  try { return await Notification.requestPermission(); } catch { return Notification.permission; }
}
/** Shows a system notification for each new alert flagged for the browser; remembers what it already showed so a reload never repeats one. */
export function useBrowserNotify(items: Notice[]) {
  const shown = useRef<Set<number> | null>(null);
  useEffect(() => {
    if (shown.current === null) { try { shown.current = new Set(JSON.parse(sessionStorage.getItem("finlit-notified") || "[]")); } catch { shown.current = new Set(); } if (!shown.current.size) items.forEach((n) => shown.current!.add(n.id)); }
    if (browserPermission() !== "granted") return;
    for (const n of items) {
      if (n.read || !n.push || shown.current.has(n.id)) continue;
      shown.current.add(n.id);
      try { const x = new Notification("FinLit alert", { body: n.title, tag: "finlit-" + n.id, icon: "/icon-192.png" }); x.onclick = () => { window.focus(); if (n.link) location.assign(n.link); }; } catch { /* some browsers only allow this from a service worker */ }
    }
    try { sessionStorage.setItem("finlit-notified", JSON.stringify([...shown.current].slice(-200))); } catch { /* private mode */ }
  }, [items]);
}

export function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} hr ago`;
  if (s < 172800) return "yesterday";
  return `${Math.floor(s / 86400)} days ago`;
}
