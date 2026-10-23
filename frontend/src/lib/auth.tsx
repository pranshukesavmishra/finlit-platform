// Who is signed in, and which plan they have. The server decides both; the website only reflects it.
// Visitors (no session) get the Basic experience. In demo mode (VITE_DEMO=1) there are no accounts and the plan is a local preview.
import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiSend, setCsrf } from "./api";
import { DEMO } from "./demo";

export type Plan = "basic" | "silver" | "gold";
export type User = { id: string; email: string; name: string | null; role: "investor" | "admin"; plan: Plan; verified: boolean; mfa: boolean; mfaOk: boolean };
export type Limits = { watchlist_lists: number; watchlist_symbols: number; screens: number; compare: number; holdings: number };
type Me = { user: User | null; plan: Plan; limits: Limits; csrf: string | null; showcase?: string[] };

/** Same numbers the server enforces (backend/finlit/auth/entitlements.py); the server is what actually applies them. */
export const LIMITS: Record<Plan, Limits> = {
  basic: { watchlist_lists: 0, watchlist_symbols: 0, screens: 3, compare: 2, holdings: 0 },
  silver: { watchlist_lists: 3, watchlist_symbols: 30, screens: 20, compare: 2, holdings: 30 },
  gold: { watchlist_lists: 50, watchlist_symbols: 1000, screens: 100, compare: 4, holdings: 500 },
};
export const limitsFor = (plan: Plan): Limits => LIMITS[plan];

/** Demo preview only: a pretend member so the dashboard, appearance settings and plan preview can be shown without servers. */
const DEMO_USER: User = { id: "demo", email: "demo@finlit.example", name: "Demo member", role: "investor", plan: "gold", verified: true, mfa: false, mfaOk: false };

const VISITOR: Me = { user: null, plan: "basic", limits: LIMITS.basic, csrf: null, showcase: [] };

type Auth = {
  ready: boolean; user: User | null; plan: Plan; limits: Limits; isAdmin: boolean;
  /** Symbols whose full report the server sends to everyone (the free example). */
  showcase: string[];
  /** Re-read the session after a sign-in, sign-out or plan change; clears plan-dependent cached data. */
  refresh: () => Promise<void>;
  signOut: () => Promise<void>;
};
const Ctx = createContext<Auth | null>(null);

/** Cached API data that differs by plan: drop it whenever the account changes. */
const KEEP_KEYS = new Set(["me", "search-index", "content", "indices", "ipos"]);

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const q = useQuery<Me>({
    queryKey: ["me"], enabled: !DEMO, staleTime: 5 * 60_000, retry: 1, refetchOnWindowFocus: true,
    // The CSRF token is stored here, the moment the session arrives: a page's own effect (child effects run before this provider's) may
    // send a request in the very render that flips "ready", and without the token the server answers bad_csrf.
    queryFn: async () => { const m = await apiGet<Me>("/api/auth/me"); setCsrf(m.csrf); return m; },
  });
  const me = DEMO ? VISITOR : q.data ?? VISITOR;
  useEffect(() => { setCsrf(me.csrf); }, [me.csrf]);

  const clearPlanData = useCallback(() => { qc.removeQueries({ predicate: (q) => !KEEP_KEYS.has(String(q.queryKey[0])) }); }, [qc]);
  const refresh = useCallback(async () => {
    const before = qc.getQueryData<Me>(["me"]);
    const fresh = await qc.fetchQuery<Me>({ queryKey: ["me"], queryFn: () => apiGet<Me>("/api/auth/me"), staleTime: 0 });
    setCsrf(fresh.csrf);
    if (before?.user?.id !== fresh.user?.id || before?.plan !== fresh.plan) clearPlanData();
  }, [qc, clearPlanData]);
  const signOut = useCallback(async () => {
    try { await apiSend("POST", "/api/auth/logout"); } catch { /* already signed out */ }
    try { sessionStorage.removeItem("cms_admin_token"); } catch { /* ignore */ }   // the content-tools token must not outlive the account session
    setCsrf(null);
    qc.setQueryData<Me>(["me"], VISITOR);
    clearPlanData();
    qc.removeQueries({ queryKey: ["state"] });
  }, [qc, clearPlanData]);

  const value = useMemo<Auth>(() => ({
    ready: DEMO || !q.isPending, user: DEMO ? DEMO_USER : me.user, plan: me.plan, limits: me.limits, isAdmin: me.user?.role === "admin", showcase: me.showcase ?? [], refresh, signOut,
  }), [me, q.isPending, refresh, signOut]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const a = useContext(Ctx);
  if (!a) throw new Error("useAuth outside AuthProvider");
  return a;
}
