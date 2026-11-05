import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import type { Financials } from "../lib/api";
import { highlightMap, insightChip, plInsights, type Growth, type Insight, type PeriodView, type Scope } from "../lib/plFlags";
import type { PlFlag } from "../lib/plFlags";
import { PLF_START, plfCardShown, plfEdgeShown, plfMode, plfReduce } from "./plfState";
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

/** Tiny line icons (16 x 16, stroke only) used instead of sentences. */
const IC = {
  split: "M2 5h4M2 11h12", wave: "M1 9c2-6 3-6 5-1s3 5 5-1 2-3 4-1", cal: "M3 4h10v9H3zM3 7h10M6 2v3M10 2v3", q: "M8 14v.1M6 6.5a2 2 0 113 1.7C8.3 8.7 8 9.2 8 10.5",
  clock: "M8 2.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM8 5v3.2l2 1.3", cost: "M8 2v12M11 5H6.6a1.8 1.8 0 000 3.6h2.8a1.8 1.8 0 010 3.6H5", spark: "M8 2l1.4 4.6L14 8l-4.6 1.4L8 14l-1.4-4.6L2 8l4.6-1.4z",
  down: "M2 5l4 4 3-3 5 6M11 12h3V9", up: "M2 11l4-4 3 3 5-6M11 4h3v3", pct: "M12.5 3.5l-9 9M5 3.5a1.5 1.5 0 100 3 1.5 1.5 0 000-3zM11 9.5a1.5 1.5 0 100 3 1.5 1.5 0 000-3z",
  info: "M8 2.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM8 7.2V11M8 5v.1", warn: "M8 2.5l6 10.5H2zM8 6.5v3M8 11.2v.1", bars: "M3 13V8M8 13V3M13 13V6", cash: "M2 4.5h12v7H2zM8 6.2a1.8 1.8 0 100 3.6 1.8 1.8 0 000-3.6z",
  search: "M7 3a4 4 0 100 8 4 4 0 000-8zM10 10l4 4", repeat: "M3 8a5 5 0 019-3M12 2v3H9M13 8a5 5 0 01-9 3M4 14v-3h3", gap: "M2 5h12M2 11h8M12 9l2 2-2 2", people: "M6 7a2 2 0 100-4 2 2 0 000 4zM2 13c0-2.5 1.8-4 4-4s4 1.5 4 4M11.5 7a1.6 1.6 0 100-3.2M12 9.2c1.5.3 2.5 1.5 2.5 3.8",
} as const;
type IconName = keyof typeof IC;
const Ico = ({ n }: { n: IconName }) => <svg className="plf-i" viewBox="0 0 16 16" aria-hidden="true"><path d={IC[n]} /></svg>;

type Chip = { ic: IconName; t: string; tip: string; tag?: "QoQ" | "YoY" };
const c = (ic: IconName, t: string, tip: string, tag?: "QoQ" | "YoY"): Chip => ({ ic, t, tip, tag });
/** Neutral, case-level pointers as compact chips: what could explain the gap and where to look. Possibilities only, never a verdict.
 *  The founder's longer wording stays on each chip as its tooltip and screen-reader description, and in full in the hidden `full` text. */
const MORE: Record<number, { why?: Chip[]; causes: Chip[]; check: Chip[]; full?: Record<Tab, string> }> = {
  1: {
    why: [c("split", "Sales vs profit gap", "Profit and sales moved very differently."), c("wave", "Quarter = momentum", "One quarter can be seasonal, so read it as momentum, not a trend.", "QoQ"),
      c("cal", "Year view = no seasonality", "Same-quarter view removes seasonality.", "YoY"), c("q", "Core gain or one-off?", "Strong profit growth may be real efficiency or a one-time boost.", "YoY")],
    causes: [c("cal", "Seasonal demand", "Seasonal demand.", "QoQ"), c("cost", "Cost change", "Sudden cost changes.", "QoQ"), c("spark", "One-time items", "One-time gains or expenses, discounting, higher interest or tax.", "QoQ"),
      c("down", "Lower input costs", "Costs growing slower than sales, lower input costs.", "YoY"), c("bars", "Weak base last year", "A weak base last year.", "YoY"), c("pct", "Lower interest/tax", "One-time gains, lower interest.", "YoY")],
    check: [c("cal", "Same quarter last year", "Same quarter last year.", "QoQ"), c("spark", "One-time items", "One-time items in the results.", "QoQ"), c("gap", "Operating vs net gap", "Gap between operating and net profit.", "QoQ"),
      c("search", "Core business profit?", "Is profit from the core business?", "YoY"), c("up", "Margin trend", "Is margin improving over several quarters?", "YoY"), c("cash", "Cash flow", "Is cash flow strong?", "YoY")],
    full: {
      why: "Quarter on quarter: Profit and sales moved very differently. One quarter can be seasonal, so read it as momentum, not a trend. Year on year: Same-quarter view removes seasonality. Strong profit growth may be real efficiency or a one-time boost.",
      causes: "Quarter on quarter: Seasonal demand, sudden cost changes, one-time gains or expenses, discounting, higher interest or tax. Year on year: Costs growing slower than sales, lower input costs, weak base last year, one-time gains, lower interest.",
      check: "Quarter on quarter: Same quarter last year. One-time items in the results. Gap between operating and net profit. Year on year: Is profit from the core business? Is margin improving over several quarters? Is cash flow strong?",
    },
  },
  2: { causes: [c("spark", "One-off gains", "One-off gains"), c("down", "Cost cuts or mix", "Cost cuts or a better product mix"), c("pct", "Lower interest/tax", "Lower tax or interest")], check: [c("up", "Margin trend", "Operating margin trend"), c("cash", "Other income", "Other income and exceptional items"), c("search", "Why sales fell", "Why sales fell")] },
  3: { causes: [c("cost", "Costs outpace sales", "Costs rising faster than sales"), c("down", "Weaker margins", "Weaker pricing or margins"), c("pct", "Higher interest/tax", "Higher interest, depreciation or tax"), c("spark", "One-off charges", "One-off charges")], check: [c("up", "Margin vs last year", "Operating margin against last year"), c("spark", "One-off items", "Exceptional items and one-off charges"), c("pct", "Interest and tax", "Interest and tax lines")] },
  4: { causes: [c("cost", "Costs match sales", "Costs rising as fast as sales"), c("pct", "Discounting", "Discounting to win volume"), c("spark", "One-off charges", "One-off charges in the period")], check: [c("up", "Margin trend", "Operating margin trend"), c("cost", "Input and staff costs", "Raw material and staff costs"), c("repeat", "Repeats next quarter?", "Whether the next quarter repeats it")] },
  5: { causes: [c("cash", "Other income", "Non-operating or other income"), c("spark", "One-off savings", "Exceptional savings or write-backs"), c("pct", "Lower interest/tax", "Lower tax or interest")], check: [c("cash", "Other income line", "Other income in the P&L"), c("gap", "Operating vs net gap", "Operating profit against net profit"), c("repeat", "Can it repeat?", "Whether the gain can repeat")] },
  6: { causes: [c("down", "Weaker demand", "Weaker demand or a slowdown"), c("people", "Price cuts, lost clients", "Price cuts or lost customers"), c("cost", "Fixed costs, less sales", "Fixed costs spread over lower sales")], check: [c("search", "Demand commentary", "Management commentary on demand"), c("bars", "Order book, volumes", "Order book or volumes"), c("people", "Peers the same?", "Whether peers saw the same")] },
  7: { causes: [c("cash", "Other income", "Other income or non-operating gains"), c("pct", "Lower tax", "Lower tax or a tax credit"), c("pct", "Lower interest", "Lower interest cost")], check: [c("cash", "Other income line", "Other income in the P&L"), c("pct", "Tax rate vs last year", "Tax rate against last year"), c("up", "Operating profit trend", "Operating profit trend")] },
  8: { causes: [c("cost", "Business or cost change", "A change in the business or its costs"), c("repeat", "Repeating one-offs", "Repeating one-off items"), c("pct", "Pricing or mix shift", "A shift in pricing or mix")], check: [c("cal", "Quarter vs year-ago", "Each quarter against the same one a year earlier"), c("up", "Margin over the run", "Operating margin over the run"), c("search", "Commentary", "Management commentary")] },
};
const WHY_SHORT: Record<number, [IconName, string]> = { 2: ["spark", "One-offs or cost cuts?"], 3: ["cost", "Cost or margin pressure?"], 4: ["warn", "Growth not reaching profit"], 5: ["cash", "Gains beyond operations?"], 6: ["down", "Possible slowdown"], 7: ["cash", "Non-operating gains?"], 8: ["repeat", "Structural change?"] };
const chipsOf = (x: Insight, tab: Tab): Chip[] => {
  const m = MORE[x.case];
  if (tab === "why") return m.why ?? [c(WHY_SHORT[x.case]?.[0] ?? "info", WHY_SHORT[x.case]?.[1] ?? "Why it matters", x.why)];
  return m[tab];
};
const fullOf = (x: Insight, tab: Tab) => MORE[x.case].full?.[tab] ?? chipsOf(x, tab).map((k) => k.tip.replace(/\.?$/, ".")).join(" ");

const SEV = { watch: "Watch", caution: "Investigate" } as const;
const sgn = (v: number) => (v < 0 ? "−" : v > 0 ? "+" : "") + Math.abs(v).toFixed(1) + "%";
const dir = (v: number) => (Math.abs(v) < 0.5 ? "flat" : v > 0 ? "up" : "down");
const WORD = { up: "Growing", down: "Declining", flat: "Flat" } as const;
const ARROW = { up: "M2 11l4-4 3 3 5-6M11 4h4v4", down: "M2 5l4 4 3-3 5 6M11 12h4V8", flat: "M2 8h12M11 5l3 3-3 3" } as const;

function Tile({ label, v }: { label: string; v: number | null }) {
  if (v == null) return <div className="plf-tile plf-flat" title="Not comparable: the earlier figure is nil or a loss"><span>{label}</span><b>—</b><em>Not comparable (earlier figure is nil or a loss)</em></div>;
  const d = dir(v);
  return (
    <div className={`plf-tile plf-${d}`} aria-label={`${label} ${sgn(v)}, ${WORD[d].toLowerCase()}`}>
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

/** Two bars, revenue growth against net profit growth, with the multiple ("3.3x faster") when one is at least 1.5 times the other and both are positive.
 *  It only draws the figures already shown in the tiles (the multiple is their ratio); nothing new is computed from raw data. */
export function GapBars({ g, sentence }: { g: Growth; sentence?: string | null }) {
  const r = g.revenue, p = g.profit;
  if (r == null || p == null) return null;
  const max = Math.max(Math.abs(r), Math.abs(p), 0.1);
  const w = (v: number) => `${Math.max(3, Math.round((Math.abs(v) / max) * 100))}%`;
  const both = r > 0 && p > 0, hi = Math.max(r, p), lo = Math.min(r, p);
  const mult = both && hi / lo >= 1.5 ? `${(hi / lo).toFixed(1)}x faster` : null;
  const who = p >= r ? "Net profit" : "Revenue";
  return (
    <div className="plf-gap" title={sentence || undefined} role="img" aria-label={`Revenue ${sgn(r)} against net profit ${sgn(p)}${mult ? `: ${who.toLowerCase()} ${mult}` : ""}`}>
      <span className="plf-gl">Rev</span><i className={`plf-bar-i ${dir(r) === "down" ? "d" : "u"}`} style={{ width: w(r) }} />
      <span className="plf-gl">Net</span><i className={`plf-bar-i ${dir(p) === "down" ? "d" : "u"}`} style={{ width: w(p) }} />
      {mult && <b className="plf-mult"><svg viewBox="0 0 16 16" aria-hidden="true"><path d={ARROW.up} /></svg>{who} {mult}</b>}
    </div>
  );
}

function Box({ kind, note, title, g, lender, sentence, extra }: { kind: "qoq" | "yoy"; note: string; title?: string; g: Growth; lender: boolean; sentence?: string | null; extra?: React.ReactNode }) {
  return (
    <section className={`plf-box plf-${kind}`} aria-label={kind === "qoq" ? "Quarter on quarter" : "Year on year"} title={title}>
      <header>
        <svg className="plf-bi" viewBox="0 0 16 16" aria-hidden="true"><path d={kind === "qoq" ? IC.bars : IC.cal} /></svg>
        <h5>{kind === "qoq" ? "Quarter-on-quarter" : "Year-on-year"} <span>({kind === "qoq" ? "QoQ" : "YoY"})</span></h5>
        <p>{note}</p>
      </header>
      <div className="plf-tiles">
        <Tile label="Revenue growth" v={g.revenue} />
        <Tile label="Net profit growth" v={g.profit} />
        {!lender && g.operating != null && <Tile label="Operating profit growth" v={g.operating} />}
      </div>
      <GapBars g={g} sentence={sentence} />
      {extra}
    </section>
  );
}

/** A quarter shows both comparisons as boxes (against the previous quarter, then against the same quarter a year earlier); the year shows the year,
 *  and says in one line how the latest quarter has moved since (`recent`), so a year that fell is not read without the newest quarter. */
export function Block({ v, lender, recent }: { v: PeriodView; lender: boolean; recent?: PeriodView }) {
  const q = v.scope === "quarterly";
  const flagged = v.triggered && v.text ? v.text.replace(/ Compared with [^.]*\.$/, "") : null;
  const ended = v.periodEnd ? ` Period ended ${dmy(v.periodEnd)}, against ${dmy(v.againstEnd)}.` : "";
  return (
    <div className="plf-blk" role="tabpanel">
      {q && v.qoq && line(v.qoq.growth, lender) && (
        <Box kind="qoq" note={`${v.qoq.period} compared with ${v.qoq.against} (the quarter before).`} g={v.qoq.growth} lender={lender} />
      )}
      <Box kind="yoy" note={`${v.period} compared with ${v.against}${q ? " (the same quarter a year earlier)" : ""}.`} title={`${v.period} compared with ${v.against}.${ended}`.trim()} g={v.growth} lender={lender} sentence={flagged}
        extra={!q && recent && line(recent.growth, lender) ? <p className="plf-qoq">Since then, the latest quarter ({recent.period}) against the same quarter a year earlier: {line(recent.growth, lender)}.</p> : null} />
      {!v.triggered && <p className="plf-sum">{`This situation does not show in the ${q ? "latest quarter" : "latest year"}.`}</p>}
    </div>
  );
}

/** The Insights box: three tabs, each a row of icon + 2 to 4 word chips. Hover, focus or tap a chip for its short explanation. */
export function Insights({ x }: { x: Insight }) {
  const [tab, setTab] = useState<Tab>("why"), [pin, setPin] = useState<number | null>(null);
  const chips = chipsOf(x, tab), cap = pin != null ? chips[pin] : null;
  useEffect(() => setPin(null), [tab, x.key]);
  const onTabKey = (e: React.KeyboardEvent) => {
    const n = TABS.length, at = TABS.findIndex(([k]) => k === tab);
    const to = e.key === "ArrowRight" ? (at + 1) % n : e.key === "ArrowLeft" ? (at + n - 1) % n : e.key === "Home" ? 0 : e.key === "End" ? n - 1 : -1;
    if (to < 0) return;
    e.preventDefault(); setTab(TABS[to][0]);
    (e.currentTarget.querySelectorAll<HTMLElement>('[role="tab"]')[to])?.focus();
  };
  return (
    <section className="plf-ins" aria-label="Insights">
      <div className="plf-insh">
        <h4>Insights</h4>
        <div className="plf-tabs plf-explore" role="tablist" aria-label="Insights" onKeyDown={onTabKey}>
          {TABS.map(([k, l]) => <button key={k} type="button" role="tab" id={`plf-t-${k}`} aria-selected={tab === k} aria-controls="plf-pane" tabIndex={tab === k ? 0 : -1} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>)}
        </div>
      </div>
      <div className="plf-pane" id="plf-pane" role="tabpanel" aria-labelledby={`plf-t-${tab}`} key={tab} onMouseLeave={() => setPin(null)}>
        <ul className="plf-chips">
          {chips.map((k, n) => (
            <li key={k.t}>
              <button type="button" className={`plf-c${pin === n ? " on" : ""}`} title={k.tip} aria-label={`${k.t}${k.tag ? ` (${k.tag})` : ""}: ${k.tip}`}
                onMouseEnter={() => setPin(n)} onFocus={() => setPin(n)} onClick={() => setPin(n)} style={{ animationDelay: `${n * 40}ms` }}>
                <Ico n={k.ic} />{k.t}{k.tag && <small className={`plf-tag plf-tag-${k.tag.toLowerCase()}`}>{k.tag}</small>}
              </button>
            </li>
          ))}
        </ul>
        <p className="plf-cap" aria-hidden="true">{cap ? <>{cap.tag && <b>{cap.tag === "QoQ" ? "Quarter on quarter" : "Year on year"}: </b>}{cap.tip}</> : " "}</p>
        <p className="plf-sr">{fullOf(x, tab)}</p>
      </div>
    </section>
  );
}

function FlagCard({ items, onClose, floating, onAnimationEnd }: { items: Insight[]; onClose: () => void; floating: boolean; onAnimationEnd: () => void }) {
  const [i, setI] = useState(0), [pick_, setPick] = useState<Scope | null>(null);
  const x = items[Math.min(i, items.length - 1)];
  const scopes = (["quarterly", "annual"] as const).filter((sc) => x.views[sc]);
  const sc: Scope = pick_ && x.views[pick_] ? pick_ : x.headline, v = x.views[sc]!, hv = x.views[x.headline]!;
  const pick = (n: number) => { setI(n); setPick(null); };
  return (
    <aside className={`plf-note${floating ? " plf-floating" : ""}`} role="status" aria-label="Flags from the latest results" onAnimationEnd={onAnimationEnd}>
      <div className="plf-top">
        <span className="plf-ico" aria-hidden="true"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6" /><path d="M20 20l-4.5-4.5M4 8V5a1 1 0 011-1h3M20 8V5a1 1 0 00-1-1h-3" /></svg></span>
        <div className="plf-tt"><b>{items.length === 1 ? "Worth a closer look" : `${items.length} things worth a closer look`}</b><small>Earnings intelligence · {hv.period} {x.headline === "quarterly" ? "quarter" : "year"}</small></div>
        <span className={`plf-sev plf-sev-${x.severity}`}>{SEV[x.severity]}</span>
        <button type="button" className="plf-x" aria-label={floating ? "Close, the alert tab stays on the edge" : "Dismiss"} title={floating ? "Close" : "Dismiss"} onClick={onClose}><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 3.5l9 9M12.5 3.5l-9 9" /></svg></button>
      </div>
      {items.length > 1 && (
        <div className="plf-pager" role="tablist" aria-label="Flags">
          {items.map((f, n) => <button key={f.key} type="button" role="tab" aria-selected={n === i} className={n === i ? "on" : ""} onClick={() => pick(n)}>{insightChip(f)}</button>)}
        </div>
      )}
      <div className="plf-body">
        <h3>{x.title}</h3>
        {scopes.length > 1 && (
          <div className="plf-tabs plf-views" role="tablist" aria-label="Period">
            {scopes.map((k) => <button key={k} type="button" role="tab" aria-selected={sc === k} className={sc === k ? "on" : ""} onClick={() => setPick(k)}>{x.views[k]!.label} · {x.views[k]!.period}{x.views[k]!.triggered ? "" : " (no flag)"}</button>)}
          </div>
        )}
        {scopes.length === 1 && <p className="plf-lbl">{v.label}</p>}
        <Block v={v} lender={x.lender} recent={sc === "annual" ? x.views.quarterly : undefined} />
        <Insights x={x} />
        <p className="plf-f">Based on reported figures{x.lender ? " (for a bank or lender, operating profit is not shown)" : ""}. Information only, not advice.</p>
      </div>
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
  const [on, setOn] = useState(read), [shown, setShown] = useState(false), [landed, setLanded] = useState(false);
  const [st, dispatch] = useReducer(plfReduce, PLF_START);
  const mode = plfMode(st), card = plfCardShown(mode), edge = plfEdgeShown(mode), gone = !card;
  const bar = useRef<HTMLDivElement>(null);
  const toggle = () => { setOn((v) => { write(!v); return !v; }); };
  // a different alert (another company, a new quarter) starts fresh: an earlier x does not carry over
  const sig = items.map((x) => x.key).join("|");
  useEffect(() => { dispatch({ type: "reset" }); }, [sig]);
  // the notice drops in once, the first time the results area comes into view
  useEffect(() => {
    if (!flags.length || !bar.current) return;
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setShown(true); io.disconnect(); } }, { rootMargin: "-80px 0px -30% 0px" });
    io.observe(bar.current);
    return () => io.disconnect();
  }, [flags.length]);
  useEffect(() => { if (shown && reduced()) setLanded(true); }, [shown]);
  // the notice belongs to its section: every scroll gives a fresh reading of where the reader is, and the state machine does the rest
  useEffect(() => {
    if (!shown) return;
    const check = () => {
      const r = bar.current?.getBoundingClientRect(), next = document.getElementById("trends");
      const a = isAway(r?.top ?? 0, r?.bottom ?? 0, next ? next.getBoundingClientRect().top : null, window.innerHeight);
      dispatch({ type: "scroll", away: a });
      if (a) setLanded(true);
    };
    check();
    window.addEventListener("scroll", check, { passive: true });
    window.addEventListener("resize", check);
    return () => { window.removeEventListener("scroll", check); window.removeEventListener("resize", check); };
  }, [shown]);
  // the floating card (opened from the edge tab) also closes by Esc or a click outside it
  useEffect(() => {
    if (mode !== "opened") return;
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") dispatch({ type: "close" }); };
    const down = (e: PointerEvent) => { if (!(e.target as Element | null)?.closest?.(".plf-note, .plf-edge")) dispatch({ type: "close" }); };
    document.addEventListener("keydown", key); document.addEventListener("pointerdown", down, true);
    return () => { document.removeEventListener("keydown", key); document.removeEventListener("pointerdown", down, true); };
  }, [mode]);
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
        <button type="button" className="plf-btn" onClick={() => { dispatch({ type: "show" }); dispatch({ type: "open" }); setShown(true); }}>Show details</button>
      </div>
      {shown && card && <FlagCard items={items} floating={mode === "opened"} onClose={() => { dispatch({ type: mode === "opened" ? "close" : "dismiss" }); setLanded(true); }} onAnimationEnd={land} />}
      {shown && edge && (
        <button type="button" className="plf-edge" aria-label={`Open alert: ${items[0].title}`} title="Open the earnings alert" onClick={() => dispatch({ type: "open" })}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6" /><path d="M20 20l-4.5-4.5M4 8V5a1 1 0 011-1h3M20 8V5a1 1 0 00-1-1h-3" /></svg><i className="plf-dot" aria-hidden="true" />
        </button>
      )}
    </>
  );
}
