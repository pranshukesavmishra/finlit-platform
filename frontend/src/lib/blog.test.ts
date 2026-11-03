import { describe, expect, it } from "vitest";
import { CATEGORIES, countByCategory, filterPosts, readMinutes, splitFeatured } from "./blog";
import type { ContentItem } from "./siteApi";

const post = (id: string, o: Partial<ContentItem> = {}): ContentItem => ({ id, title: "Title " + id, slug: id, excerpt: "About " + id, author: "A", contentType: "ARTICLE", status: "PUBLISHED", publishedAt: `2026-10-${String(10 + Number(id)).padStart(2, "0")}T00:00:00Z`, ...o });
const LIST = [post("1", { category: "Myth Busters" }), post("2", { category: "Explainers", featured: true }), post("3", { category: "Hot Topics" }), post("4", { contentType: "PDF" }), post("5")];

describe("blog logic", () => {
  it("has the five topics from the design, in order", () => {
    expect([...CATEGORIES]).toEqual(["Myth Busters", "Explainers", "Hot Topics", "Investing Basics", "Industry Insights"]);
  });
  it("reading time is whole minutes at 200 words a minute, at least one, and none for a file", () => {
    const words = (n: number) => `<p>${"word ".repeat(n)}</p>`;
    expect(readMinutes(post("a", { articleBody: words(1) }))).toBe(1);
    expect(readMinutes(post("a", { articleBody: words(200) }))).toBe(1);
    expect(readMinutes(post("a", { articleBody: words(201) }))).toBe(2);
    expect(readMinutes(post("a", { articleBody: words(1500) }))).toBe(8);
    expect(readMinutes(post("a", { articleBody: "<p><b>one</b> <i>two</i></p>" }))).toBe(1);               // tags are not words
    expect(readMinutes(post("p", { contentType: "PDF", articleBody: words(900) }))).toBeNull();
  });
  it("the featured story is the newest one flagged featured, else the newest article; nothing is singled out while searching", () => {
    expect(splitFeatured(LIST, false).featured!.id).toBe("2");
    expect(splitFeatured(LIST, false).rest.map((c) => c.id)).toEqual(["5", "4", "3", "1"]);               // newest first, the featured one not repeated
    expect(splitFeatured(LIST.map((c) => ({ ...c, featured: false })), false).featured!.id).toBe("5");   // newest article (5 is an article)
    expect(splitFeatured(LIST, true).featured).toBeNull();
    expect(splitFeatured([post("4", { contentType: "PDF" })], false).featured).toBeNull();               // a file is never the big story
    expect(splitFeatured([], false)).toEqual({ featured: null, rest: [] });
  });
  it("a topic chip shows articles of that topic; kind and search narrow further", () => {
    expect(filterPosts(LIST, { cat: "Explainers", kind: "all", q: "" }).map((c) => c.id)).toEqual(["2"]);
    expect(filterPosts(LIST, { cat: "all", kind: "files", q: "" }).map((c) => c.id)).toEqual(["4"]);
    expect(filterPosts(LIST, { cat: "all", kind: "articles", q: "" })).toHaveLength(4);
    expect(filterPosts(LIST, { cat: "all", kind: "all", q: "  about 3 " }).map((c) => c.id)).toEqual(["3"]);
    expect(filterPosts(LIST, { cat: "Myth Busters", kind: "all", q: "nothing like this" })).toEqual([]);
  });
  it("counts posts per topic", () => {
    expect(countByCategory(LIST)).toEqual({ "Myth Busters": 1, Explainers: 1, "Hot Topics": 1, "Investing Basics": 0, "Industry Insights": 0 });
  });
});
