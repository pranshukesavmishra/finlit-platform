import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Financials } from "../lib/api";
import { highlightMap, insightChip, plInsights, type Growth, type Insight, type PeriodView, type Scope } from "../lib/plFlags";
import type { PlFlag } from "../lib/plFlags";
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

type Tab = "why" | "causes" | "check";
const TABS: [Tab, string][] = [["why", "Why it matters"], ["causes", "Possible causes"], ["check", "What to check"]];
/** Neutral, case-level pointers: what could explain the gap and where to look. Possibilities only, never a verdict. */
const MORE: Record<number, { causes: string[]; check: string[] }> = {
  1: { causes: ["One-off gains or asset sales", "Unusual cost savings or lower tax", "Lower interest or depreciation"], check: ["Other income in the P&L", "Exceptional items in the notes", "Whether operating profit moved the same way"] },
  2: { causes: ["One-off gains", "Cost cuts or a better product mix", "Lower tax or interest"], check: ["Operating margin trend", "Other income and exceptional items", "Why sales fell"] },
  3: { causes: ["Costs rising faster than sales", "Weaker pricing or margins", "Higher interest, depreciation or tax", "One-off charges"], check: ["Operating margin against last year", "Exceptional items and one-off charges", "Interest and tax lines"] },
  4: { causes: ["Costs rising as fast as sales", "Discounting to win volume", "One-off charges in the period"], check: ["Operating margin trend", "Raw material and staff costs", "Whether the next quarter repeats it"] },
  5: { causes: ["Non-operating or other income", "Exceptional savings or write-backs", "Lower tax or interest"], check: ["Other income in the P&L", "Operating profit against net profit", "Whether the gain can repeat"] },
  6: { causes: ["Weaker demand or a slowdown", "Price cuts or lost customers", "Fixed costs spread over lower sales"], check: ["Management commentary on demand", "Order book or volumes", "Whether peers saw the same"] },
  7: { causes: ["Other income or non-operating gains", "Lower tax or a tax credit", "Lower interest cost"], check: ["Other income in the P&L", "Tax rate against last year", "Operating profit trend"] },
  8: { causes: ["A change in the business or its costs", "Repeating one-off items", "A shift in pricing or mix"], check: ["Each quarter against the same one a year earlier", "Operating margin over the run", "Management commentary"] },
};
const SEV = { watch: "Watch", caution: "Investigate" } as const;
const sgn = (v: number) => (v < 0 ? "−" : v > 0 ? "+" : "") + Math.abs(v).toFixed(1) + "%";
const dir = (v: number) => (Math.abs(v) < 0.5 ? "flat" : v > 0 ? "up" : "down");
const WORD = { up: "Growing", down: "Declining", flat: "Flat" } as const;
const ARROW = { up: "M2 11l4-4 3 3 5-6M11 4h4v4", down: "M2 5l4 4 3-3 5 6M11 12h4V8", flat: "M2 8h12M11 5l3 3-3 3" } as const;

function Tile({ label, v }: { label: string; v: number | null }) {
  if (v == null) return <div className="plf-tile plf-flat"><span>{label}</span><b>—</b><em>Not comparable (earlier figure is nil or a loss)</em></div>;
  const d = dir(v);
  return (
    <div className={`plf-tile plf-${d}`}>
      <span>{label}</span>
      <b>{sgn(v)}</b>
      <em><svg viewBox="0 0 16 16" aria-hidden="true"><path d={ARROW[d]} /></svg>{WORD[d]}</em>
    </div>
  );
}

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
/** 2026-09-30 -> "30 Sep 2026"; blank when the date is missing. */
export const dmy = (d: string | null) => (d && /^\d{4}-\d{2}-\d{2}/.test(d) ? `${+d.slice(8, 10)} ${MON[+d.slice(5, 7) - 1]} ${d.slice(0, 4)}` : "");
const line = (g: Growth, lender: boolean) => [["revenue", g.revenue], ["net profit", g.profit], ...(lender ? [] : [["operating profit", g.operating]])].filter((x) => x[1] != null).map((x) => `${x[0]} ${sgn(x[1] as number)}`).join(", ");

function Block({ v, lender }: { v: PeriodView; lender: boolean }) {
  const revLabel = lender ? "Total income growth" : "Revenue growth";
  const q = v.scope === "quarterly";
  return (
    <div className="plf-blk" role="tabpanel">
      <p className="plf-vs"><b>{v.period}</b> compared with <b>{v.against}</b>{q ? " (the same quarter a year earlier)" : ""}{v.periodEnd ? `. Period ended ${dmy(v.periodEnd)}, against ${dmy(v.againstEnd)}.` : "."}</p>
      <div className="plf-tiles">
        <Tile label={revLabel} v={v.growth.revenue} />
        <Tile label="Net profit growth" v={v.growth.profit} />
        {!lender && v.growth.operating != null && <Tile label="Operating profit growth" v={v.growth.operating} />}
      </div>
      {q && v.qoq && line(v.qoq.growth, lender) && <p className="plf-qoq">Quarter on quarter, {v.qoq.period} against {v.qoq.against}: {line(v.qoq.growth, lender)}.</p>}
      <p className="plf-sum">{v.triggered ? v.text!.replace(/ Compared with [^.]*\.$/, "") : `This situation does not show in the ${q ? "latest quarter" : "latest year"}.`}</p>
    </div>
  );
}

function FlagCard({ items, onClose, onAnimationEnd }: { items: Insight[]; onClose: () => void; onAnimationEnd: () => void }) {
  const [i, setI] = useState(0), [tab, setTab] = useState<Tab>("why"), [pick_, setPick] = useState<Scope | null>(null);
  const x = items[Math.min(i, items.length - 1)], more = MORE[x.case];
  const scopes = (["quarterly", "annual"] as const).filter((sc) => x.views[sc]);
  const sc: Scope = pick_ && x.views[pick_] ? pick_ : x.headline, v = x.views[sc]!, hv = x.views[x.headline]!;
  const pick = (n: number) => { setI(n); setTab("why"); setPick(null); };
  const body = tab === "why" ? <p>{x.why}</p> : <ul>{more[tab === "causes" ? "causes" : "check"].map((t) => <li key={t}>{t}</li>)}</ul>;
  return (
    <aside className="plf-note" role="status" aria-label="Flags from the latest results" onAnimationEnd={onAnimationEnd}>
      <div className="plf-top">
        <span className="plf-ico" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6" /><path d="M20 20l-4.5-4.5M4 8V5a1 1 0 011-1h3M20 8V5a1 1 0 00-1-1h-3" /></svg></span>
        <div className="plf-tt"><b>{items.length === 1 ? "Worth a closer look" : `${items.length} things worth a closer look`}</b><small>Earnings intelligence · {hv.period} {x.headline === "quarterly" ? "quarter" : "year"}</small></div>
        <span className={`plf-sev plf-sev-${x.severity}`}>{SEV[x.severity]}</span>
        <button type="button" className="plf-x" aria-label="Dismiss" onClick={onClose}>×</button>
      </div>
      {items.length > 1 && (
        <div className="plf-pager" role="tablist" aria-label="Flags">
          {items.map((f, n) => <button key={f.key} type="button" role="tab" aria-selected={n === i} className={n === i ? "on" : ""} onClick={() => pick(n)}>{insightChip(f)}</button>)}
        </div>
      )}
      <section className="plf-in">
        <h3>{x.title}</h3>
        <p className="plf-base">Flag based on the {hv.label.toLowerCase()}: {hv.period} against {hv.against}.</p>
        {scopes.length > 1 && (
          <div className="plf-tabs plf-views" role="tablist" aria-label="Period">
            {scopes.map((k) => <button key={k} type="button" role="tab" aria-selected={sc === k} className={sc === k ? "on" : ""} onClick={() => setPick(k)}>{x.views[k]!.label} · {x.views[k]!.period}{x.views[k]!.triggered ? "" : " (no flag)"}</button>)}
          </div>
        )}
        {scopes.length === 1 && <p className="plf-lbl">{v.label}</p>}
        <Block v={v} lender={x.lender} />
      </section>
      <h4>Explore this insight</h4>
      <div className="plf-tabs" role="tablist">
        {TABS.map(([k, l]) => <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>)}
      </div>
      <div className="plf-pane" role="tabpanel">{body}</div>
      <p className="plf-f">Based on reported figures{x.lender ? " (for a bank or lender, revenue is total income and operating profit is not shown)" : ""}. Information only, not advice.</p>
    </aside>
  );
}

export function PlFlagsLayer({ f, lender = false }: { f?: Financials; lender?: boolean }) {
  // both series come from the same stored financials report as the results tables and the quarter section, so a new quarter shows after a refresh
  const items = useMemo(() => plInsights({ annual: f?.yearly?.pl, quarterly: f?.quarterly?.pl, lender }), [f, lender]);
  const flags = useMemo(() => items.flatMap((x) => x.flags), [items]);
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
  return (
    <>
      <div className="plf-bar" ref={bar}>
        <span className="plf-chip" title="Revenue and profit comparisons worth a closer look">Flags · {items.length}</span>
        <span className="plf-legend"><i className="plf-sw" />highlighted rows and columns in the results tables</span>
        <button type="button" className="plf-btn" aria-pressed={on} onClick={toggle}>{on ? "Turn highlights off" : "Turn highlights on"}</button>
        <button type="button" className="plf-btn" onClick={() => { setGone(false); setShown(true); }}>Show details</button>
      </div>
      {shown && !gone && <FlagCard items={items} onClose={() => { setGone(true); setLanded(true); }} onAnimationEnd={land} />}
    </>
  );
}
