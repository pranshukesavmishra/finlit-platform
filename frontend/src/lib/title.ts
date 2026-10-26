import { useEffect } from "react";

/** Per-page title and description (the old site had one static title for every page). */
let siteDescription: string | null = null;   // the description the page loaded with: pages that set none go back to it, so a stale one never lingers

export function useDocTitle(title: string, description?: string) {
  useEffect(() => {
    document.title = `${title} · FinLit`;
    let m = document.querySelector<HTMLMetaElement>('meta[name="description"]');
    if (siteDescription === null) siteDescription = m?.content ?? "";
    const text = description || siteDescription;
    if (!m && text) { m = document.createElement("meta"); m.name = "description"; document.head.appendChild(m); }
    if (m && text) m.content = text;
  }, [title, description]);
}
