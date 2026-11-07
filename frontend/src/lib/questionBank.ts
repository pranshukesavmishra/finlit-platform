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

/** Starter questions for pages that have no company question list and no page FAQ (the home page, for one), so the assistant never opens empty.
 *  Each has its answer written here, so a tap answers at once without calling the language model (which can take many seconds). They describe how things
 *  work and use only what the site already says about its own scores; none asks for or offers advice. */
export const STARTERS: { q: string; a: string }[] = [
  { q: "What is the FinLit IQ score and how is it built?",
    a: "The FinLit IQ is a score from 0 to 100 that averages five pillars: quality, growth, profitability, balance sheet and technical (the price trend). Each input is mapped to a score using fixed thresholds. The score has not been back-tested against future returns and does not predict them. Information only, not investment advice." },
  { q: "What does the FinLit Prism rating describe?",
    a: "FinLit Prism describes a company's financial health from its filings and prices. The fundamental score weighs four parts: growth and profitability, valuation, quality and risk. Technical indicators are shown separately and are not part of that score. It describes the company; it is not a recommendation." },
  { q: "What is the difference between a mutual fund and an ETF?",
    a: "Both pool many investors' money into a basket of securities. A mutual fund's units are bought and redeemed from the fund house at the day's NAV (net asset value). An ETF trades on the stock exchange during market hours at the market price, usually follows an index, and needs a demat account. Costs, taxes and tracking differ by fund, so read each fund's factsheet." },
  { q: "How do I read a P/E ratio?",
    a: "P/E is the share price divided by earnings per share: how many rupees the market pays for each rupee of a company's yearly profit. A higher P/E means the market pays more per rupee of profit, a lower one less. It is most useful next to the company's own past P/E and its industry peers; with very low or negative profit it is not meaningful." },
  { q: "What is an expense ratio in a mutual fund?",
    a: "The expense ratio is the yearly fee a fund house charges to run a fund, shown as a percentage of the fund's average assets. It is taken out of the fund's NAV a little each day, so the returns a fund reports are already after it. Direct plans have a lower expense ratio than regular plans of the same fund." },
  { q: "Which FinLit tools help me look at a company's financial health?",
    a: "On every company page the FinLit IQ scorecard shows the five pillars, and the FinLit Prism report (Gold) goes into growth, valuation, quality and risk with the reasons. The Score Screener lists companies by these scores, and Compare puts companies side by side. They describe a company's financial health; they are not recommendations." },
];
export const STARTER_QUESTIONS: string[] = STARTERS.map((x) => x.q);
