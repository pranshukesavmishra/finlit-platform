// Turns what a browser's contentEditable produces into the small HTML the content service stores
// (p, h1-h3, strong, em, u, ul, ol, li, blockquote, a, img, hr, br). The service sanitises again; this keeps bold/italic from being lost.
const RENAME: Record<string, string> = { b: "strong", i: "em", div: "p" };
const KEEP_ATTRS: Record<string, string[]> = { a: ["href", "title"], img: ["src", "alt", "title"] };
const KNOWN = new Set(["p", "h1", "h2", "h3", "strong", "em", "u", "ul", "ol", "li", "blockquote", "a", "img", "hr", "br"]);

export function normaliseHtml(html: string): string {
  let out = html
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/<(script|style|iframe|object|embed)\b[\s\S]*?<\/\1\s*>/gi, "")
    .replace(/&nbsp;/g, " ");
  out = out.replace(/<(\/?)([a-zA-Z][a-zA-Z0-9]*)((?:\s[^>]*)?)>/g, (_m, slash: string, rawTag: string, attrs: string) => {
    let tag = rawTag.toLowerCase(); tag = RENAME[tag] || tag;
    if (!KNOWN.has(tag)) return "";                  // span, font, etc.: drop the tag, keep its text
    if (slash) return `</${tag}>`;
    const keep: string[] = [];
    for (const name of KEEP_ATTRS[tag] || []) {
      const m = new RegExp(`\\s${name}\\s*=\\s*("([^"]*)"|'([^']*)')`, "i").exec(attrs);
      if (m) keep.push(` ${name}="${(m[2] ?? m[3]).replace(/"/g, "&quot;")}"`);
    }
    return `<${tag}${keep.join("")}>`;
  });
  out = out.replace(/<p>\s*(<br>)?\s*<\/p>/g, "");   // empty paragraphs the browser leaves behind
  return out.trim();
}
export const htmlIsEmpty = (html: string) => !html.replace(/<[^>]+>/g, "").trim() && !/<img/i.test(html);

/** Plain text pasted into the editor becomes paragraphs; nothing in it can become markup. */
export function textToHtml(text: string): string {
  const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c] as string));
  return text.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean).map((p) => `<p>${esc(p).replace(/\n/g, "<br>")}</p>`).join("");
}
/** Link addresses the editor accepts: https only, like the content service. */
export const linkOk = (href: string) => { try { const u = new URL(href.trim()); return u.protocol === "https:" && !!u.hostname; } catch { return false; } };
