import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./api";

export type Ipo = {
  id: number; name: string; symbol: string | null; kind: "mainboard" | "sme"; sector: string | null; status: "upcoming" | "open" | "closed" | "listed";
  openDate: string; closeDate: string; listingDate: string | null; priceLow: number | null; priceHigh: number | null; lotSize: number | null;
  issueSizeCr: number | null; listingPrice: number | null; note: string | null; link: string | null;
};
/** `fresh` skips the browser cache (the admin console must see its own changes at once). */
export const useIpos = (fresh = false) => useQuery({ queryKey: ["ipos", fresh], queryFn: () => apiGet<{ ipos: Ipo[] }>("/api/ipos", fresh ? { cache: "reload" } : undefined).then((d) => d.ipos), staleTime: 120_000, retry: 1 });
/** Smallest application: one lot at the top of the price band. */
export const minInvest = (i: Ipo) => (i.priceHigh && i.lotSize ? i.priceHigh * i.lotSize : null);
export const listingGain = (i: Ipo) => (i.listingPrice && i.priceHigh ? ((i.listingPrice - i.priceHigh) / i.priceHigh) * 100 : null);
