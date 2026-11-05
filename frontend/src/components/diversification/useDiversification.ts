import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { apiSend, type ApiError } from "../../lib/api";
import type { Diversification, Horizon } from "./types";

/** The card's one request: share names, the benchmark and the horizon. Nothing else is ever sent (the server refuses any other field). */
export const useDiversification = (symbols: string[], horizon: Horizon, enabled = true) => {
  const key = [...new Set(symbols)].sort();
  return useQuery<Diversification, ApiError>({
    queryKey: ["diversification", key, horizon],
    queryFn: () => apiSend<Diversification>("POST", "/api/diversification", { symbols: key, benchmark: "NIF50", horizon }),
    enabled: enabled && key.length > 0, staleTime: 5 * 60_000, placeholderData: keepPreviousData, retry: (n, e) => (e.status >= 500 || e.status === 429 ? n < 1 : false),
  });
};
