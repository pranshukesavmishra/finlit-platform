// A company listed only on the BSE has its 6-digit BSE code as its symbol (for example 526775). Lists show such a company by its NAME, never by the bare number;
// the code stays in the address (/stocks/526775) and on the company's own page. One rule for every list, so a new list cannot forget it.
type Co = { symbol: string; name?: string | null; exchange?: string | null };

export const isBseCode = (symbol: string): boolean => /^\d+$/.test(symbol);
/** What to print as the bold title of a company: its name for a BSE-only company, else its symbol. With no name on file the code is shown (see `codeNote`). */
export const titleOf = (r: Co): string => (isBseCode(r.symbol) && r.name ? r.name : r.symbol);
/** The small line under the title: the company name, left out when the name is already the title. */
export const subOf = (r: Co): string | null => (isBseCode(r.symbol) && r.name ? null : r.name || null);
/** The reason to show on hover when a BSE code had to stay the title because no name is stored. */
export const codeNote = (r: Co): string | undefined => (isBseCode(r.symbol) && !r.name ? "BSE code. The company name is not in our data yet." : undefined);
/** The exchange a company is listed on, when known: the row's own field (from the company record), else BSE for a numeric symbol. Null when neither says. */
export const exchangeOf = (r: Co): "NSE" | "BSE" | null => (r.exchange === "NSE" || r.exchange === "BSE" ? r.exchange : isBseCode(r.symbol) ? "BSE" : null);
/** True for a company listed on the BSE only (no NSE listing): the ones the "NSE-listed only" option leaves out. */
export const isBseOnly = (r: Co): boolean => exchangeOf(r) === "BSE";
/** The small tag for a BSE-only company: the exchange and its scrip code (the code is the symbol for such a company). Null for an NSE-listed one. */
export const exchangeTag = (r: Co): string | null => (isBseOnly(r) ? (isBseCode(r.symbol) ? `BSE only, code ${r.symbol}` : "BSE only") : null);
