import { useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import DOMPurifyless from "../lib/sanitize";
import { apiUrl } from "../lib/api";
import { assetUrl, getContent, getContentItem, type ContentItem } from "../lib/siteApi";
import { Icon } from "../lib/icons";
import { dateIN } from "../lib/format";
import { Reveal } from "../components/Reveal";
import { useDocTitle } from "../lib/title";

const TYPES = [["ALL", "All"], ["ARTICLE", "Articles"], ["PDF", "Reports"], ["SPREADSHEET", "Data"], ["IMAGE", "Visuals"]] as const;
const ICON: Record<string, string> = { ARTICLE: "notes", PDF: "table", SPREADSHEET: "bars", IMAGE: "line", FILE: "table" };

export function Blog() {
  useDocTitle("Blog & research", "Articles, reports and data from the FinLit research team.");
  const [type, setType] = useState<string>("ALL");
  const [q, setQ] = useState("");
  const { data, isLoading, isError } = useQuery({ queryKey: ["content"], queryFn: () => getContent(), staleTime: 60_000, retry: 1 });
  const list = useMemo(() => (data || []).filter((c) => (type === "ALL" || c.contentType === type) && (!q || (c.title + " " + c.excerpt).toLowerCase().includes(q.toLowerCase()))), [data, type, q]);
  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><div className="eyebrow">Blog & research</div><h1>Notes from the research desk.</h1><p>Articles, reports and data, written to be understood.</p></div></section>
      <section className="sec" style={{ paddingTop: 16 }}><div className="wrap">
        <div className="filters"><div className="seg" role="group" aria-label="Type">{TYPES.map(([k, l]) => <button key={k} aria-pressed={type === k} onClick={() => setType(k)}>{l}</button>)}</div><input className="sbox" placeholder="Search posts" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search posts" /></div>
        {isLoading && <div className="cards3">{[0, 1, 2].map((i) => <div key={i} className="skeleton" style={{ height: 280 }} />)}</div>}
        {isError && <div className="state"><h2>Posts are unavailable right now</h2><p>Please try again shortly.</p></div>}
        {!isLoading && !isError && !list.length && <div className="state"><h2>Nothing here yet</h2><p>{q ? "No posts match your search." : "New research is on the way."}</p></div>}
        <div className="cards3">{list.map((c, i) => (
          <Reveal key={c.id} delay={(i % 3) * 70}><Link className="postcard" to={`/blog/${c.slug}`}><div className="cover">{c.coverImageKey ? <img src={assetUrl(c.coverImageKey)} alt="" loading="lazy" /> : c.coverImageUrl && /^https:\/\//.test(c.coverImageUrl) ? <img src={c.coverImageUrl} alt="" loading="lazy" /> : <Icon name={ICON[c.contentType] || "notes"} />}</div>
            <div className="body"><span className="chip gold">{TYPES.find((t) => t[0] === c.contentType)?.[1] || c.contentType}</span><h3>{c.title}</h3><p>{c.excerpt}</p><p className="faint" style={{ marginTop: 10, fontSize: 12.5 }}>{c.author} · {c.publishedAt ? dateIN(c.publishedAt) : ""}</p></div></Link></Reveal>
        ))}</div>
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
