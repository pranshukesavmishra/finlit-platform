// The macro backdrop per sector (backend/finlit/macro_sectors.py): the indicators as signals, each sector's 0 to 100 score with its label and reasons, and one
// company's sector. Gold, and shown to members only once the owner switches it on in the Console; the server answers 404 or 403 otherwise and the page shows nothing.
import { useQuery } from "@tanstack/react-query";
import { ApiError, apiGet } from "./api";

export type MacroSignal = { key: string; label: string; signal: number | null; reading: string | null; reason: string | null };
export type MacroSector = { key: string; name: string; score: number; label: string; raw: number; reasons: string[] };
export type MacroSectors = {
  asOf: string | null; signals: MacroSignal[]; sectors: MacroSector[]; disclaimer: string; method: string; switchedOn: boolean;
  company?: { symbol: string; sectorKey: string | null; sector: MacroSector | null; industry: string | null; reason: string | null };
};
export const useMacroSectors = (symbol = "", enabled = true) => useQuery<MacroSectors, ApiError>({
  queryKey: ["macro-sectors", symbol], enabled, staleTime: 30 * 60_000, retry: false,
  queryFn: () => apiGet<MacroSectors>(`/api/macro/sectors${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ""}`),
});
/** The colour family of a label: two greens, a neutral, two reds (the meaning, not decoration). */
export const labelTone = (label: string): "up2" | "up" | "flat" | "down" | "down2" =>
  label === "Strong tailwind" ? "up2" : label === "Tailwind" ? "up" : label === "Headwind" ? "down" : label === "Strong headwind" ? "down2" : "flat";
/** "Rate hikes -" -> "Rate hikes −" (a real minus sign for display). */
export const reasonText = (r: string) => r.replace(/ -$/, " −").replace(/-CPI/, "−CPI");
