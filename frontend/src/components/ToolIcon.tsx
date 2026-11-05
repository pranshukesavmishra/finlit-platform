import type { ReactNode } from "react";
import { TOOL_ICONS, TIER_LABEL, type ToolId } from "../lib/toolIcons";
import "../styles/tool-icon.css";

/** The shared round tool badge: a disc with a tier ring (gold with a soft glow, blue for Free, silver for Silver) and a 1.75px line icon with one gold accent. Decorative by default (the title sits beside it); pass `label` to make it a named image. */
const A = "var(--ti-accent)";
const G: Record<ToolId, ReactNode> = {
  "stock-radar": <><circle cx="12" cy="12" r="8.5" /><circle cx="12" cy="12" r="4.5" /><circle cx="12" cy="12" r="1.4" fill={A} stroke={A} /></>,
  "score-screener": <><path d="M4 5h16l-6 7.5V19l-4-2v-4.5z" /><path d="M9 7.5h6" stroke={A} /></>,
  "etf-explorer": <><circle cx="12" cy="12" r="8.5" /><path d="M12 3.5V12h8.5" /><path d="M12 12l-6 6" /><path d="M12 3.5A8.5 8.5 0 0 1 20.5 12H12z" fill={A} fillOpacity=".35" stroke={A} /></>,
  "fund-finder": <><circle cx="10.5" cy="10.5" r="6.5" /><path d="M15.5 15.5L20 20" /><path d="M8 8h5M8 10.5h5M8.5 8c3 0 3 3-1 3l3 3" stroke={A} strokeWidth="1.4" /></>,
  "fund-health-check": <><path d="M12 3l7.5 3v5.5c0 4.5-3.2 7.8-7.5 9.5-4.3-1.7-7.5-5-7.5-9.5V6z" /><path d="M8.5 12l2.5 2.5 4.5-5" stroke={A} /></>,
  "chart-studio": <><path d="M7 4v3M7 14v3M7 7h0" /><rect x="5" y="7" width="4" height="7" rx=".8" /><path d="M16 7v3M16 17v3" /><rect x="14" y="10" width="4" height="7" rx=".8" fill={A} fillOpacity=".4" stroke={A} /></>,
  "peer-compare": <><path d="M12 3.5l8 5.8-3 9.4H7l-3-9.4z" /><path d="M12 8l4.5 3.3-1.7 5H9.2l-1.7-5z" opacity=".6" /><circle cx="12" cy="8" r="1.4" fill={A} stroke={A} /></>,
  "company-health-score": <><path d="M12 20s-7.5-4.6-7.5-10A4.3 4.3 0 0 1 12 7.2 4.3 4.3 0 0 1 19.5 10c0 5.4-7.5 10-7.5 10z" /><path d="M5 12h3.5l1.5-3 2.5 6 1.5-3H19" stroke={A} /></>,
  "company-financials": <><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v4h4" /><path d="M9 11h6M9 14h6M9 17h3" stroke={A} /></>,
  "deep-dive-report": <><path d="M6 3h8l4 4v14H6z" /><path d="M14 3v4h4" /><path d="M9 17v-3M12 17v-6M15 17v-4.5" stroke={A} /></>,
  "fair-value-calculator": <><rect x="5" y="3" width="14" height="18" rx="2" /><rect x="8" y="6" width="8" height="3.5" rx=".6" /><path d="M8.5 13h.01M12 13h.01M15.5 13h.01M8.5 16.5h.01M12 16.5h.01" strokeWidth="2.2" strokeLinecap="round" /><path d="M15.5 16.5h.01" strokeWidth="2.2" strokeLinecap="round" stroke={A} /></>,
  "forecast-builder": <><path d="M4 19h16" /><path d="M5 16l4.5-4.5 3 3L19 8" /><path d="M15 8h4v4" stroke={A} /></>,
  "finance-calculators": <><path d="M4 8h16M4 16h16" /><circle cx="9" cy="8" r="2.3" fill="var(--ti-disc)" /><circle cx="15" cy="16" r="2.3" fill="var(--ti-disc)" stroke={A} /></>,
  "option-chain": <><rect x="4" y="5" width="16" height="14" rx="2" /><path d="M4 10h16M10 5v14" /><rect x="10" y="10" width="10" height="4.5" fill={A} fillOpacity=".4" stroke={A} /></>,
  "watchlists": <><path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z" /><circle cx="12" cy="12" r="2.8" fill={A} stroke={A} /></>,
  "portfolio-check-up": <><rect x="3.5" y="7.5" width="17" height="12" rx="2" /><path d="M9 7.5V6a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 15 6v1.5" /><path d="M9.5 13.5l2 2 3.5-4" stroke={A} /></>,
  "alerts": <><path d="M6 17V11a6 6 0 0 1 12 0v6l1.5 2h-15z" /><path d="M10 21h4" /><circle cx="18" cy="5" r="1.9" fill={A} stroke={A} /></>,
  "compare-funds": <><path d="M4 8h15M15.5 4.5L19 8l-3.5 3.5" /><path d="M20 16H5M8.5 12.5L5 16l3.5 3.5" stroke={A} /></>,
  "theme-tracker": <><path d="M12 3.5l8.5 4.5-8.5 4.5L3.5 8z" /><path d="M3.5 12.5l8.5 4.5 8.5-4.5" /><path d="M3.5 17l8.5 4.5 8.5-4.5" stroke={A} /></>,
  "market-dashboard": <><rect x="4" y="4" width="7" height="7" rx="1.5" /><rect x="13" y="4" width="7" height="7" rx="1.5" /><rect x="4" y="13" width="7" height="7" rx="1.5" /><rect x="13" y="13" width="7" height="7" rx="1.5" fill={A} fillOpacity=".4" stroke={A} /></>,
  "newsroom": <><path d="M5 4h11v16H6.5A1.5 1.5 0 0 1 5 18.5z" /><path d="M16 8h3v10.5a1.5 1.5 0 0 1-3 0" /><path d="M8 8h5M8 11.5h5" /><path d="M8 15h5" stroke={A} /></>,
  "investor-circle": <><circle cx="9" cy="8.5" r="3" /><path d="M3.5 19c0-3.2 2.4-5.5 5.5-5.5s5.5 2.3 5.5 5.5" /><circle cx="17" cy="9.5" r="2.3" stroke={A} /><path d="M16.5 14c2.5.2 4 2 4 4.5" stroke={A} /></>,
};

export type ToolIconSize = "sm" | "md" | "lg";
export function ToolIcon({ id, size = "md", label }: { id: ToolId; size?: ToolIconSize; label?: string }) {
  const m = TOOL_ICONS[id];
  return (
    <span className={`ti ti-${size} ti-${m.tier}`} {...(label ? { role: "img", "aria-label": label } : { "aria-hidden": true })} data-tier={TIER_LABEL[m.tier]}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" focusable="false">{G[id]}</svg>
    </span>
  );
}
