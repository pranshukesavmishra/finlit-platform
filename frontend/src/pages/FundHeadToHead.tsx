// Fund Compare, head to head: two funds of one category over 1, 3, 5 or 10 years, on four questions (returns, risk, consistency, costs), each
// fund also against its category's average. The default view of /funds/compare (the 2 to 4 scheme compare is /funds/compare?ids=...).
// Data: /api/mf-compare (backend/finlit/mf_compare.py). Every figure states its period and source; a missing one says why. Information only.
// Colours are fixed per fund everywhere: A blue, B orange, category average green (dotted in charts). A shaded table cell only marks the higher (or,
// for swing and fall, the smaller) figure of the two funds in the past; it is never a recommendation.
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { PageArt } from "../components/PageArt";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import { dateIN, nf } from "../lib/format";
import { factValueText, searchOptions, type FactVal } from "../lib/mf";
import {
  CARDS, PERIODS, cardTeaser, consistencyLine, costsLine, h2hToParams, leader, parseH2H, pct, periodBlock, periodWords, pickCategory, returnsLine, riskLine, rupees, share,
  shortName, signedPct, useCompareCategories, useCompareFunds, useHeadToHead, type Card, type CostFacts, type H2HState, type HeadToHead, type Side,
} from "../lib/mfCompare";
import { H2HChart, RangeBars, SIDE_COLOR, SIDE_DASH, SIDE_LETTER, type SideSeries } from "../mf/H2HChart";
import { Foot, GTerm } from "../mf/Bits";
import "../styles/mf.css";
import "../styles/mfcompare.css";

const SIDES: Side[] = ["a", "b", "cat"];
const NAME: Record<Side, string> = { a: "Fund A", b: "Fund B", cat: "Category average" };
const CARD_ICON: Record<Card, "growth" | "gauge" | "bars" | "coins"> = { returns: "growth", risk: "gauge", consistency: "bars", costs: "coins" };

/** The fund's letter in its colour (the category average: a dotted green line). Used the same way in the selectors, legend, tables, charts and bars. */
function Badge({ side }: { side: Side }) {
  return side === "cat"
    ? <span className="h2h-key-line" style={{ borderTopColor: SIDE_COLOR.cat }} aria-hidden="true" />
    : <span className={`h2h-badge ${side}`} aria-hidden="true">{SIDE_LETTER[side]}</span>;
}

// ================================================================================================ a searchable menu

type Opt = { value: string; label: string; sub?: string; count?: number };
const SHOW_MAX = 150;

function SearchSelect({ label, hint, value, items, onChange, placeholder, disabled, badge }: {
  label: string; hint?: string; value: string; items: Opt[]; onChange: (v: string) => void; placeholder: string; disabled?: boolean; badge?: Side;
}) {
  const [open, setOpen] = useState(false), [q, setQ] = useState(""), [at, setAt] = useState(0);
  const root = useRef<HTMLDivElement>(null), input = useRef<HTMLInputElement>(null), btn = useRef<HTMLButtonElement>(null);
  const id = useId();
  const all = useMemo(() => searchOptions(items, q, (i) => `${i.label} ${i.sub || ""}`), [items, q]);
  const shown = all.slice(0, SHOW_MAX);
  const current = items.find((i) => i.value === value);
  useEffect(() => {
    if (!open) return;
    input.current?.focus();
    const out = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", out);
    return () => document.removeEventListener("mousedown", out);
  }, [open]);
  useEffect(() => { setAt(0); }, [q]);
  useEffect(() => { if (open) document.getElementById(`${id}-${at}`)?.scrollIntoView({ block: "nearest" }); }, [at, id, open]);
  const choose = (v: string) => { onChange(v); setOpen(false); setQ(""); btn.current?.focus(); };
  const key = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setAt((a) => Math.min(shown.length - 1, a + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setAt((a) => Math.max(0, a - 1)); }
    else if (e.key === "Enter") { e.preventDefault(); if (shown[at]) choose(shown[at].value); }
    else if (e.key === "Escape") { setOpen(false); btn.current?.focus(); }
  };
  return (
    <div className={"mf-pick h2h-pick" + (badge ? ` h2h-s${badge}` : "")} ref={root}>
      <span className="label" id={`${id}-l`}>{label}</span>
      <button type="button" ref={btn} className="mf-pick-b" aria-haspopup="listbox" aria-expanded={open} aria-labelledby={`${id}-l ${id}-v`} disabled={disabled} onClick={() => setOpen((o) => !o)}>
        {badge && <Badge side={badge} />}
        <span id={`${id}-v`} className={current ? "" : "ph"}>{current ? current.label : placeholder}</span><span aria-hidden="true" className="h2h-caret">▾</span>
      </button>
      {hint && <small className="faint h2h-hint">{hint}</small>}
      {open && (
        <div className="mf-pick-pop h2h-pop">
          <input ref={input} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={key} placeholder="Type to search…" aria-label={`Search: ${label}`}
            role="combobox" aria-expanded="true" aria-controls={`${id}-list`} aria-activedescendant={shown.length ? `${id}-${at}` : undefined} autoComplete="off" spellCheck={false} />
          <ul id={`${id}-list`} role="listbox" aria-label={label}>
            {shown.map((i, n) => (
              <li key={i.value} id={`${id}-${n}`} role="option" aria-selected={i.value === value} className={at === n ? "on" : ""} onMouseDown={(e) => { e.preventDefault(); choose(i.value); }}>
                <span>{i.label}{i.sub && <small className="h2h-sub">{i.sub}</small>}</span>{i.count != null && <small>{i.count.toLocaleString("en-IN")}</small>}
              </li>))}
            {!shown.length && <li className="mf-pick-none" role="presentation">Nothing matches “{q}”.</li>}
            {all.length > SHOW_MAX && <li className="mf-pick-none" role="presentation">{all.length - SHOW_MAX} more: type to narrow the list.</li>}
          </ul>
        </div>)}
    </div>
  );
}

// ================================================================================================ small pieces

/** A figure, or a dash that says why there is none (on hover, and to screen readers). */
function Val({ v, why, fmt = pct }: { v: number | null | undefined; why?: string | null; fmt?: (v: number) => string }) {
  if (v == null) return <span className="mf-na" title={why || undefined} aria-label={why ? `No figure. ${why}` : "No figure"}>—</span>;
  return <>{fmt(v)}</>;
}
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "pos" : "neg");

type Row = {
  label: React.ReactNode; cell: (s: Side) => React.ReactNode; head?: boolean;
  lead?: { get: (s: "a" | "b") => number | null | undefined; dir: "high" | "low" };   // shade the higher / lower of the two funds
};
/** Rows of figures for A, B and the category average. Wide screens: a table. Phones: every row becomes a small card, one labelled line per column. */
function Table({ d, caption, rows }: { d: HeadToHead; caption: string; rows: Row[] }) {
  return (
    <div className="tw"><table className="mf-cmp h2h-t">
      <caption className="sr-only">{caption}</caption>
      <thead><tr><th scope="col"><span className="sr-only">Measure</span></th>
        {SIDES.map((s) => <th scope="col" key={s} className={"col-" + s}><span className="h2h-th"><Badge side={s} />{NAME[s]}</span><small>{s === "cat" ? d.category.short : shortName(d.funds[s].name)}</small></th>)}</tr></thead>
      <tbody>{rows.map((r, i) => {
        if (r.head) return <tr key={i} className="mf-grp"><th scope="colgroup" colSpan={4}>{r.label}</th></tr>;
        const win = r.lead ? leader(r.lead.get("a"), r.lead.get("b"), r.lead.dir) : null;
        return (
          <tr key={i}><th scope="row">{r.label}</th>
            {SIDES.map((s) => (
              <td key={s} data-label={NAME[s]} data-side={s} className={win === s ? "win" : undefined}>
                <span className="cell">{r.cell(s)}</span>{win === s && <span className="sr-only"> (the {r.lead!.dir === "high" ? "higher" : "lower"} of the two funds)</span>}
              </td>))}
          </tr>);
      })}</tbody>
    </table></div>
  );
}

const Key = ({ children }: { children: React.ReactNode }) => <p className="h2h-keynote faint"><span className="h2h-keysw" aria-hidden="true" />{children}</p>;
const Verdict = ({ text }: { text: string }) => <p className="h2h-verdict" role="status"><Icon name="spark" /><span>{text}</span></p>;

/** The reasons figures are missing, once each, under a table. */
function Whys({ d }: { d: HeadToHead }) {
  const lines = [d.why.a && `Fund A: ${d.why.a}`, d.why.b && `Fund B: ${d.why.b}`, !d.category.pending && d.category.why && `Category average: ${d.category.why}`].filter(Boolean) as string[];
  return lines.length ? <ul className="h2h-whys faint">{lines.map((l) => <li key={l}>{l}</li>)}</ul> : null;
}

// ================================================================================================ the four cards

type Names = { a: string; b: string };
const sideNames = (n: Names): Record<Side, string> => ({ a: n.a, b: n.b, cat: "Category average" });
const toSeries = (pts: Partial<Record<Side, { t: string[]; v: number[] }>>, n: Names): SideSeries[] =>
  SIDES.filter((s) => pts[s]).map((s) => ({ side: s, label: s === "cat" ? "Category average" : n[s], t: pts[s]!.t, v: pts[s]!.v }));

function ReturnsPanel({ d, names }: { d: HeadToHead; names: Names }) {
  const r = d.returns, roll = r.rolling, perYear = r.kind === "cagr", rollYear = roll.kind === "cagr";
  const growth = toSeries(r.growth, names), rolling = toSeries(roll.chart, names);
  const f = r.funds, rf = roll.funds;
  const rows: Row[] = [
    { label: perYear ? <GTerm id="cagr-compound-annual-growth-rate">Return per year (CAGR)</GTerm> : "Return over 1 year (total)", lead: { get: (s) => f[s].value, dir: "high" },
      cell: (s) => <b className={tone(f[s].value)}><Val v={f[s].value} why={f[s].why} fmt={(v) => signedPct(v, 2)} /></b> },
    { label: "₹10,000 invested became", lead: { get: (s) => f[s].growth, dir: "high" }, cell: (s) => <Val v={f[s].growth} why={f[s].why} fmt={rupees} /> },
    { label: <>Rolling {roll.label} returns{rollYear ? ", per year" : " (total change)"}</>, head: true, cell: () => null },
    { label: "Lowest", lead: { get: (s) => rf[s].min, dir: "high" }, cell: (s) => <><Val v={rf[s].min} why={rf[s].why} fmt={(v) => signedPct(v)} />{rf[s].minAt && <small className="faint"> to {dateIN(rf[s].minAt!)}</small>}</> },
    { label: "Median (middle)", lead: { get: (s) => rf[s].median, dir: "high" }, cell: (s) => <Val v={rf[s].median} why={rf[s].why} fmt={(v) => signedPct(v)} /> },
    { label: "Highest", lead: { get: (s) => rf[s].max, dir: "high" }, cell: (s) => <><Val v={rf[s].max} why={rf[s].why} fmt={(v) => signedPct(v)} />{rf[s].maxAt && <small className="faint"> to {dateIN(rf[s].maxAt!)}</small>}</> },
    { label: "Windows with a gain", lead: { get: (s) => rf[s].positive, dir: "high" }, cell: (s) => <Val v={rf[s].positive} why={rf[s].why} fmt={(v) => `${nf(v, 0)}%`} /> },
    { label: "Windows measured", cell: (s) => rf[s].count ? rf[s].count.toLocaleString("en-IN") : <Val v={null} why={rf[s].why} /> },
  ];
  return (
    <>
      <Verdict text={returnsLine(d, names)} />
      <Table d={d} caption={`Returns over ${periodWords(d.period)}`} rows={rows} />
      <Key>Shaded: the higher of the two funds. It describes the past, not what to choose.</Key>
      <Whys d={d} />
      {growth.length > 0 && <div className="h2h-block"><h4 className="mf-h4">Growth of ₹10,000</h4>
        <H2HChart series={growth} base={10000} format={(v) => rupees(v)} label={`Value of ₹10,000 invested on ${d.from ? dateIN(d.from) : "the start date"}, NAV only`} />
        <p className="faint mf-fine">Each line starts at ₹10,000 on the fund's NAV of {d.from ? dateIN(d.from) : "the start date"} (or the NAV just before it) and follows the NAV. NAV already counts the fund's costs; taxes and exit loads are not taken off.</p></div>}
      <div className="h2h-block"><h4 className="mf-h4">How far the {roll.label} returns ranged</h4>
        <RangeBars stats={rf} names={sideNames(names)} fmt={(v) => signedPct(v)} unit={roll.label} />
        <p className="faint mf-fine">Each bar runs from the fund's lowest to its highest {roll.label} {rollYear ? "per-year " : ""}return over the period, the white tick is the median, the line marks zero. A short bar high up means the start day mattered little.</p></div>
      {rolling.length > 0 && <div className="h2h-block"><h4 className="mf-h4">Rolling {roll.label} returns</h4>
        <H2HChart series={rolling} base={0} format={(v) => signedPct(v, 0)} tipFormat={(v) => signedPct(v)} label={`Return over each ${roll.label} window ending on the day shown`} />
        <p className="faint mf-fine">Each point is the {rollYear ? "per-year return" : "total return"} over the {roll.label} that ended that day, for every trading day of the period with a whole window behind it. A line that stays high and narrow means the fund did well whenever someone happened to invest; wide swings mean the start day mattered a lot.</p></div>}
    </>
  );
}

function RiskPanel({ d, names }: { d: HeadToHead; names: Names }) {
  const f = d.risk.funds;
  const ddNote = (m: HeadToHead["risk"]["funds"]["a"]["maxDrawdown"]) => m.peak && m.trough
    ? <small className="faint h2h-dates">{dateIN(m.peak)} to {dateIN(m.trough)}; {m.recovered ? `back to the high on ${dateIN(m.recovered)}` : "not back to the high yet"}</small> : null;
  const rows: Row[] = [
    { label: <><GTerm id="volatility">Volatility</GTerm>, a year</>, lead: { get: (s) => f[s].volatility.value, dir: "low" }, cell: (s) => <Val v={f[s].volatility.value} why={f[s].volatility.why} fmt={(v) => pct(v, 2)} /> },
    { label: "Downside deviation, a year", lead: { get: (s) => f[s].downside.value, dir: "low" }, cell: (s) => <Val v={f[s].downside.value} why={f[s].downside.why} fmt={(v) => pct(v, 2)} /> },
    { label: <><GTerm id="drawdown">Largest fall</GTerm> (from a high)</>, lead: { get: (s) => f[s].maxDrawdown.value, dir: "high" },
      cell: (s) => <><b className={tone(f[s].maxDrawdown.value)}><Val v={f[s].maxDrawdown.value} why={f[s].maxDrawdown.why} fmt={(v) => pct(v, 2)} /></b>{ddNote(f[s].maxDrawdown)}</> },
    { label: "Worst calendar month", lead: { get: (s) => f[s].worstMonth.value, dir: "high" },
      cell: (s) => <><span className={tone(f[s].worstMonth.value)}><Val v={f[s].worstMonth.value} why={f[s].worstMonth.why} fmt={(v) => signedPct(v)} /></span>{f[s].worstMonth.month && <small className="faint"> {f[s].worstMonth.month}</small>}</> },
    { label: "Best calendar month", lead: { get: (s) => f[s].bestMonth.value, dir: "high" },
      cell: (s) => <><span className={tone(f[s].bestMonth.value)}><Val v={f[s].bestMonth.value} why={f[s].bestMonth.why} fmt={(v) => signedPct(v)} /></span>{f[s].bestMonth.month && <small className="faint"> {f[s].bestMonth.month}</small>}</> },
    { label: <><GTerm id="sharpe-ratio">Sharpe ratio</GTerm> <small className="faint">(at an assumed {nf(d.risk.riskFree, 0)}% risk-free)</small></>, lead: { get: (s) => f[s].sharpe.value, dir: "high" },
      cell: (s) => <Val v={f[s].sharpe.value} why={f[s].sharpe.why} fmt={(v) => (v < 0 ? "−" : "") + nf(Math.abs(v), 2)} /> },
  ];
  return (
    <>
      <Verdict text={riskLine(d, names)} />
      <Table d={d} caption={`Risk over ${periodWords(d.period)}`} rows={rows} />
      <Key>Shaded: the smaller swing or fall (or the higher Sharpe ratio, best month) of the two funds. It describes the past, not what to choose.</Key>
      <Whys d={d} />
      <p className="faint mf-fine">Volatility is how much the NAV swings day to day, as a yearly figure (standard deviation of daily NAV changes × √252). Downside deviation counts only the falls. The largest fall is the deepest drop from a NAV high to a later low inside the period. {d.risk.note} All of these describe the past, not what comes next.</p>
    </>
  );
}

function Split({ a, b, n, label }: { a: number; b: number; n: number; label: string }) {
  if (!n) return null;
  const pa = (100 * a) / n, pb = (100 * b) / n;
  return (
    <div className="h2h-split" role="img" aria-label={`${label}: Fund A ahead in ${a} of ${n}, Fund B in ${b}${n - a - b ? `, level in ${n - a - b}` : ""}.`}>
      <span style={{ width: `${pa}%`, background: SIDE_COLOR.a }} />
      <span style={{ width: `${100 - pa - pb}%` }} className="tie" />
      <span style={{ width: `${pb}%`, background: SIDE_COLOR.b }} />
    </div>
  );
}

function ConsistencyPanel({ d, names }: { d: HeadToHead; names: Names }) {
  const c = d.consistency, w = c.window.label;
  const tile = (title: string, t: { a: number; b: number; n: number; why: string | null }, unit: string) => (
    <div className="mf-tile h2h-tile">
      <dt>{title}</dt>
      <dd>{t.n ? <>
        <span className="h2h-score"><b className={t.a > t.b ? "win" : ""}><Badge side="a" />{t.a.toLocaleString("en-IN")}</b><b className={t.b > t.a ? "win" : ""}><Badge side="b" />{t.b.toLocaleString("en-IN")}</b></span>
        <Split a={t.a} b={t.b} n={t.n} label={title} />
        <small className="faint">of {t.n.toLocaleString("en-IN")} {unit}{t.n - t.a - t.b ? `, ${t.n - t.a - t.b} level` : ""}</small></>
        : <small className="mf-why">{t.why || "Nothing to count in this period."}</small>}</dd>
    </div>
  );
  const vs = (k: "a" | "b") => c.vsCategory[k];
  return (
    <>
      <Verdict text={consistencyLine(d, names)} />
      <dl className="mf-ret3 h2h-tiles">
        {tile(`Ahead in ${w} windows`, c.rolling, `${w} windows`)}
        {tile("Calendar months won", c.months, "whole months")}
        {tile("Calendar years won", c.years, "whole years")}
      </dl>
      <div className="h2h-vs">
        <h4 className="mf-h4">Ahead of the category average</h4>
        <ul>{(["a", "b"] as const).map((k) => {
          const p = vs(k).pct;
          return (
            <li key={k}><Badge side={k} /><span className="nm">{names[k]}</span>
              <b className={leader(vs("a").pct, vs("b").pct, "high") === k ? "win" : ""}>{vs(k).beat != null && vs(k).n ? share(vs(k).beat!, vs(k).n) : <Val v={null} why={vs(k).why} />}</b>
              <span className="h2h-meter" role="img" aria-label={p != null ? `${Math.round(p)}% of the ${w} windows` : "No figure"}><span style={{ width: `${p ?? 0}%`, background: SIDE_COLOR[k] }} /></span>
              <small className="faint">of the {w} windows</small></li>);
        })}</ul>
      </div>
      {c.years.rows.length > 0 && (
        <div className="tw"><table className="mf-cmp h2h-t h2h-years">
          <caption className="sr-only">Return in each whole calendar year of the period</caption>
          <thead><tr><th scope="col">Year</th><th scope="col" className="col-a"><span className="h2h-th"><Badge side="a" />Fund A</span></th><th scope="col" className="col-b"><span className="h2h-th"><Badge side="b" />Fund B</span></th>
            <th scope="col" className="col-cat"><span className="h2h-th"><Badge side="cat" />Category average</span></th><th scope="col">Ahead</th></tr></thead>
          <tbody>{c.years.rows.map((y) => {
            const win = leader(y.a, y.b, "high");
            return (
              <tr key={y.year}><th scope="row">{y.year}</th>
                <td data-label="Fund A" data-side="a" className={win === "a" ? "win" : undefined}><span className={"cell " + tone(y.a)}><Val v={y.a} fmt={(v) => signedPct(v)} /></span></td>
                <td data-label="Fund B" data-side="b" className={win === "b" ? "win" : undefined}><span className={"cell " + tone(y.b)}><Val v={y.b} fmt={(v) => signedPct(v)} /></span></td>
                <td data-label="Category average" data-side="cat"><span className={"cell " + tone(y.cat)}><Val v={y.cat} fmt={(v) => signedPct(v)} /></span></td>
                <td data-label="Ahead"><span className="cell">{y.a == null || y.b == null ? "—" : !win ? "Level" : win.toUpperCase()}</span></td></tr>);
          })}</tbody>
        </table></div>)}
      <Whys d={d} />
      <p className="faint mf-fine">A {w} window is the {w} ending on one trading day; every trading day of the period with a whole window behind it counts once. Calendar months and years count only those wholly inside the period (the first, part-covered one and the unfinished current one are left out). Being ahead often in the past says nothing certain about the future.</p>
    </>
  );
}

const COST_ROWS: { k: keyof CostFacts; label: React.ReactNode }[] = [
  { k: "ter", label: <GTerm id="expense-ratio">Expense ratio (TER), a year</GTerm> }, { k: "exitLoad", label: <GTerm id="exit-load">Exit load</GTerm> },
  { k: "aum", label: "Fund size (AUM)" }, { k: "benchmark", label: "Benchmark index" }, { k: "managers", label: "Fund managers" },
  { k: "riskometer", label: "Risk-o-meter" }, { k: "launchDate", label: "Launch date" },
];

function Fact({ f }: { f: FactVal }) {
  const text = factValueText(f);
  if (!text) { const why = "unavailable" in f ? f.unavailable : "The source gives no value."; return <span className="mf-na" title={why}>—<small className="mf-why h2h-dates">{why}</small></span>; }
  return <>{text}{!("unavailable" in f) && (f.asOf || f.source) && <small className="faint h2h-dates">{[f.asOf ? `As of ${dateIN(f.asOf)}` : "", f.source || ""].filter(Boolean).join(" · ")}</small>}</>;
}

function CostsPanel({ d, names }: { d: HeadToHead; names: Names }) {
  const f = d.costs.funds, al = d.costs.alpha;
  const lowTer = leader(f.a.terPct, f.b.terPct, "low"), hiAlpha = leader(al.a.value, al.b.value, "high");
  return (
    <>
      <Verdict text={costsLine(d, names)} />
      <div className="tw"><table className="mf-cmp h2h-t h2h-costs">
        <caption className="sr-only">Costs and fund facts</caption>
        <thead><tr><th scope="col"><span className="sr-only">Fact</span></th>{(["a", "b"] as const).map((k) => <th scope="col" key={k} className={"col-" + k}><span className="h2h-th"><Badge side={k} />{NAME[k]}</span><small>{names[k]}</small></th>)}</tr></thead>
        <tbody>
          {COST_ROWS.map((r) => <tr key={r.k}><th scope="row">{r.label}</th>{(["a", "b"] as const).map((k) => (
            <td key={k} data-label={NAME[k]} data-side={k} className={r.k === "ter" && lowTer === k ? "win" : undefined}><span className="cell"><Fact f={f[k][r.k] as FactVal} /></span></td>))}</tr>)}
          <tr className="mf-grp"><th scope="colgroup" colSpan={3}>Excess return over the category average, a year ({periodWords(d.period)})</th></tr>
          <tr><th scope="row">Fund minus category average</th>{(["a", "b"] as const).map((k) => (
            <td key={k} data-label={NAME[k]} data-side={k} className={hiAlpha === k ? "win" : undefined}><span className="cell"><b className={tone(al[k].value)}><Val v={al[k].value} why={al[k].why} fmt={(v) => `${v < 0 ? "−" : v > 0 ? "+" : ""}${nf(Math.abs(v), 2)} points`} /></b></span></td>))}</tr>
        </tbody>
      </table></div>
      <Key>Shaded: the lower expense ratio and the higher excess return of the two funds. It describes the past, not what to choose.</Key>
      <Whys d={d} />
      <p className="faint mf-fine">{d.costs.alphaNote} The expense ratio shown is the {d.funds.a.plan === d.funds.b.plan ? d.funds.a.plan : "each fund's own"} plan's; it is already taken out of the NAV, so every return on this page is after it.</p>
    </>
  );
}

// ================================================================================================ the page

export function FundHeadToHead() {
  useDocTitle("Fund Compare", "Two mutual funds of the same category, head to head over 1, 3, 5 or 10 years: returns, risk, consistency and costs, each against the category average. Information only.");
  const [sp, setSp] = useSearchParams();
  const s = useMemo(() => parseH2H(sp), [sp]);
  const cats = useCompareCategories();
  const category = pickCategory(cats.data?.categories, s.category)?.name || s.category;
  const funds = useCompareFunds(category, s.plan);
  const set = (patch: Partial<H2HState>) => setSp(h2hToParams({ ...s, category, ...patch }), { replace: true });
  const list = funds.data?.funds || [];
  const fa = list.find((f) => f.code === s.a), fb = list.find((f) => f.code === s.b);
  const dataDate = funds.data?.dataDate || cats.data?.dataDate || null;
  const blocked = useMemo(() => Object.fromEntries(PERIODS.map((p) => [p, periodBlock(p, [fa, fb], dataDate)])) as Record<string, string | null>, [fa, fb, dataDate]);
  const h = useHeadToHead(s.a, s.b, s.period);
  const d = h.data;
  const stale = !!d && (d.funds.a.code !== s.a || d.funds.b.code !== s.b || d.period !== s.period);

  const catItems: Opt[] = useMemo(() => (cats.data?.categories || []).filter((c) => (s.plan === "Direct" ? c.direct : c.regular) >= 2)
    .map((c) => ({ value: c.name, label: c.short, sub: c.group, count: s.plan === "Direct" ? c.direct : c.regular })), [cats.data, s.plan]);
  const fundItems = (other: number): Opt[] => list.filter((f) => f.code !== other).map((f) => ({ value: String(f.code), label: shortName(f.name), sub: `${f.amc.replace(/\s*mutual fund\s*$/i, "")}${f.launch ? ` · since ${dateIN(f.launch, { month: "short", year: "numeric" })}` : ""}` }));
  const names = d ? { a: shortName(d.funds.a.name), b: shortName(d.funds.b.name) } : { a: "Fund A", b: "Fund B" };
  const errText = h.error ? (h.error.status === 400 || h.error.status === 404 ? h.error.message : h.error.status === 503 && h.error.body.status === "demo" ? h.error.message : "This comparison is unavailable right now. Please try again in a moment.") : "";
  const pholder = !category ? "Choose a category first" : funds.isLoading ? "Loading funds…" : `Choose from ${list.length.toLocaleString("en-IN")} funds`;
  const blockedList = PERIODS.filter((p) => blocked[p]);

  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><PageArt kind="portfolio" />
        <div className="eyebrow">Mutual funds</div><h1>Fund Compare</h1><p>Two funds of the same category, head to head: returns, risk, consistency and costs over 1, 3, 5 or 10 years, each also against the category average. Information only, never advice.</p></div></section>
      <div className="wrap mf h2h">
        <section className="card mf-card h2h-setup" aria-labelledby="h2h-h">
          <div className="h2h-setup-h">
            <h3 id="h2h-h"><span className="ci"><Icon name="compare" /></span><span>Compare performance, consistency and risk<small>Choose a category, then two of its funds and a period.</small></span></h3>
            <Link className="mf-linkbtn" to="/funds/compare?ids=">Compare up to 4 schemes instead</Link>
          </div>
          <div className="h2h-row">
            <SearchSelect label="Mutual fund category" hint="Compare funds within the same category" value={category} items={catItems} placeholder={cats.isLoading ? "Loading categories…" : "Choose a category"}
              disabled={!catItems.length} onChange={(v) => set({ category: v, a: 0, b: 0 })} />
            <div className="mf-seg-w"><span className="label" id="h2h-plan">Plan</span>
              <div className="seg" role="group" aria-labelledby="h2h-plan">{(["Direct", "Regular"] as const).map((p) => <button key={p} type="button" aria-pressed={s.plan === p} onClick={() => set({ plan: p, a: 0, b: 0 })}>{p}</button>)}</div>
              <small className="faint h2h-hint">Growth option of each fund</small></div>
          </div>
          <div className="h2h-pair">
            <SearchSelect label="Fund A" badge="a" value={s.a ? String(s.a) : ""} items={fundItems(s.b)} disabled={!list.length} onChange={(v) => set({ a: Number(v) })} placeholder={pholder} />
            <button type="button" className="h2h-swap" aria-label="Swap Fund A and Fund B" title="Swap Fund A and Fund B" disabled={!s.a && !s.b} onClick={() => set({ a: s.b, b: s.a })}>⇄</button>
            <SearchSelect label="Fund B" badge="b" value={s.b ? String(s.b) : ""} items={fundItems(s.a)} disabled={!list.length} onChange={(v) => set({ b: Number(v) })} placeholder={pholder} />
          </div>
          <div className="h2h-period"><span className="label" id="h2h-period">Investment period</span>
            <div className="seg" role="group" aria-labelledby="h2h-period">{PERIODS.map((p) => (
              <button key={p} type="button" aria-pressed={s.period === p} disabled={!!blocked[p] && s.period !== p} title={blocked[p] || undefined} onClick={() => set({ period: p })}><b>{p}</b><small>{periodWords(p)}</small></button>))}</div>
            {blockedList.length > 0 && <small className="faint h2h-hint">{blockedList.join(", ")} not available: {blocked[blockedList[blockedList.length - 1]]}</small>}
          </div>
        </section>

        {!(s.a && s.b) ? (
          <div className="pm-empty mf-empty"><b>Choose Fund A and Fund B.</b>
            <p>Pick a category, then two of its funds. Funds are compared on their Growth option and the same plan, over the same days, and each against the average of its category.</p></div>
        ) : h.error && !d ? (
          <div className="card mf-card" role="alert"><p>{errText}</p>{h.error.status >= 500 && <button className="btn" onClick={() => h.refetch()}>Try again</button>}</div>
        ) : !d ? (
          <div className="card" aria-busy="true"><div className="skeleton" style={{ height: 360 }} /></div>
        ) : (
          <div aria-busy={h.isFetching || stale} className={stale ? "h2h-stale" : undefined}>
            <section aria-labelledby="h2h-what">
              <div className="h2h-head">
                <h2 id="h2h-what">Compare what matters</h2>
                <p className="muted">{d.from && d.to ? <>{dateIN(d.from)} to {dateIN(d.to)} ({periodWords(d.period)}), {d.funds.a.plan === d.funds.b.plan ? `${d.funds.a.plan} plan, ` : ""}Growth option.</> : "No common period."}</p>
              </div>
              <ul className="h2h-legend" aria-label="Colours">
                {(["a", "b"] as const).map((k) => <li key={k}><Badge side={k} /><Link to={`/funds/${d.funds[k].code}`}>{names[k]}</Link></li>)}
                <li><svg width="26" height="8" aria-hidden="true"><line x1="1" y1="4" x2="25" y2="4" stroke={SIDE_COLOR.cat} strokeWidth="2.4" strokeLinecap="round" strokeDasharray={SIDE_DASH.cat} /></svg><span>Category average · {d.category.short}{d.category.members ? ` (${d.category.members} funds)` : ""}</span></li>
              </ul>
              <div className="h2h-cards" role="group" aria-label="What to compare">
                {CARDS.map((c) => { const t = cardTeaser(c.id, d); return (
                  <button key={c.id} type="button" className="h2h-card" aria-pressed={s.card === c.id} aria-controls="h2h-panel" onClick={() => set({ card: c.id as Card })}>
                    <span className="h2h-ico"><Icon name={CARD_ICON[c.id]} /></span>
                    <span className="h2h-ct">{c.title}</span><small>{c.sub}</small>{t && <em>{t}</em>}
                    <span className="h2h-tick" aria-hidden="true"><Icon name="check" /></span>
                  </button>); })}
              </div>
            </section>
            {d.pending && <p className="mf-note" role="status"><Icon name="info" /><span>{d.category.why}</span></p>}
            {d.planNote && <p className="mf-note warn" role="note"><Icon name="alert" /><span>{d.planNote}</span></p>}
            <section id="h2h-panel" className="card mf-card h2h-panel" aria-label={CARDS.find((c) => c.id === s.card)!.title}>
              {s.card === "returns" ? <ReturnsPanel d={d} names={names} /> : s.card === "risk" ? <RiskPanel d={d} names={names} /> : s.card === "consistency" ? <ConsistencyPanel d={d} names={names} /> : <CostsPanel d={d} names={names} />}
            </section>
            <div className="card mf-card h2h-about">
              <h4 className="mf-h4">About the category average</h4>
              <p className="muted">{d.category.pending ? d.category.why : d.category.note || d.category.why}{d.category.membersAtStart != null && d.category.members ? ` ${d.category.membersAtStart} of the ${d.category.members} had a NAV on the first day of this period; younger funds join on their first NAV.` : ""} {d.category.survivorship}</p>
              {(d.funds.a.history.source === "mirror" || d.funds.b.history.source === "mirror") && <p className="faint mf-fine">Some NAV history here comes from a third-party mirror of AMFI data (api.mfapi.in), used only after its NAV for AMFI's latest date was checked against AMFI's own. AMFI's own history is kept for five years, so the 10 year view always uses the mirror.</p>}
            </div>
          </div>
        )}
        <Foot facts={d || funds.data || cats.data || null} />
      </div>
    </>
  );
}
