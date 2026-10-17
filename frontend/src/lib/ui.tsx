// App-wide UI state: theme, plan, toasts. The plan comes from the signed-in account (server-side); demo mode previews it locally.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useLocation, useNavigate } from "react-router";
import { useAuth, type Plan } from "./auth";
import { DEMO } from "./demo";
import { applyPalette } from "./palettes";
import { usePrefs } from "./prefs";

export type { Plan };
export const RANK: Record<Plan, number> = { basic: 0, bronze: 1, gold: 2 };
export const TIER: Record<Plan, { n: string; ic: string; tc: string }> = {
  basic: { n: "Basic", ic: "sprout", tc: "--t-basic" },
  bronze: { n: "Bronze", ic: "medal", tc: "--t-bronze" },
  gold: { n: "Gold", ic: "crown", tc: "--t-gold" },
};

type UI = {
  theme: "dark" | "light"; toggleTheme: () => void;
  plan: Plan; has: (tier: Plan) => boolean;
  /** Demo mode only (the header preview switch); a no-op for real accounts. */
  setPlan: (p: Plan) => void;
  /** The user wants a feature their plan lacks: preview it (demo), ask them to sign in, or open the plan request. */
  upgrade: (tier: Plan, why?: string) => void;
  toast: (msg: string) => void;
};
const Ctx = createContext<UI | null>(null);

const read = (k: string) => { try { return localStorage.getItem(k); } catch { return null; } };
const write = (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } };

export function UIProvider({ children }: { children: ReactNode }) {
  const root = document.documentElement;
  const [theme, setTheme] = useState<"dark" | "light">((root.dataset.theme as "dark" | "light") || "dark");
  const auth = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  // Demo only: preview each tier locally. Otherwise the plan is whatever the server says the account has.
  const [preview, setPreview] = useState<Plan>(((read("finlit-plan") as Plan) || (root.dataset.plan as Plan) || "gold"));
  const plan: Plan = DEMO ? preview : auth.plan;
  const [msg, setMsg] = useState<string | null>(null);
  const timer = useRef<number>(0);

  const prefs = usePrefs();
  useEffect(() => { root.dataset.theme = theme; write("finlit-theme", theme); applyPalette(prefs.palette, theme, root); }, [theme, prefs.palette, root]);
  useEffect(() => { if (prefs.density === "compact") root.dataset.density = "compact"; else delete root.dataset.density; write("finlit-density", prefs.density); }, [prefs.density, root]);
  useEffect(() => { root.dataset.plan = plan; if (DEMO) write("finlit-plan", plan); }, [plan, root]);

  const toast = useCallback((m: string) => {
    setMsg(m); window.clearTimeout(timer.current); timer.current = window.setTimeout(() => setMsg(null), 3400);
  }, []);
  const upgrade = useCallback((tier: Plan, why?: string) => {
    if (DEMO) { setPreview(tier); toast(`Previewing the ${TIER[tier].n} plan.`); return; }
    const next = encodeURIComponent(loc.pathname + loc.search);
    if (!auth.user) { toast(why ? `${why} Sign in or create a free account first.` : "Create a free account to continue."); nav(`/login?next=${next}&plan=${tier}`); return; }
    nav(`/account/plan?want=${tier}&from=${next}`);
  }, [auth.user, loc.pathname, loc.search, nav, toast]);
  const value = useMemo<UI>(() => ({
    theme, toggleTheme: () => setTheme((t) => (t === "dark" ? "light" : "dark")),
    plan, has: (tier) => RANK[plan] >= RANK[tier], setPlan: DEMO ? setPreview : () => undefined, upgrade, toast,
  }), [theme, plan, toast, upgrade]);

  return (
    <Ctx.Provider value={value}>
      {children}
      <div className="toast" role="status" hidden={!msg}>{msg}</div>
    </Ctx.Provider>
  );
}

export function useUI() {
  const ui = useContext(Ctx);
  if (!ui) throw new Error("useUI outside UIProvider");
  return ui;
}

/** Re-render charts when the theme changes (they read CSS variables at draw time). */
export const useThemeKey = () => useUI().theme;
