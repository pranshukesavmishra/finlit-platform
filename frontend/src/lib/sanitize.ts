import { apiUrl } from "./api";

// The site backend already sanitises article HTML with nh3 before storing it. This is a second,
// defence-in-depth pass in the browser: only a small allow-list of tags/attributes survives.
// (DOMParser never runs scripts or event handlers, so parsing is safe.)
const ALLOWED = new Set(["P", "BR", "STRONG", "B", "EM", "I", "U", "S", "H1", "H2", "H3", "H4", "UL", "OL", "LI", "BLOCKQUOTE", "A", "IMG", "TABLE", "THEAD", "TBODY", "TR", "TH", "TD", "CODE", "PRE", "HR", "SPAN", "FIGURE", "FIGCAPTION"]);
const DROP = new Set(["SCRIPT", "STYLE", "IFRAME", "OBJECT", "EMBED", "FORM", "INPUT", "BUTTON", "LINK", "META", "SVG", "MATH", "TEMPLATE", "NOSCRIPT"]);
const ATTRS: Record<string, string[]> = { A: ["href", "title"], IMG: ["src", "alt", "title", "width", "height"], TH: ["colspan", "rowspan"], TD: ["colspan", "rowspan"] };

function clean(node: Element) {
  for (const child of Array.from(node.children)) {
    const tag = child.tagName.toUpperCase();
    if (DROP.has(tag)) { child.remove(); continue; }
    if (!ALLOWED.has(tag)) {
      const kids = Array.from(child.childNodes);
      child.replaceWith(...kids);
      kids.forEach((k) => { if (k.nodeType === 1) clean(k.parentElement as Element); });
      continue;
    }
    for (const a of Array.from(child.attributes)) if (!(ATTRS[tag] || []).includes(a.name)) child.removeAttribute(a.name);
    if (tag === "A") {
      const h = child.getAttribute("href") || "";
      if (!/^(https?:|mailto:|\/|#)/i.test(h)) child.removeAttribute("href");
      child.setAttribute("rel", "noopener noreferrer");
      if (/^https?:/i.test(h)) child.setAttribute("target", "_blank");
    }
    if (tag === "IMG" && !/^(https:|\/api\/content\/assets\/|data:image\/(png|jpe?g|webp|gif);)/i.test(child.getAttribute("src") || "")) { child.remove(); continue; }
    if (tag === "IMG" && (child.getAttribute("src") || "").startsWith("/api/")) child.setAttribute("src", apiUrl(child.getAttribute("src") as string));
    clean(child);
  }
}

export default function sanitize(html: string): string {
  const doc = new DOMParser().parseFromString(html, "text/html");
  clean(doc.body);
  return doc.body.innerHTML;
}
