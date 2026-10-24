// Which accounts a company's page shows: consolidated (the group) or standalone (the parent alone). Chosen per company, kept for the session.
import { useSyncExternalStore } from "react";

export type Basis = "consolidated" | "standalone";
const chosen = new Map<string, Basis>();
const subs = new Set<() => void>();
let version = 0;

export function basisOf(symbol: string): Basis { return chosen.get(symbol.toUpperCase()) ?? "consolidated"; }
export function setBasis(symbol: string, b: Basis) {
  const k = symbol.toUpperCase();
  if (basisOf(k) === b) return;
  if (b === "consolidated") chosen.delete(k); else chosen.set(k, b);
  version += 1;
  subs.forEach((f) => f());
}
/** The basis for one company, re-rendering when it changes. */
export function useBasis(symbol: string): Basis {
  useSyncExternalStore((f) => { subs.add(f); return () => { subs.delete(f); }; }, () => version, () => 0);
  return basisOf(symbol);
}
/** `?statement=standalone` joined onto a path that may already carry a query; nothing for the default. */
export function withBasis(path: string, b: Basis): string {
  return b === "consolidated" ? path : path + (path.includes("?") ? "&" : "?") + "statement=standalone";
}
