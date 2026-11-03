// The blog page's logic, pure and tested: the five topic chips, minutes to read, the one featured story, and the filters.
import type { ContentItem } from "./siteApi";

export const CATEGORIES = ["Myth Busters", "Explainers", "Hot Topics", "Investing Basics", "Industry Insights"] as const;
export type Category = (typeof CATEGORIES)[number];
export type Kind = "all" | "articles" | "files";

const words = (html: string) => (html || "").replace(/<[^>]+>/g, " ").split(/\s+/).filter(Boolean).length;
/** Whole minutes to read at 200 words a minute, at least 1; null for a report, a data file or a picture (they have nothing to read). */
export function readMinutes(c: Pick<ContentItem, "contentType" | "articleBody" | "articleHtml" | "excerpt">): number | null {
  if (c.contentType !== "ARTICLE") return null;
  const n = words(c.articleHtml || c.articleBody || "") || words(c.excerpt || "");
  return Math.max(1, Math.ceil(n / 200));
}

const when = (c: ContentItem) => Date.parse(c.publishedAt || c.createdAt || "") || 0;
export const newestFirst = (list: ContentItem[]) => [...list].sort((a, b) => when(b) - when(a));

/** Posts matching the chosen topic chip, kind and search words (title and excerpt). A topic chip shows articles of that topic only. */
export function filterPosts(list: ContentItem[], o: { cat: Category | "all"; kind: Kind; q: string }): ContentItem[] {
  const q = o.q.trim().toLowerCase();
  return list.filter((c) => {
    if (o.cat !== "all") return c.contentType === "ARTICLE" && c.category === o.cat;
    if (o.kind === "articles") return c.contentType === "ARTICLE";
    if (o.kind === "files") return c.contentType !== "ARTICLE";
    return true;
  }).filter((c) => !q || `${c.title} ${c.excerpt}`.toLowerCase().includes(q));
}

/** The featured story and the rest. The featured one is the newest post flagged "featured", else the newest article; with a search or a topic chip on, nothing is singled out. */
export function splitFeatured(list: ContentItem[], narrowed: boolean): { featured: ContentItem | null; rest: ContentItem[] } {
  const sorted = newestFirst(list);
  if (narrowed || !sorted.length) return { featured: null, rest: sorted };
  const pick = sorted.find((c) => c.featured && c.contentType === "ARTICLE") ?? sorted.find((c) => c.contentType === "ARTICLE") ?? null;
  return { featured: pick, rest: pick ? sorted.filter((c) => c.id !== pick.id) : sorted };
}

export const countByCategory = (list: ContentItem[]): Record<Category, number> =>
  Object.fromEntries(CATEGORIES.map((k) => [k, list.filter((c) => c.contentType === "ARTICLE" && c.category === k).length])) as Record<Category, number>;
