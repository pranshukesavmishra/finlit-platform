import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { prefetchStock, useSearchIndex, type SearchRow } from "../lib/api";
import { initials } from "../lib/format";

const COLORS = ["#544C38", "#70644A", "#827659", "#7A5A12", "#8A6A25", "#B8862B", "#584F3B", "#79705C", "#8A6420", "#685F4A", "#6B4E10", "#867F6D"];
const colorOf = (s: string) => COLORS[[...s].reduce((a, c) => a + c.charCodeAt(0), 0) % COLORS.length];
const SHOWN = 40;   // rows drawn at once; the list grows as you scroll, so all ~5,700 companies are reachable without drawing them all

/** Ctrl-K / "/" search over every listed stock. The whole index (~89 KB gzipped) is held in the browser,
 *  so results appear as you type with no server wait; hovering a result warms its report. */
export function SearchPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const nav = useNavigate();
  const qc = useQueryClient();
  const { data, isLoading, isError } = useSearchIndex(true);   // fetched as soon as the page is up, so the palette opens with the list already here
  const [limit, setLimit] = useState(SHOWN);

  useEffect(() => { if (open) { setQ(""); setSel(0); setLimit(SHOWN); setTimeout(() => input.current?.focus(), 30); } }, [open]);

  // The server sends the list biggest company first, so the empty box shows the top companies and the rest follow below them.
  const all = useMemo<SearchRow[]>(() => {
    const rows = data?.rows || [];
    const s = q.trim().toUpperCase();
    if (!s) return rows;
    const score = (r: SearchRow) => (r[0] === s ? 0 : r[0].startsWith(s) ? 1 : r[1].toUpperCase().startsWith(s) ? 2 : r[2] === s ? 3 : 4);
    const pos = new Map(rows.map((r, i) => [r[0], i]));
    return rows.filter((r) => r[0].includes(s) || r[1].toUpperCase().includes(s) || r[2] === s || (r[4] || "").toUpperCase().includes(s))
      .sort((a, b) => score(a) - score(b) || (pos.get(a[0]) ?? 0) - (pos.get(b[0]) ?? 0));
  }, [data, q]);
  const hits = useMemo(() => all.slice(0, limit), [all, limit]);

  const go = (sym: string) => { onClose(); nav(`/stocks/${encodeURIComponent(sym)}`); };
  if (!open) return null;
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div className="palette" role="dialog" aria-modal="true" aria-label="Search stocks">
        <div className="in">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
          <input ref={input} value={q} placeholder="Search company, ticker or BSE code" autoComplete="off" role="combobox" aria-expanded="true" aria-controls="palList"
            onChange={(e) => { setQ(e.target.value); setSel(0); setLimit(SHOWN); }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => { const n = Math.max(0, Math.min(s + 1, all.length - 1)); if (n >= limit - 3) setLimit((l) => l + SHOWN); return n; }); }
              if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
              if (e.key === "Enter" && hits[sel]) go(hits[sel][0]);
              if (e.key === "Escape") onClose();
            }} />
        </div>
        <ul id="palList" role="listbox" onScroll={(e) => { const el = e.currentTarget; if (el.scrollTop + el.clientHeight > el.scrollHeight - 80 && limit < all.length) setLimit((l) => l + SHOWN); }}>
          {isLoading && <li aria-disabled="true"><span className="muted">Loading the stock list…</span></li>}
          {isError && <li aria-disabled="true"><span className="muted">Stock search is unavailable right now.</span></li>}
          {!isLoading && !isError && hits.length === 0 && <li aria-disabled="true"><span className="muted">No match. Try a ticker such as RELIANCE or TCS.</span></li>}
          {hits.map((r, i) => (
            <li key={r[0]} role="option" aria-selected={i === sel} className={i === sel ? "sel" : ""} onMouseEnter={() => { setSel(i); if (r[3]) prefetchStock(qc, r[0], 150); }} onClick={() => go(r[0])}>
              <span className="av" style={{ background: colorOf(r[0]) }}>{initials(r[0])}</span>
              <span className="nm">{r[1]}</span><span className="tk">{r[0]}</span>
            </li>
          ))}
        </ul>
        <div className="hint">↑ ↓ to move · Enter to open · Esc to close · {data ? `${data.rows.length.toLocaleString("en-IN")} stocks, biggest first, searched in your browser` : "…"}</div>
      </div>
    </>
  );
}
