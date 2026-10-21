// Demo portfolio for previews and tests ONLY: invented names and numbers, never shown as real data (the section says so through its source line).
import type { Portfolio } from "./types";

const mk = (name: string, sector: string, pct: number, prevPct: number | null, stockSymbol: string | null = null) =>
  ({ name, isin: null, sector, assetClass: "equity", pct, qty: null, valueLakh: null, stockSymbol, prevPct, change: prevPct == null ? null : Math.round((pct - prevPct) * 100) / 100 });

export const DEMO_PORTFOLIO: Portfolio = {
  asOf: "2026-09-30", previousAsOf: "2026-08-31", source: "DEMO DATA, not a real fund", sourceUrl: null,
  holdings: [
    mk("Demo Bank Ltd", "Banks", 9.5, 9.1, "DEMOBANK"), mk("Demo Software Ltd", "IT", 7.2, 7.9), mk("Demo Motors Ltd", "Automobile", 5.1, null), mk("Demo Power Ltd", "Power", 4.4, 4.4),
    mk("Demo Pharma Ltd", "Healthcare", 3.9, 3.2), mk("Demo Cement Ltd", "Cement", 2.8, 3.1), mk("Demo Telecom Ltd", "Telecom", 2.2, 2.2), mk("Demo Finance Ltd", "Financial Services", 1.6, 1.5),
    mk("Demo Retail Ltd", "Consumer", 1.1, 1.0), mk("Demo Steel Ltd", "Metals", 0.9, 0.9), mk("Demo Paints Ltd", "Consumer", 0.7, 0.8), mk("Demo Textiles Ltd", "Textiles", 0.4, null),
  ],
  exited: [{ name: "Demo Chemicals Ltd", sector: "Chemicals", pct: 0, prevPct: 1.3 }],
  summary: { count: 12, top10Pct: 38.8, assetSplit: { equity: 39.8, debt: null, cash: null, other: null }, sectors: [{ sector: "Banks", pct: 9.5 }, { sector: "IT", pct: 7.2 }, { sector: "Automobile", pct: 5.1 }] },
};
