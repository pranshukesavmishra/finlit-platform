// Company brief (backend/finlit/company_brief): the About section written from the company's own filings, every line cited. The page reads the PUBLISHED brief only;
// when there is none it shows the reason the server gives. Nothing here judges a company.
import { useQuery } from "@tanstack/react-query";
import { ApiError, apiGet } from "./api";

export type Cite = { doc: string; page?: number | null; needles?: string[] };
export type Doc = { title: string; date?: string | null; kind: string; url?: string };
export type Line = { text: string; cites: Cite[] };
export type Figure = { label: string; value: string; note?: string; cites: Cite[] };
export type GroupRow = { name: string; what?: string; stake: number; note?: string; cites: Cite[] };
export type Segment = { name: string; what: string; what_cites: Cite[]; points: Line[] };
export type MixRow = { name: string; value_cr: number; share_pct?: number };
export type MixSide = { total_cr?: number; rows: MixRow[]; cites: Cite[]; basis?: string };
export type Recent = { date: string; title: string; text: string; cites: Cite[] };
export type Brief = {
  symbol: string; name: string; as_of: string; status?: string; template?: string; docs: Record<string, Doc>; about: Line[]; key_figures?: Figure[];
  group?: { as_of?: string; rows: GroupRow[] }; segments: Segment[]; mix?: { period?: string; ebitda?: MixSide; revenue?: MixSide }; recent: Recent[]; gaps?: string[]; disclaimer?: string;
};
export type Checks = { date?: string | null; citations: number; passed: number; unchecked: number; fixed: string[]; method?: string | null };
export type BriefReply =
  | { symbol: string; name?: string | null; state: "published"; brief: Brief; asOf: string; reviewedAt: string | null; stale: boolean; waiting?: boolean; changes?: { since: string | null; now: string | null; parts: string[] } | null;
      checks: Checks; chips: Record<string, string>; disclaimer: string; compliance: string }
  | { symbol: string; name?: string | null; state: "empty"; code: string; reason: string; disclaimer: string; compliance: string };

export const COMPLIANCE = "Describes the company's financial health from its filings and prices; not a recommendation. Information only, not investment advice.";
export const PART_NAMES: Record<string, string> = { about: "what the company does", key_figures: "key figures", group: "the group table", segments: "the businesses", mix: "where the money comes from", recent: "recent developments" };

export const useCompanyBrief = (symbol: string, enabled = true) => useQuery<BriefReply, ApiError>({
  queryKey: ["company-brief", symbol], enabled: enabled && !!symbol, staleTime: 10 * 60_000, retry: false,
  queryFn: () => apiGet<BriefReply>(`/api/stocks/${encodeURIComponent(symbol)}/brief`) });

/** The link a citation chip opens: the filing at the cited page. Only https addresses are ever linked. */
export function citeUrl(doc: Doc | undefined, page?: number | null): string | null {
  if (!doc?.url || !/^https:\/\//i.test(doc.url)) return null;
  return page ? `${doc.url.split("#")[0]}#page=${page}` : doc.url;
}

/** Share of the total for a bar: the stated share when the brief gives one, else the row's part of the rows shown. */
export function shares(side?: MixSide): { name: string; value: number; pct: number }[] {
  const rows = side?.rows ?? [];
  let sum = 0;
  for (const r of rows) sum += r.value_cr || 0;
  return rows.map((r) => ({ name: r.name, value: r.value_cr, pct: r.share_pct ?? (sum > 0 ? (100 * r.value_cr) / sum : 0) }));
}

export const crore = (n: number) => "₹" + new Intl.NumberFormat("en-IN").format(Math.round(n)) + " crore";

/** Every filing the brief cites, with the pages cited in it (sorted), so a reader can open each one. */
export function citedPages(b: Brief): { key: string; doc: Doc; pages: number[] }[] {
  const seen = new Map<string, Set<number>>();
  const walk = (o: unknown): void => {
    if (Array.isArray(o)) o.forEach(walk);
    else if (o && typeof o === "object") for (const [k, v] of Object.entries(o)) {
      if ((k === "cites" || k === "what_cites") && Array.isArray(v)) for (const c of v as Cite[]) { if (c?.doc) { const s = seen.get(c.doc) ?? new Set<number>(); if (c.page) s.add(c.page); seen.set(c.doc, s); } }
      else if (k !== "docs") walk(v);
    }
  };
  walk(b);
  return [...seen.entries()].filter(([k]) => b.docs?.[k]).map(([key, s]) => ({ key, doc: b.docs[key], pages: [...s].sort((a, c) => a - c) }));
}

/** "Reliance Industries Ltd" -> "Reliance", for "Reliance's share of each company". */
export const shortName = (name: string) => name.replace(/\b(ltd|limited|inc|corp|corporation|industries|company|co)\b\.?/gi, "").replace(/\s+/g, " ").trim().split(" ")[0] || name;
