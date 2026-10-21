import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Financials } from "../lib/api";
import { highlightMap, plFlags, type PlFlag } from "../lib/plFlags";
import "../styles/plflags.css";

const KEY = "finlit.plflags.highlight";
const LABEL: Record<string, string> = { revenue: "revenue", "net profit": "net_profit", "operating profit": "operating_profit" };
const read = () => { try { return localStorage.getItem(KEY) !== "off"; } catch { return true; } };
const write = (on: boolean) => { try { localStorage.setItem(KEY, on ? "on" : "off"); } catch { /* private mode */ } };
const reduced = () => typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** Marks flagged rows and cells of the P&L tables on the page (data attributes only; the table files are not touched). */
function apply(flags: PlFlag[], on: boolean) {
  const map = highlightMap(flags, on);
  document.querySelectorAll<HTMLTableElement>("#financials table, #quarter table").forEach((t) => {
    const heads = Array.from(t.querySelectorAll("thead th")).map((h) => (h.textContent || "").trim());
    const annual = heads.some((h) => /^FY\d{2}$/.test(h));
    const rows = map[annual ? "annual" : "quarterly"];
    t.querySelectorAll<HTMLElement>("tbody tr").forEach((tr) => {
      const label = (tr.firstElementChild?.textContent || "").trim().toLowerCase();
      const key = tr.getAttribute("data-row-key") || LABEL[label];
      const periods = key ? rows[key] : undefined;
      tr.toggleAttribute("data-flag-row", !!periods);
      Array.from(tr.children).forEach((td, i) => {
        const h = heads[i] || "";
        td.toggleAttribute("data-flag-cell", !!periods && i > 0 && [...periods].some((p) => h === p || h.startsWith(p + " ")));
      });
    });
  });
}

export function PlFlagsLayer({ f }: { f?: Financials }) {
  const flags = useMemo(() => plFlags({ annual: f?.yearly.pl, quarterly: f?.quarterly.pl }), [f]);
  const [on, setOn] = useState(read), [shown, setShown] = useState(false), [gone, setGone] = useState(false), [landed, setLanded] = useState(false);
  const bar = useRef<HTMLDivElement>(null);
  const toggle = () => { setOn((v) => { write(!v); return !v; }); };
  // the notice drops in once, the first time the results area comes into view
  useEffect(() => {
    if (!flags.length || !bar.current) return;
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setShown(true); io.disconnect(); } }, { rootMargin: "-80px 0px -30% 0px" });
    io.observe(bar.current);
    return () => io.disconnect();
  }, [flags.length]);
  useEffect(() => { if (shown && reduced()) setLanded(true); }, [shown]);
  const land = useCallback(() => setLanded(true), []);
  useEffect(() => {
    if (!flags.length) return;
    const run = () => apply(flags, on && (landed || gone));
    run();
    const root = document.getElementById("financials")?.parentElement;
    const mo = root ? new MutationObserver(run) : null;
    mo?.observe(root!, { childList: true, subtree: true });
    return () => { mo?.disconnect(); apply([], false); };
  }, [flags, on, landed, gone]);
  if (!flags.length) return null;
  const cautions = flags.filter((x) => x.severity === "caution").length;
  return (
    <>
      <div className="plf-bar" ref={bar}>
        <span className="plf-chip" title="Revenue and profit comparisons worth a closer look">Flags · {flags.length}</span>
        <span className="plf-legend"><i className="plf-sw" />highlighted rows and columns in the results tables</span>
        <button type="button" className="plf-btn" aria-pressed={on} onClick={toggle}>{on ? "Turn highlights off" : "Turn highlights on"}</button>
        <button type="button" className="plf-btn" onClick={() => { setGone(false); setShown(true); }}>Show details</button>
      </div>
      {shown && !gone && (
        <aside className="plf-note" role="status" aria-label="Flags from the latest results" onAnimationEnd={land}>
          <div className="plf-h"><b>{flags.length} {flags.length === 1 ? "thing" : "things"} worth a closer look{cautions ? "" : ""}</b>
            <button type="button" className="plf-x" aria-label="Dismiss" onClick={() => { setGone(true); setLanded(true); }}>×</button></div>
          <ul>{flags.map((x) => <li key={x.key}><b>{x.title}</b> <span className="plf-p">({x.period})</span><br />{x.text}<br /><small>{x.why}</small></li>)}</ul>
          <p className="plf-f">Based on reported figures. Information only, not advice.</p>
        </aside>
      )}
    </>
  );
}
