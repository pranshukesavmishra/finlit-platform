// App-wide UI state: theme, plan preview, toasts.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

export type Plan = "basic" | "bronze" | "gold";
export const RANK: Record<Plan, number> = { basic: 0, bronze: 1, gold: 2 };
export const TIER: Record<Plan, { n: string; ic: string; tc: string }> = {
  basic: { n: "Basic", ic: "sprout", tc: "--t-basic" },
  bronze: { n: "Bronze", ic: "medal", tc: "--t-bronze" },
  gold: { n: "Gold", ic: "crown", tc: "--t-gold" },
};

type UI = {
  theme: "dark" | "light"; toggleTheme: () => void;
  plan: Plan; setPlan: (p: Plan) => void; has: (tier: Plan) => boolean;
  toast: (msg: string) => void;
};
const Ctx = createContext<UI | null>(null);

const read = (k: string) => { try { return localStorage.getItem(k); } catch { return null; } };
const write = (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } };

export function UIProvider({ children }: { children: ReactNode }) {
  const root = document.documentElement;
  const [theme, setTheme] = useState<"dark" | "light">((root.dataset.theme as "dark" | "light") || "dark");
  // Plan preview lets anyone see each tier before accounts ship; real entitlements come from the server.
  const [plan, setPlanState] = useState<Plan>(((read("finlit-plan") as Plan) || (root.dataset.plan as Plan) || "gold"));
  const [msg, setMsg] = useState<string | null>(null);
  const timer = useRef<number>(0);

  useEffect(() => { root.dataset.theme = theme; write("finlit-theme", theme); }, [theme, root]);
  useEffect(() => { root.dataset.plan = plan; write("finlit-plan", plan); }, [plan, root]);

  const toast = useCallback((m: string) => {
    setMsg(m); window.clearTimeout(timer.current); timer.current = window.setTimeout(() => setMsg(null), 3400);
  }, []);
  const value = useMemo<UI>(() => ({
    theme, toggleTheme: () => setTheme((t) => (t === "dark" ? "light" : "dark")),
    plan, setPlan: setPlanState, has: (tier) => RANK[plan] >= RANK[tier], toast,
  }), [theme, plan, toast]);

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
