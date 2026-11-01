// Identity of each group in the left rail: a quiet line icon (from lib/icons.tsx); the rail uses one neutral palette, so there is no per-group colour.
// The group titles are the ones AppShell builds from lib/nav.ts, plus Overview, Your workspace, Learn and Account.
export type SideBadge = { icon: string };

export const SIDE_BADGES: Record<string, SideBadge> = {
  "Overview": { icon: "grid" },
  "Find stocks": { icon: "search" },
  "Analyse a company": { icon: "layers" },
  "Investment calculators": { icon: "gauge" },
  "Charts": { icon: "line" },
  "Markets": { icon: "activity" },
  "News & events": { icon: "bell" },
  "Funds": { icon: "pie" },
  "Your workspace": { icon: "wallet" },
  "Gold dashboards": { icon: "crown" },
  "Learn": { icon: "book" },
  "Account": { icon: "users" },
};
const FALLBACK: SideBadge = { icon: "grid" };
export const badgeFor = (title: string): SideBadge => SIDE_BADGES[title] ?? FALLBACK;
