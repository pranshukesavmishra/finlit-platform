// What the company header and the slim company bar share: the plan the scores are drawn for, the Prism input, and the watchlist button's state and action.
import { useContext } from "react";
import { OpenAccess } from "../components/Gate";
import { useAuth } from "../lib/auth";
import { useUI, TIER } from "../lib/ui";
import { watch as wl, useWatchlist } from "../lib/watchlist";
import type { Summary } from "../lib/api";
import type { Plan, PrismInput } from "../lib/scoreBands";
import { notRatedReason } from "../lib/prism";
import { parseTechnical } from "../lib/prismTechnical";
import { LABEL, usePrismLatest } from "./PrismCard";

export function useReportHeader(s: Summary) {
  const { has, toast, upgrade } = useUI();
  const open = useContext(OpenAccess);
  const two = has("gold") || open;   // Gold sees the score and FinLit Prism side by side
  const { isAdmin } = useAuth();
  const prism = usePrismLatest(s.profile.symbol, s.meta.statement, two || isAdmin).data;
  const prismRep = prism?.kind === "report" ? prism.report : null;
  const effPlan: Plan = two || isAdmin ? "gold" : has("silver") ? "silver" : "basic";
  const tech = prismRep ? parseTechnical(prismRep.technicalAssessment) : null;
  const prismIn: PrismInput = !prism ? { kind: "loading" } : prism.kind === "report"
    ? { kind: "report", final: prism.report.rating.final, word: LABEL[prism.report.rating.label][0], status: prism.report.rating.status, parts: prism.report.rating.parts,
        short: tech && { score: tech.shortTerm.score, rating: tech.shortTerm.rating }, long: tech && { score: tech.longTerm.score, rating: tech.longTerm.rating },
        reason: notRatedReason(prism.report.rating), techAsOf: prism.report.technical?.asOf ?? tech?.asOf ?? null }
    : { kind: prism.kind };
  const wlState = useWatchlist(); void wlState;
  const p = s.profile, watch = wl.has(p.symbol);
  const need = (tier: "silver" | "gold", what: string) => { if (has(tier)) return true; upgrade(tier, `${what} come with the ${TIER[tier].n} plan.`); return false; };
  const toggleWatch = () => {
    if (!need("silver", "Watchlist and portfolio tracking")) return;
    const on = !watch;
    if (on) { if (!has("gold") && wl.total() >= 30) { upgrade("gold", "Silver holds up to 30 stocks; Gold holds up to 1,000."); return; } wl.add(p.symbol); } else wl.remove(p.symbol);
    toast(on ? `${p.nse || p.symbol} added to your watchlist.` : `${p.nse || p.symbol} removed from your watchlist.`);
  };
  return { open, two, isAdmin, prism, prismRep, effPlan, prismIn, watch, toggleWatch, need, has };
}
