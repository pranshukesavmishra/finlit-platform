import type { ContentItem } from "../lib/siteApi";
import sanitize from "../lib/sanitize";
import { canEmbedPdf, sizeText } from "../lib/cms";

/** The body of a post, by kind. Article HTML always goes through the sanitiser; a file is only used when its address is the content
 *  service's own (or https); a PDF is embedded only when the browser will allow it, otherwise it is a link. */
export function PostBody({ c, file, origin }: { c: Pick<ContentItem, "contentType" | "title" | "articleHtml" | "originalFileName" | "fileSize">; file: string | null; origin?: string }) {
  const here = origin ?? (typeof window !== "undefined" ? window.location.origin : "");
  const name = c.originalFileName || "file";
  const meta = [c.originalFileName, sizeText(c.fileSize)].filter(Boolean).join(" · ");
  return (
    <>
      {c.contentType === "ARTICLE" && <article className="article" dangerouslySetInnerHTML={{ __html: sanitize(c.articleHtml || "") }} />}
      {c.contentType === "PDF" && file && (canEmbedPdf(file, here)
        ? <iframe title={c.title} src={file} className="post-pdf" />
        : <div className="card post-file"><b>PDF report</b><span className="muted">{meta}</span><a className="btn primary" href={file} target="_blank" rel="noopener noreferrer">Open the PDF</a></div>)}
      {c.contentType === "IMAGE" && file && <img src={file} alt={c.title} className="post-img" />}
      {c.contentType === "SPREADSHEET" && file && <div className="card post-file"><b>Spreadsheet</b><span className="muted">{meta}</span></div>}
      {c.contentType !== "ARTICLE" && file && <p className="post-dl"><a className="btn primary" href={file} download={name}>Download {name}</a></p>}
      {c.contentType !== "ARTICLE" && !file && <p className="muted">The file for this post is not available.</p>}
    </>
  );
}
