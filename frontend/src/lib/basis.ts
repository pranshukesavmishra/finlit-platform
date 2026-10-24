// Which accounts a company's page shows: consolidated (the group) or standalone (the parent alone). Chosen per company, kept for the session.
import { useSyncExternalStore } from "react";

export type Basis = "consolidated" | "standalone";
const chosen = new Map<string, Basis>();
const explicit = new Set<string>();   // companies where the reader pressed a button: the page never changes the choice after that
const automatic = new Set<string>();  // companies where the page picked standalone itself, because consolidated history is short
const subs = new Set<() => void>();
let version = 0;

export function basisOf(symbol: string): Basis { return chosen.get(symbol.toUpperCase()) ?? "consolidated"; }
export function setBasis(symbol: string, b: Basis, auto = false) {
  const k = symbol.toUpperCase();
  if (auto) { if (explicit.has(k)) return; automatic.add(k); } else { explicit.add(k); automatic.delete(k); }
  if (basisOf(k) === b) return;
  if (b === "consolidated") chosen.delete(k); else chosen.set(k, b);
  version += 1;
  subs.forEach((f) => f());
}
export const wasAutomatic = (symbol: string) => automatic.has(symbol.toUpperCase());
export const wasChosen = (symbol: string) => explicit.has(symbol.toUpperCase());
/** The basis for one company, re-rendering when it changes. */
export function useBasis(symbol: string): Basis {
  useSyncExternalStore((f) => { subs.add(f); return () => { subs.delete(f); }; }, () => version, () => 0);
  return basisOf(symbol);
}
/** `?statement=standalone` joined onto a path that may already carry a query; nothing for the default. */
export function withBasis(path: string, b: Basis): string {
  return b === "consolidated" ? path : path + (path.includes("?") ? "&" : "?") + "statement=standalone";
}
