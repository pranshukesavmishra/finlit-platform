import { PAGE_FAQS, type PageFaq } from "../content/pageFaqs";

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
export function faqForPath(path: string, all: PageFaq[] = PAGE_FAQS): PageFaq | null {
  let best: PageFaq | null = null, bestScore = -1;
  for (const f of all) for (const r of f.routes) { const s = matchScore(r, path); if (s > bestScore) { best = f; bestScore = s; } }
  return best;
}

/** A link target for a set: the first route that has no parameter (the page itself), else the first route. */
export const faqHref = (f: PageFaq) => f.routes.find((r) => !r.includes(":")) ?? f.routes[0];
