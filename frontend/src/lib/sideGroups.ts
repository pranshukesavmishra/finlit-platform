// Identity of each group in the left rail: a badge icon (from lib/icons.tsx) and a palette token (--k1..--k8, see styles/finlit.css).
// The group titles are the ones AppShell builds from lib/nav.ts, plus Overview, Your workspace, Learn and Account.
export type SideBadge = { icon: string; tone: string };

export const SIDE_BADGES: Record<string, SideBadge> = {
  "Overview": { icon: "grid", tone: "--k1" },
  "Find stocks": { icon: "search", tone: "--k3" },
  "Analyse a company": { icon: "layers", tone: "--k7" },
  "Investment calculators": { icon: "gauge", tone: "--k2" },
  "Charts": { icon: "line", tone: "--k5" },
  "Markets": { icon: "activity", tone: "--k1" },
  "News & events": { icon: "bell", tone: "--k8" },
  "Funds": { icon: "pie", tone: "--k3" },
  "Your workspace": { icon: "wallet", tone: "--k7" },
  "Gold dashboards": { icon: "crown", tone: "--k2" },
  "Learn": { icon: "book", tone: "--k5" },
  "Account": { icon: "users", tone: "--k1" },
};
const FALLBACK: SideBadge = { icon: "grid", tone: "--k1" };
export const badgeFor = (title: string): SideBadge => SIDE_BADGES[title] ?? FALLBACK;
