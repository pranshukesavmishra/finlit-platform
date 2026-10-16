import { useEffect } from "react";

/** Per-page title and description (the old site had one static title for every page). */
export function useDocTitle(title: string, description?: string) {
  useEffect(() => {
    document.title = `${title} · FinLit`;
    if (description) {
      let m = document.querySelector<HTMLMetaElement>('meta[name="description"]');
      if (!m) { m = document.createElement("meta"); m.name = "description"; document.head.appendChild(m); }
      m.content = description;
    }
  }, [title, description]);
}
