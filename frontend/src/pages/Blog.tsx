import { CoverArt } from "../components/PageArt";
import { BlogArt } from "../components/BlogArt";
import "../styles/blog.css";
import { CATEGORIES, countByCategory, filterPosts, readMinutes, splitFeatured, type Category, type Kind } from "../lib/blog";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import DOMPurifyless from "../lib/sanitize";
import { apiUrl } from "../lib/api";
import { assetUrl, getContent, getContentItem, type ContentItem } from "../lib/siteApi";
import { dateIN } from "../lib/format";
import { Reveal } from "../components/Reveal";
import { useDocTitle } from "../lib/title";

const KINDS = [["all", "Everything"], ["articles", "Articles"], ["files", "Reports & data"]] as const;
const TYPE_WORD: Record<string, string> = { ARTICLE: "Article", PDF: "Report", SPREADSHEET: "Data", IMAGE: "Visual", FILE: "File" };
/** One small line icon per topic chip (stroke only, no fill): decoration beside a word, never the only signal. */
const ICON: Record<string, string> = {
  all: "M4 6h16M4 12h16M4 18h10",
  "Myth Busters": "M4 17l6-6 4 4 6-8M15 7h5v5",
  Explainers: "M5 4h9a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3zM8 8h6M8 12h6",
  "Hot Topics": "M12 3c1 4 5 5 5 10a5 5 0 0 1-10 0c0-2 1-3 2-4 0 2 1 3 2 3 0-3-1-5 1-9z",
  "Investing Basics": "M4 20V10M10 20V4M16 20v-7M22 20H2",
  "Industry Insights": "M3 21h18M5 21V9l7-5 7 5v12M9 21v-6h6v6",
};
const Ico = ({ k }: { k: string }) => <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={ICON[k]} /></svg>;
const cover = (c: ContentItem) => (c.coverImageKey ? <img src={assetUrl(c.coverImageKey)} alt="" loading="lazy" /> : c.coverImageUrl && /^https:\/\//.test(c.coverImageUrl) ? <img src={c.coverImageUrl} alt="" loading="lazy" /> : <CoverArt seed={c.title} type={c.contentType} />);
function Meta({ c }: { c: ContentItem }) {
  const m = readMinutes(c);
  return <p className="bl-meta">{c.publishedAt ? <time dateTime={c.publishedAt}>{dateIN(c.publishedAt)}</time> : null}{m != null && <span> · {m} min read</span>}{m == null && <span> · {TYPE_WORD[c.contentType] || c.contentType}</span>}</p>;
}
const Tag = ({ c }: { c: ContentItem }) => <span className="bl-tag">{c.contentType === "ARTICLE" ? c.category || "Article" : TYPE_WORD[c.contentType] || c.contentType}</span>;

export function Blog() {
  useDocTitle("FinLit Blog", "Long-form articles on investing, finance and markets: explainers, myth-busters and thought pieces from the FinLit team.");
  const [cat, setCat] = useState<Category | "all">("all");
  const [kind, setKind] = useState<Kind>("all");
  const [q, setQ] = useState("");
  const { data, isLoading, isError } = useQuery({ queryKey: ["content"], queryFn: () => getContent(), staleTime: 60_000, retry: 1 });
  const all = data || [];
  const counts = useMemo(() => countByCategory(all), [all]);
  const list = useMemo(() => filterPosts(all, { cat, kind, q }), [all, cat, kind, q]);
  const narrowed = cat !== "all" || kind !== "all" || q.trim() !== "";
  const { featured, rest } = useMemo(() => splitFeatured(list, narrowed), [list, narrowed]);
  return (
    <>
      <section className="bl-hero"><div className="wrap bl-hero-in">
        <div className="bl-hero-t">
          <span className="bl-pill">FinLit Blog</span>
          <h1>Long-Form Articles on Investing, Finance &amp; Markets</h1>
          <p>In-depth explainers, myth-busters and thought pieces on the hottest topics in the world of investing. Plain language; none of it is a recommendation.</p>
        </div>
        <BlogArt />
      </div></section>
      <section className="sec bl-sec"><div className="wrap">
        <div className="bl-bar">
          <div className="bl-chips" role="group" aria-label="Topic">
            <button type="button" aria-pressed={cat === "all"} onClick={() => { setCat("all"); setKind("all"); }}><Ico k="all" />All Articles</button>
            {CATEGORIES.map((k) => <button key={k} type="button" aria-pressed={cat === k} onClick={() => setCat(cat === k ? "all" : k)}><Ico k={k} />{k}{counts[k] > 0 && <small>{counts[k]}</small>}</button>)}
          </div>
          <div className="bl-tools">
            <div className="seg" role="group" aria-label="Kind">{KINDS.map(([k, l]) => <button key={k} type="button" aria-pressed={kind === k && cat === "all"} disabled={cat !== "all"} onClick={() => setKind(k)}>{l}</button>)}</div>
            <input className="sbox" placeholder="Search posts" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search posts" />
          </div>
        </div>
        {isLoading && <div className="bl-grid">{[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 300 }} />)}</div>}
        {isError && <div className="state"><h2>We could not load the posts</h2><p>Please try again in a minute.</p></div>}
        {!isLoading && !isError && !list.length && <div className="state"><h2>Nothing here yet</h2><p>{narrowed ? "No posts match. Try another topic, or clear the search." : "Nothing published yet. We will post here when we have something worth reading."}</p></div>}
        {featured && (
          <Reveal><Link className="bl-feature" to={`/blog/${featured.slug}`} aria-label={`Featured: ${featured.title}`}>
            <div className="bl-fcover">{cover(featured)}</div>
            <div className="bl-fbody"><Tag c={featured} /><h2>{featured.title}</h2><p>{featured.excerpt}</p><Meta c={featured} /><span className="bl-go" aria-hidden="true">→</span></div>
          </Link></Reveal>
        )}
        {rest.length > 0 && (
          <>
            <div className="bl-lh"><h2>{narrowed ? (cat !== "all" ? cat : "Results") : "Latest Articles"}</h2><span className="faint">{rest.length + (featured ? 1 : 0)} {rest.length + (featured ? 1 : 0) === 1 ? "post" : "posts"}</span></div>
            <div className="bl-grid">{rest.map((c, i) => (
              <Reveal key={c.id} delay={(i % 3) * 70}><Link className="bl-card" to={`/blog/${c.slug}`}>
                <div className="bl-cover">{cover(c)}</div>
                <div className="bl-cbody"><Tag c={c} /><h3>{c.title}</h3><Meta c={c} /></div>
              </Link></Reveal>
            ))}</div>
          </>
        )}
      </div></section>
    </>
  );
}

export function BlogPost() {
  const { slug = "" } = useParams();
  const { data: c, isLoading, isError } = useQuery<ContentItem>({ queryKey: ["content", slug], queryFn: () => getContentItem(slug), retry: 1 });
  useDocTitle(c?.title || "Post", c?.excerpt);
  if (isLoading) return <div className="wrap state"><div className="skeleton" style={{ height: 300 }} /></div>;
  if (isError || !c) return <div className="wrap state"><h2>We couldn't find that post</h2><p><Link to="/blog">Back to the blog</Link></p></div>;
  const file = c.fileUrl && (c.fileUrl.startsWith("/api/content/assets/") || /^https:\/\//.test(c.fileUrl)) ? apiUrl(c.fileUrl) : null;
  return (
    <>
      <section className="pagehead"><div className="wrap" style={{ maxWidth: 760 }}><Link className="chip gold" to="/blog">← Blog</Link><h1 style={{ maxWidth: "none", fontSize: "clamp(30px,4.4vw,52px)" }}>{c.title}</h1><p>{c.excerpt}</p><p className="faint" style={{ marginTop: 12, fontSize: 13 }}>{c.author} · {c.publishedAt ? dateIN(c.publishedAt) : ""}</p></div></section>
      <section className="sec" style={{ paddingTop: 0 }}><div className="wrap">
        {c.contentType === "ARTICLE" && <article className="article" dangerouslySetInnerHTML={{ __html: DOMPurifyless(c.articleHtml || "") }} />}
        {c.contentType === "PDF" && file && <><iframe title={c.title} src={file} style={{ width: "100%", height: "78vh", border: "1px solid var(--border)", borderRadius: 16, background: "#fff" }} /></>}
        {c.contentType === "IMAGE" && file && <img src={file} alt={c.title} style={{ maxWidth: "100%", borderRadius: 16, display: "block", margin: "0 auto" }} />}
        {c.contentType !== "ARTICLE" && file && <p style={{ textAlign: "center", marginTop: 20 }}><a className="btn primary" href={file} download={c.originalFileName || undefined}>Download {c.originalFileName || "file"}</a></p>}
      </div></section>
    </>
  );
}
