import { useQuery } from "@tanstack/react-query";
import { apiSend, type ApiError } from "../lib/api";
import type { PageResponse } from "./types";

/** The page figures for the saved list (names only). The server keeps them per list and finished week, so the key is the sorted names. */
export function usePortfolioPage(symbols: string[], enabled: boolean) {
  const key = [...symbols].sort().join(",");
  return useQuery<PageResponse, ApiError>({
    queryKey: ["portfolio-page", key],
    queryFn: () => apiSend<PageResponse>("POST", "/api/portfolio/page", { symbols }),
    enabled: enabled && symbols.length > 0, retry: false, staleTime: 300_000,
  });
}
