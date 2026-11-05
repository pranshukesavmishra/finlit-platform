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
type Para = { lead?: string; text: string };
const list = (a: string[]): Para[] => [{ text: a.join(", ") + "." }];
/** Neutral, case-level pointers: what could explain the gap and where to look. Possibilities only, never a verdict. Every tab is a list of paragraphs. */
const MORE: Record<number, { causes: Para[]; check: Para[]; why?: Para[] }> = {
  1: {
    why: [{ lead: "Quarter on quarter", text: "Profit and sales moved very differently. One quarter can be seasonal, so read it as momentum, not a trend." }, { lead: "Year on year", text: "Same-quarter view removes seasonality. Strong profit growth may be real efficiency or a one-time boost." }],
    causes: [{ lead: "Quarter on quarter", text: "Seasonal demand, sudden cost changes, one-time gains or expenses, discounting, higher interest or tax." }, { lead: "Year on year", text: "Costs growing slower than sales, lower input costs, weak base last year, one-time gains, lower interest." }],
    check: [{ lead: "Quarter on quarter", text: "Same quarter last year. One-time items in the results. Gap between operating and net profit." }, { lead: "Year on year", text: "Is profit from the core business? Is margin improving over several quarters? Is cash flow strong?" }],
  },
  2: { causes: list(["One-off gains", "Cost cuts or a better product mix", "Lower tax or interest"]), check: list(["Operating margin trend", "Other income and exceptional items", "Why sales fell"]) },
  3: { causes: list(["Costs rising faster than sales", "Weaker pricing or margins", "Higher interest, depreciation or tax", "One-off charges"]), check: list(["Operating margin against last year", "Exceptional items and one-off charges", "Interest and tax lines"]) },
  4: { causes: list(["Costs rising as fast as sales", "Discounting to win volume", "One-off charges in the period"]), check: list(["Operating margin trend", "Raw material and staff costs", "Whether the next quarter repeats it"]) },
  5: { causes: list(["Non-operating or other income", "Exceptional savings or write-backs", "Lower tax or interest"]), check: list(["Other income in the P&L", "Operating profit against net profit", "Whether the gain can repeat"]) },
  6: { causes: list(["Weaker demand or a slowdown", "Price cuts or lost customers", "Fixed costs spread over lower sales"]), check: list(["Management commentary on demand", "Order book or volumes", "Whether peers saw the same"]) },
  7: { causes: list(["Other income or non-operating gains", "Lower tax or a tax credit", "Lower interest cost"]), check: list(["Other income in the P&L", "Tax rate against last year", "Operating profit trend"]) },
  8: { causes: list(["A change in the business or its costs", "Repeating one-off items", "A shift in pricing or mix"]), check: list(["Each quarter against the same one a year earlier", "Operating margin over the run", "Management commentary"]) },
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

const tiles = (g: Growth, lender: boolean) => (
  <div className="plf-tiles">
    <Tile label="Revenue growth" v={g.revenue} />
    <Tile label="Net profit growth" v={g.profit} />
    {!lender && g.operating != null && <Tile label="Operating profit growth" v={g.operating} />}
  </div>
);

/** A quarter shows both comparisons as boxes (against the previous quarter, then against the same quarter a year earlier); the year shows the year,
 *  and says in one line how the latest quarter has moved since (`recent`), so a year that fell is not read without the newest quarter. */
export function Block({ v, lender, recent }: { v: PeriodView; lender: boolean; recent?: PeriodView }) {
  const q = v.scope === "quarterly";
  return (
    <div className="plf-blk" role="tabpanel">
      {q && v.qoq && line(v.qoq.growth, lender) && (
        <>
          <p className="plf-vs"><b>Quarter on quarter:</b> <b>{v.qoq.period}</b> compared with <b>{v.qoq.against}</b> (the quarter before).</p>
          {tiles(v.qoq.growth, lender)}
        </>
      )}
      <p className={"plf-vs" + (q && v.qoq ? " plf-vs2" : "")}>{q && <b>Year on year: </b>}<b>{v.period}</b> compared with <b>{v.against}</b>{q ? " (the same quarter a year earlier)" : ""}{v.periodEnd ? `. Period ended ${dmy(v.periodEnd)}, against ${dmy(v.againstEnd)}.` : "."}</p>
      {tiles(v.growth, lender)}
      {!q && recent && line(recent.growth, lender) && <p className="plf-qoq">Since then, the latest quarter ({recent.period}) against the same quarter a year earlier: {line(recent.growth, lender)}.</p>}
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
  const paras: Para[] = tab === "why" ? more.why ?? [{ text: x.why }] : more[tab];
  const body = paras.map((p) => <p key={p.text}>{p.lead && <b>{p.lead}: </b>}{p.text}</p>);
  const onTabKey = (e: React.KeyboardEvent) => {
    const n = TABS.length, at = TABS.findIndex(([k]) => k === tab);
    const to = e.key === "ArrowRight" ? (at + 1) % n : e.key === "ArrowLeft" ? (at + n - 1) % n : e.key === "Home" ? 0 : e.key === "End" ? n - 1 : -1;
    if (to < 0) return;
    e.preventDefault(); setTab(TABS[to][0]);
    (e.currentTarget.querySelectorAll<HTMLElement>('[role="tab"]')[to])?.focus();
  };
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
        {scopes.length > 1 && (
          <div className="plf-tabs plf-views" role="tablist" aria-label="Period">
            {scopes.map((k) => <button key={k} type="button" role="tab" aria-selected={sc === k} className={sc === k ? "on" : ""} onClick={() => setPick(k)}>{x.views[k]!.label} · {x.views[k]!.period}{x.views[k]!.triggered ? "" : " (no flag)"}</button>)}
          </div>
        )}
        {scopes.length === 1 && <p className="plf-lbl">{v.label}</p>}
        <Block v={v} lender={x.lender} recent={sc === "annual" ? x.views.quarterly : undefined} />
      </section>
      <h4>Explore this insight</h4>
      <div className="plf-tabs plf-explore" role="tablist" aria-label="Explore this insight" onKeyDown={onTabKey}>
        {TABS.map(([k, l]) => <button key={k} type="button" role="tab" id={`plf-t-${k}`} aria-selected={tab === k} aria-controls="plf-pane" tabIndex={tab === k ? 0 : -1} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>)}
      </div>
      <div className="plf-pane" id="plf-pane" role="tabpanel" aria-labelledby={`plf-t-${tab}`} key={tab}>{body}</div>
      <p className="plf-f">Based on reported figures{x.lender ? " (for a bank or lender, operating profit is not shown)" : ""}. Information only, not advice.</p>
    </aside>
  );
}

/** True when the reader is not on the alert's own section: the next section (trends) is past the middle of the screen, the results are far above, or the
 *  reader has gone back up so the results are still well below the fold. `nextTop` is null when the next section is not on the page. */
export function isAway(barTop: number, barBottom: number, nextTop: number | null, vh: number): boolean {
  return (nextTop != null && nextTop < vh * 0.45) || barBottom < -vh * 0.8 || barTop > vh * 0.85;
}

export function PlFlagsLayer({ f, lender = false }: { f?: Financials; lender?: boolean }) {
  // both series come from the same stored financials report as the results tables and the quarter section, so a new quarter shows after a refresh
  const items = useMemo(() => plInsights({ annual: f?.yearly?.pl, quarterly: f?.quarterly?.pl, lender }), [f, lender]);
  const flags = useMemo(() => items.flatMap((x) => x.flags), [items]);
  const [on, setOn] = useState(read), [shown, setShown] = useState(false), [dismissed, setDismissed] = useState(false), [away, setAway] = useState(false), [forced, setForced] = useState(false), [landed, setLanded] = useState(false);
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
  // the notice belongs to its section: it goes by itself when the reader moves to another section, and a small edge tab brings it back
  useEffect(() => {
    if (!shown) return;
    const check = () => {
      const r = bar.current?.getBoundingClientRect(), next = document.getElementById("trends");
      const a = isAway(r?.top ?? 0, r?.bottom ?? 0, next ? next.getBoundingClientRect().top : null, window.innerHeight);
      setAway(a);
      if (a) setLanded(true); else setForced(false);
    };
    check();
    window.addEventListener("scroll", check, { passive: true });
    window.addEventListener("resize", check);
    return () => { window.removeEventListener("scroll", check); window.removeEventListener("resize", check); };
  }, [shown]);
  const gone = dismissed || (away && !forced);
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
        <button type="button" className="plf-btn" onClick={() => { setDismissed(false); setForced(true); setShown(true); }}>Show details</button>
      </div>
      {shown && !gone && <FlagCard items={items} onClose={() => { setDismissed(true); setLanded(true); }} onAnimationEnd={land} />}
      {shown && !dismissed && away && !forced && (
        <button type="button" className="plf-edge" aria-label={`Open alert: ${items[0].title}`} title="Open the earnings alert" onClick={() => setForced(true)}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6" /><path d="M20 20l-4.5-4.5M4 8V5a1 1 0 011-1h3M20 8V5a1 1 0 00-1-1h-3" /></svg><i className="plf-dot" aria-hidden="true" />
        </button>
      )}
    </>
  );
}
