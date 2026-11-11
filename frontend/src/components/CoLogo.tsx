// A company's logo beside its name, everywhere a company is named (task 71). One shared list (the search list's logo paths, loaded once and kept) serves every place on the page;
// a company without a logo, or a logo that fails to load, shows the same coloured initials tile the site always used. Decorative (alt=""): the name next to it says who it is.
import { useContext } from "react";
import { QueryClientContext, useQuery } from "@tanstack/react-query";
import { apiGet, type ApiError } from "../lib/api";
import type { Quotes } from "../lib/globalSearch";
import { Logo } from "./search/parts";

/** symbol -> logo path, from the one search-quotes request the whole site shares. */
export function useLogoMap(enabled = true): Map<string, string> | undefined {
  // A tree without the data provider (a unit test of one table) simply has no logos: the initials tile shows. The provider never comes or goes in a live page, so the hook order is stable.
  const qc = useContext(QueryClientContext);
  if (!qc) return undefined;
  // eslint-disable-next-line react-hooks/rules-of-hooks
  return useQuery<Quotes, ApiError, Map<string, string>>({
    queryKey: ["search-quotes"], queryFn: () => apiGet("/api/search/quotes"), enabled, staleTime: 300_000, gcTime: 600_000, retry: 1,
    select: (q) => { const m = new Map<string, string>(); for (const r of q?.rows || []) if (r[6]) m.set(String(r[0]).toUpperCase(), r[6]); return m; },
  }).data;
}

/** The logo (or initials) of one company. `size` in px: 20 to 24 in tables and lists, 32 to 40 in cards, 48 or more in a company header. */
export function CoLogo({ symbol, name, size = 24, inline = false }: { symbol: string; name?: string | null; size?: number; inline?: boolean }) {
  const m = useLogoMap();
  const logo = <Logo src={m?.get(symbol.toUpperCase()) ?? null} name={name || symbol} kind="stock" size={size} />;
  return inline ? <span className="cl-in">{logo}</span> : logo;   // `inline`: sits in a line of text, centred on it, with a gap before the name
}
