import suggestions from "../content/questionSuggestions.json";

export type BankSuggestion = { id: string; text: string };

/** The FinLit question-bank questions the assistant offers on a company page, with that company filled in ("What is {company}'s ..." becomes "What is RELIANCE's ...").
 *  The wording is the bank's own (content/questionSuggestions.json is built from it by scripts/build_question_bank.py), so a tap is exactly a predefined question. */
export function bankSuggestions(pathname: string, limit = 5): BankSuggestion[] {
  const m = /^\/stocks\/([A-Za-z0-9&.\-]{1,20})\/?$/.exec(pathname);
  if (!m) return [];
  const sym = decodeURIComponent(m[1]).toUpperCase();
  return suggestions.company.slice(0, limit).map((q) => ({ id: q.id, text: q.text.replace(/\{company\}/g, sym).replace(/\{n\}/g, "5") }));
}
