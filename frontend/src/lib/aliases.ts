/** Retired trading symbols and where their data lives now (mirrors backend/finlit/aliases.py). */
export const SYMBOL_ALIASES: Record<string, string> = { TATAMOTORS: "TMPV" };
export const canon = (s: string) => SYMBOL_ALIASES[s.trim().toUpperCase()] || s;
/** Names an old broker file may use for a company that has since split: whoever held the old share now holds all of these. */
export const SPLIT_NAMES: Record<string, string[]> = { "TATAMOTORS": ["TMPV", "TMCV"], "TATA MOTORS": ["TMPV", "TMCV"], "TATA MOTORS LTD": ["TMPV", "TMCV"], "TATA MOTORS LIMITED": ["TMPV", "TMCV"] };
