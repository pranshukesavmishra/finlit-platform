import { PAGE_FAQS, type PageFaq } from "../content/pageFaqs";
import { MF_PORTFOLIO_FAQ } from "../content/mfPortfolioFaqs";

/** Product copy that changed after the source PDF; leave the generated content untouched. */
export const CURRENT_PAGE_FAQS = PAGE_FAQS.map(faq => faq.id !== "dashboard" ? faq : {
  ...faq, items: faq.items.map(item => item.q !== "What does the dashboard show?" ? item : {
    ...item, a: "Your dashboard starts with the companies you follow, active alerts and saved screens, plus a shortcut to research a company. Your chosen widgets show quarterly results, dates, news, IPOs, watchlist moves and more. Open Market overview when you want index levels, breadth, sectors and institutional flows. Customise lets you choose, resize and reorder widgets.",
  }),
});

/** Sets written by hand after the PDF (the PDF-built list in content/pageFaqs.ts is generated and not edited). */
const EXTRA_FAQS: PageFaq[] = [MF_PORTFOLIO_FAQ];

/** Route patterns use react-router's ":param" segments. Query string, hash, a trailing slash and letter case are ignored. */
const clean = (p: string) => p.split(/[?#]/)[0].replace(/\/+$/, "").toLowerCase() || "/";
const segs = (p: string) => clean(p).split("/").filter(Boolean);

/** How well a pattern fits an address: -1 for no match, else the number of fixed (non-param) segments, so a specific route beats a general one. */
export function matchScore(pattern: string, path: string): number {
  const a = segs(pattern), b = segs(path);
  if (a.length !== b.length) return -1;
  let score = 0;
  for (let i = 0; i < a.length; i++) {
    if (a[i].startsWith(":")) { if (!b[i]) return -1; }
    else if (a[i] === b[i]) score++;
    else return -1;
  }
  return score;
}

/** The FAQ set that belongs to this address, or null when the page has none (Learn, Account, Home, legal, sign-in ...). */
export function faqForPath(path: string, all: PageFaq[] = [...CURRENT_PAGE_FAQS, ...EXTRA_FAQS]): PageFaq | null {
  let best: PageFaq | null = null, bestScore = -1;
  for (const f of all) for (const r of f.routes) { const s = matchScore(r, path); if (s > bestScore) { best = f; bestScore = s; } }
  return best;
}

/** A link target for a set: the first route that has no parameter (the page itself), else the first route. */
export const faqHref = (f: PageFaq) => f.routes.find((r) => !r.includes(":")) ?? f.routes[0];
