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

export type BankGroup = { n: number; title: string; items: { id: string; text: string; needsSecondCompany?: boolean }[] };

const symbolOf = (pathname: string) => {
  const m = /^\/stocks\/([A-Za-z0-9&.\-]{1,20})\/?$/.exec(pathname);
  return m ? decodeURIComponent(m[1]).toUpperCase() : "";
};

/** Sectors whose companies report as lenders: only for them is the banks-and-NBFCs question (NIM, GNPA, NNPA, CASA) offered. */
export const isLenderSector = (sector?: string | null) => /\b(bank|banks|banking|nbfc|financ\w*|lending|lender|housing finance)\b/i.test(sector || "");

/** The founder's 40 company questions in their 12 groups, with the company filled in ("{company}" becomes the symbol). The question about two companies keeps XYZ for the user to replace.
 *  The banks-and-NBFCs question is left out unless the page knows the company is a lender. */
export function bankGroups(pathname: string, opts: { lender?: boolean } = {}): BankGroup[] {
  const sym = symbolOf(pathname);
  if (!sym) return [];
  return (suggestions.groups as { n: number; title: string; items: { id: string; text: string; lendersOnly?: boolean; needsSecondCompany?: boolean }[] }[])
    .map((g) => ({
      n: g.n, title: g.title,
      items: g.items.filter((q) => !q.lendersOnly || opts.lender).map((q) => ({ id: q.id, needsSecondCompany: q.needsSecondCompany, text: q.text.replace(/\{company_2\}/g, SECOND).replace(/\{company\}/g, sym).replace(/\{n\}/g, "5") })),
    }))
    .filter((g) => g.items.length > 0);
}

/** The stand-in the user replaces when a question needs a second company. */
export const SECOND = "XYZ";
