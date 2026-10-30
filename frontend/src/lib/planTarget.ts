import type { Plan } from "./auth";

/** The plan a Plans page link points at: /plans#gold or /plans?plan=gold (the hash wins). Anything else is null. */
export function planTarget(hash: string, search: string): Plan | null {
  const h = hash.replace(/^#(plan-)?/, "").toLowerCase();
  const q = (new URLSearchParams(search).get("plan") || "").toLowerCase();
  for (const v of [h, q]) if (v === "basic" || v === "silver" || v === "gold") return v;
  return null;
}
