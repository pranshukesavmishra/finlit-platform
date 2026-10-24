// Query builder: types for the server's answers, the calls, and the pure helpers (autocomplete, underline marks, one-click fixes, the
// "Add a condition" text). The language itself lives on the server (backend/finlit/screener/ql.py): this file only helps a person write it.
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiSend, type ApiError } from "./api";
import { score } from "./metricSearch";
import type { Plan } from "./ui";

export type Fix = { label: string; start: number; end: number; text: string };
export type Problem = {
  code: string; severity: "error" | "warning"; message: string; start: number; end: number; line: number; col: number; text: string; fixes: Fix[];
  suggestions?: { key: string; label: string }[]; seeAll?: boolean; plan?: Plan; name?: string; key?: string;
};
export type Reading = { type: "cond"; text: string } | { type: "and" | "or"; items: Reading[] };
export type UsedRatio = { key: string; label: string; unit: string; unitLabel: string; tier: Plan; locked: boolean; digits: number };
export type Validation = {
  ok: boolean; errors: Problem[]; warnings: Problem[]; metrics: UsedRatio[]; conditions: number; plan: Plan; reading?: Reading; canonical?: string;
  limits: { chars: number; conditions: number };
};
export type Ratio = UsedRatio & {
  group: string; groupLabel: string; better: "higher" | "lower" | "none"; names: string[]; definition: string; example: string;
  stats: { min: number; p10: number; p50: number; p90: number; max: number } | null;
};
export type Example = { id: string; title: string; about: string; query: string; plan: Plan; locked: boolean };
export type Ratios = {
  ratios: Ratio[]; operators: { op: string; say: string }[]; examples: Example[]; plan: Plan; aliases: number; total: number; withReport: number; defaultColumns: string[];
  limits: { chars: number; conditions: number; rows: number | null; export: boolean };
  recentResults: { available: boolean; quarterEnd: number | null; companies: number };
};
export type LeftOut = { key: string; label: string; known: number; missing: number; leftOut: number };
export type Row = { symbol: string; name: string; sector: string | null; cap: string | null; band: string | null; full: boolean; v: Record<string, number | null> };
export type RunOk = {
  ok: true; total: number; offset: number; limit: number; capped: boolean; columns: string[]; sort: { key: string; dir: "asc" | "desc" }; rows: Row[]; warnings: Problem[];
  reading: Reading; canonical: string; universe: number; withReport: number; leftOut: { total: number; divisionByZero: number; metrics: LeftOut[] };
  recent: { quarterEnd: number; dropped: number; reported: number } | null; updatedAt: string; took: number;
};
export type RunBad = { ok: false; errors: Problem[]; warnings: Problem[] };
export type RunBody = { query: string; sort?: { key: string; dir: "asc" | "desc" }; columns: string[]; recent: boolean; offset: number; limit: number };
export type Basket = {
  id: string; name: string; query: string; note: string | null; columns: string[]; sort: { key: string; dir: "asc" | "desc" } | null; recent: boolean; createdAt: string; updatedAt: string;
  count: number | null; countedAt: string | null; status: "ok" | "locked" | "invalid"; stale: boolean; leftOut?: number;
};

// ------------------------------------------------------------------------------------------------------------------------------ calls
export const useRatios = () => useQuery<Ratios, ApiError>({ queryKey: ["ql-ratios"], queryFn: () => apiGet<Ratios>("/api/screener/ql/ratios"), staleTime: 300_000, retry: 1 });
export const validateQuery = (query: string) => apiSend<Validation>("POST", "/api/screener/ql/validate", { query });
export const runQuery = (body: RunBody) => apiSend<RunOk | RunBad>("POST", "/api/screener/ql/run", body);
export const useBaskets = (enabled: boolean) => useQuery<{ baskets: Basket[]; max: number; plan: Plan }, ApiError>({
  queryKey: ["baskets"], queryFn: () => apiGet("/api/screener/baskets"), enabled, staleTime: 30_000, placeholderData: keepPreviousData, retry: false,
});
export const useBasket = (id: string | null) => useQuery<{ basket: Basket }, ApiError>({ queryKey: ["basket", id], queryFn: () => apiGet(`/api/screener/baskets/${id}`), enabled: !!id, retry: false });
export type BasketInput = { name: string; query: string; note?: string | null; columns?: string[]; sort?: { key: string; dir: "asc" | "desc" } | null; recent?: boolean };
export function useBasketActions() {
  const qc = useQueryClient();
  const done = () => { qc.invalidateQueries({ queryKey: ["baskets"] }); qc.invalidateQueries({ queryKey: ["basket"] }); };
  return {
    create: useMutation({ mutationFn: (b: BasketInput) => apiSend<{ basket: Basket }>("POST", "/api/screener/baskets", { ...b, sort: b.sort ?? undefined }), onSuccess: done }),
    update: useMutation({ mutationFn: ({ id, ...b }: Partial<BasketInput> & { id: string }) => apiSend<{ basket: Basket }>("PUT", `/api/screener/baskets/${id}`, { ...b, sort: b.sort ?? undefined }), onSuccess: done }),
    duplicate: useMutation({ mutationFn: ({ id, name }: { id: string; name?: string }) => apiSend<{ basket: Basket }>("POST", `/api/screener/baskets/${id}/duplicate`, { name }), onSuccess: done }),
    remove: useMutation({ mutationFn: (id: string) => apiSend("DELETE", `/api/screener/baskets/${id}`), onSuccess: done }),
  };
}

// ------------------------------------------------------------------------------------------------------------------------------ fixes
/** Apply a server-suggested repair to the text. Returns the new text and where the caret goes (just after the inserted piece). */
export function applyFix(text: string, fix: Pick<Fix, "start" | "end" | "text">): { text: string; caret: number } {
  const s = Math.max(0, Math.min(fix.start, text.length)), e = Math.max(s, Math.min(fix.end, text.length));
  let insert = fix.text;
  // removing a word leaves a double space: tidy it
  let next = text.slice(0, s) + insert + text.slice(e);
  if (insert === "") next = next.replace(/[ \t]{2,}/g, " ").replace(/[ \t]+\n/g, "\n").replace(/^[ \t]+|[ \t]+$/g, "");
  return { text: next, caret: Math.min(next.length, s + insert.length) };
}

/** Replace the exact text of an unknown name with a suggested real one. */
export const replaceRange = (text: string, p: Pick<Problem, "start" | "end">, with_: string) => applyFix(text, { start: p.start, end: p.end, text: with_ });

// ------------------------------------------------------------------------------------------------------------------------------ underline marks
export type Seg = { text: string; problem?: Problem };
/** Cut the text into pieces for the underline layer under the textarea. A zero-width problem (a missing AND) marks the character after it. */
export function segments(text: string, problems: Problem[]): Seg[] {
  const marks = problems
    .map((p) => {
      let s = Math.max(0, Math.min(p.start, text.length)), e = Math.max(s, Math.min(p.end, text.length));
      if (e <= s) { if (s < text.length && text[s] !== "\n") e = s + 1; else if (s > 0) { s = s - 1; e = s + 1; } }
      return { p, s, e };
    })
    .filter((m) => m.e > m.s)
    .sort((a, b) => a.s - b.s || (a.p.severity === "error" ? -1 : 1));
  const out: Seg[] = [];
  let at = 0;
  for (const m of marks) {
    if (m.s < at) continue;                                  // overlaps an earlier mark: the first one wins
    if (m.s > at) out.push({ text: text.slice(at, m.s) });
    out.push({ text: text.slice(m.s, m.e), problem: m.p });
    at = m.e;
  }
  if (at < text.length) out.push({ text: text.slice(at) });
  return out;
}

// ------------------------------------------------------------------------------------------------------------------------------ autocomplete
export type Completion = { kind: "metric" | "operator" | "connector" | "none"; start: number; end: number; prefix: string };
const NONE: Completion = { kind: "none", start: 0, end: 0, prefix: "" };
const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
/** What could be typed at the caret: a ratio name, a comparison, or AND / OR. Looks only at the current line, up to the caret. */
export function completionAt(text: string, caret: number, names: Set<string>): Completion {
  const lineStart = text.lastIndexOf("\n", caret - 1) + 1;
  const line = text.slice(lineStart, caret);
  // the part after the last joiner / comparison / bracket / plus / times is the phrase being typed
  let cut = 0;
  for (const b of line.matchAll(/[(<>=!+*]|\s-\s|\b(?:and|or)\b|&&|\|\||\)/gi)) cut = (b.index ?? 0) + b[0].length;
  if (line[cut - 1] === ")") return NONE;
  const phrase = line.slice(cut), trimmed = phrase.trim();
  if (!trimmed) return NONE;                                   // nothing typed yet: suggestions wait for a letter (or Ctrl+Space)
  const before = line.slice(0, line.length - phrase.length);
  const rhs = /[<>=]\s*$/.test(before);                        // after a comparison: a number or a second ratio
  const num = /^[-+]?[\d.,]+\s*(%|cr|crore|crores|lakh|x|times|days)?$/i;
  if (rhs && num.test(trimmed)) return /\s$/.test(phrase) ? { kind: "connector", start: caret, end: caret, prefix: "" } : NONE;
  if (/\s$/.test(phrase) && names.has(norm(trimmed))) return { kind: rhs ? "connector" : "operator", start: caret, end: caret, prefix: "" };
  if (/^[\d.,]+$/.test(trimmed)) return NONE;
  return { kind: "metric", start: lineStart + line.length - phrase.length + (phrase.length - phrase.trimStart().length), end: caret, prefix: trimmed };
}

/** The ratios that fit what has been typed, best first. Names, labels and short forms (P/E, mcap) all count. */
export function rankRatios<T extends { label: string; names: string[]; key: string }>(items: T[], query: string, limit = 8): T[] {
  const q = query.trim();
  if (!q) return items.slice(0, limit);
  return items.map((r, i) => ({ r, i, s: score(q, r.label, r.names) })).filter((x) => x.s > 0).sort((a, b) => b.s - a.s || a.i - b.i).slice(0, limit).map((x) => x.r);
}

/** All the names the page knows, normalised, so "ROE " is seen as a finished name. */
export const nameSet = (ratios: Ratio[]): Set<string> => new Set(ratios.flatMap((r) => [r.label, ...r.names].map(norm)));

export const CONNECTORS = [{ op: "AND", say: "and also" }, { op: "OR", say: "or else" }];

/** Put the chosen suggestion into the text. Returns the new text and the caret. */
export function acceptCompletion(text: string, c: Completion, insert: string): { text: string; caret: number } {
  const add = insert + " ";
  const next = text.slice(0, c.start) + add + text.slice(c.end);
  return { text: next, caret: c.start + add.length };
}

// ------------------------------------------------------------------------------------------------------------------------------ "Add a condition"
export const OPS = [{ op: ">", say: "is greater than" }, { op: ">=", say: "is at least" }, { op: "<", say: "is less than" }, { op: "<=", say: "is at most" }, { op: "=", say: "is equal to" }, { op: "!=", say: "is not equal to" }];

/** What to put after the number for a ratio, so the text says what is meant: "500 Cr", "15%". Plain for everything else. */
export function unitSuffix(unit: string): string {
  return unit === "Cr" ? " Cr" : unit === "%" ? "%" : "";
}
export const unitHint = (r: Pick<Ratio, "unit" | "unitLabel">): string => ({ Cr: "in ₹ crore, e.g. 500 means ₹500 crore", "%": "a percentage, e.g. 15 means 15%", x: "a multiple, e.g. 15 means 15 times", Rs: "in rupees", d: "in days", pts: "in points", n: "a count", flag: "yes or no" } as Record<string, string>)[r.unit] ?? r.unitLabel;

/** "1,00,000", "12.5", "₹ 2,000" -> a clean number string, or null if it is not a number. */
export function cleanNumber(raw: string): string | null {
  const t = raw.replace(/[,\s₹]/g, "").replace(/(%|cr|crore|crores)$/i, "");
  return /^-?(\d+\.?\d*|\.\d+)$/.test(t) ? t : null;
}

export type ConditionDraft = { ratio: Ratio | null; op: string; value: string; yes?: boolean };
/** Why the helper cannot add this condition yet, in a sentence; null when it can. */
export function draftProblem(d: ConditionDraft): string | null {
  if (!d.ratio) return "Pick a ratio first.";
  if (d.ratio.unit === "flag") return null;
  if (d.value.trim() === "") return `Type a number for ${d.ratio.label}.`;
  if (cleanNumber(d.value) == null) return `“${d.value.trim()}” is not a number. Use digits only, like 15 or 1,000.`;
  if (d.ratio.unit === "%" && /cr|crore/i.test(d.value)) return `${d.ratio.label} is a percentage, so “Cr” does not fit.`;
  return null;
}
/** The query text for the helper's choices: "ROE > 15%", "Market cap > 500 Cr", "Pays a dividend = yes". */
export function conditionText(d: ConditionDraft): string {
  if (!d.ratio) return "";
  if (d.ratio.unit === "flag") return `${d.ratio.label} = ${d.yes === false ? "no" : "yes"}`;
  const n = cleanNumber(d.value);
  return `${d.ratio.label} ${d.op} ${n ?? d.value.trim()}${n != null ? unitSuffix(d.ratio.unit) : ""}`;
}
/** Add a condition to the query: on its own line (all must match), or joined with OR to the last line. */
export function addCondition(text: string, cond: string, joiner: "AND" | "OR" = "AND"): { text: string; caret: number } {
  const body = text.replace(/\s+$/, "");
  if (!body) return { text: cond, caret: cond.length };
  const next = joiner === "OR" ? `${body} OR ${cond}` : `${body}\n${cond}`;
  return { text: next, caret: next.length };
}

// ------------------------------------------------------------------------------------------------------------------------------ words for the page
export const quarterLabel = (ymd: number | null | undefined): string => {
  if (!ymd) return "";
  const s = String(ymd), mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][+s.slice(4, 6) - 1];
  return `${+s.slice(6, 8)} ${mon} ${s.slice(0, 4)}`;
};

/** One sentence per ratio about the companies left out because that figure is unknown. */
export function leftOutLines(items: LeftOut[], total: number): string[] {
  return items.filter((m) => m.leftOut > 0).sort((a, b) => b.leftOut - a.leftOut).map((m) =>
    `${m.label} is not known for ${m.missing.toLocaleString("en-IN")} of ${total.toLocaleString("en-IN")} companies; ${m.leftOut.toLocaleString("en-IN")} of them were left out only because of it.`);
}

export const basketNameProblem = (name: string, existing: string[], except?: string): string | null => {
  const n = name.trim().replace(/\s+/g, " ");
  if (!n) return "Give the basket a name.";
  if (n.length > 80) return "Keep the name to 80 characters.";
  if (existing.some((e) => e.toLowerCase() === n.toLowerCase() && e !== except)) return `You already have a basket called “${n}”.`;
  return null;
};

/** Short plain text for a basket's query on a card: lines joined with “ · ”. */
export const queryPreview = (q: string, max = 140): string => { const t = q.trim().split(/\n+/).join("  ·  "); return t.length > max ? t.slice(0, max - 1) + "…" : t; };

/** A link that opens the builder with a query already in the box. */
export const builderLink = (query: string) => `/query-builder?q=${encodeURIComponent(query)}`;
