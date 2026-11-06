import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { HScroll } from "../components/HScroll";
import { MINUS } from "../lib/format";
import { bandInk, bandVar, scoreBand, type ScoreBand } from "../lib/scoreBands";
import {
  TABS, blankWhy, changeText, columnsFor, dash, isReady, money, monthYear, nextTab, priceText, scoreOf, scoreWhy, sortLines, BASIS_WORD, FINLIT_PILLARS, PRISM_FOUR,
  type Col, type Line, type Model, type Period, type Ready, type Tab,
} from "../lib/portfolioOverview";
import { SIZE_WORD, pct, plural, sectorOrder, short2 } from "./derive";
import { TABLE_FOOT } from "./words";
import type { Meta, Mode, PageObject } from "./types";

const SHORT_LABEL: Record<string, string> = { fundamental: "G&P", valuation: "Val.", quality: "Qual.", risk: "Risk", growth: "Growth", profitability: "Profit.", balance: "Balance", technical: "Tech." };
/** The part columns of the plan's model: the four Prism parts (Gold) or the five FinLit IQ pillars (Silver). */
export const partDefs = (model: Model): { id: string; label: string; short: string; get: (h: Ready) => number | null }[] =>
  model === "prism" ? PRISM_FOUR.map((p) => ({ id: p.key, label: p.label, short: SHORT_LABEL[p.key], get: (h: Ready) => h.prism?.parts?.[p.key] ?? null }))
    : FINLIT_PILLARS.map(([k, label]) => ({ id: k, label, short: SHORT_LABEL[k], get: (h: Ready) => h.finlit?.pillars[k] ?? null }));

const Chip = ({ v, big, why }: { v: number | null | undefined; big?: boolean; why?: string }) => {
  if (v == null) return <span className="pfx-sc na" title={why || "Not scored"}>{MINUS}<span className="sr-only"> {why || "not scored"}</span></span>;
  const b = scoreBand(v);
  return <span className={"pfx-sc" + (big ? " big" : "")} style={{ background: `color-mix(in srgb, ${bandVar(b)} 18%, var(--s1))`, color: bandInk(b) }}>{Math.round(v)}</span>;
};
const Dash = ({ why }: { why: string }) => <span className="pfx-dash" title={why}>{MINUS}<span className="sr-only"> not available: {why}</span></span>;
const mean = (xs: (number | null | undefined)[]) => { const v = xs.filter((x): x is number => x != null); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };

type Props = {
  lines: Line[]; meta: Record<string, Meta>; page: PageObject | null; mode: Mode; colors: Record<string, string>; model: Model; tab: Tab; period: Period; limit: number;
  state: "loading" | "ready" | "error"; errorText?: string; onTab: (t: Tab) => void; onPeriod: (p: Period) => void; onExport: () => void; actions: (symbol: string) => ReactNode;
};

export function SharesTable(p: Props) {
  const { lines, meta, page, mode, colors, model, tab, period } = p;
  const long = (page?.layout ?? (lines.length > 15 ? "long" : "short")) === "long";
  const parts = useMemo(() => partDefs(model), [model]);
  // the Overview shows what the design lists (price, today, score and its parts); market value and the two Prism trend readings stay in the CSV and in the other views
  const cols = useMemo(() => columnsFor(tab, model, period).filter((c) => c.id !== "share" && !(tab === "overview" && (c.id === "cap" || c.id.startsWith("t_")))), [tab, model, period]);
  const rest = page?.avg_with_rest ?? {};
  const letter = useMemo(() => new Map((page?.groups ?? []).flatMap((g) => g.members.map((m) => [m, g.letter] as const))), [page]);
  const [sortId, setSortId] = useState<string | null>(null), [dir, setDir] = useState<1 | -1>(-1);
  const [q, setQ] = useState(""), [band, setBand] = useState<ScoreBand | null>(null);
  const [openSet, setOpenSet] = useState<Set<string>>(new Set());       // long lists: sectors opened by hand (all shut at first)
  const secOf = (s: string) => meta[s]?.sector || `${s} (not classified)`;

  const sortCol: Col | undefined = sortId === "rest" ? { id: "rest", label: "", sort: (h) => rest[h.symbol] ?? null, csv: () => null } : cols.find((c) => c.id === sortId);
  const bandOf = (l: Line) => scoreOf(l.ov, model).band;
  const counts = { hi: 0, mid: 0, lo: 0, na: 0 } as Record<ScoreBand, number>;
  lines.forEach((l) => { counts[bandOf(l)]++; });
  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    const f = lines.filter((l) => (band == null || bandOf(l) === band) && (!needle || [l.symbol, l.name || "", secOf(l.symbol)].join(" ").toLowerCase().includes(needle)));
    return sortCol ? sortLines(f, sortCol, dir) : f;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lines, q, band, sortCol, dir, model, meta]);

  const head = (c: { id: string; label: string; hint?: string; sortable?: boolean; num?: boolean }) => (
    <th key={c.id} scope="col" className={c.num ? "r" : ""} aria-sort={sortId === c.id ? (dir === 1 ? "ascending" : "descending") : "none"} title={c.hint}>
      {c.sortable === false ? c.label : <button type="button" className="pfx-sort" onClick={() => { if (sortId === c.id) setDir((d) => (d === 1 ? -1 : 1)); else { setSortId(c.id); setDir(1); } }}>{c.label}<i aria-hidden="true">{sortId === c.id ? (dir === 1 ? "▲" : "▼") : ""}</i></button>}
    </th>);

  const cell = (h: Ready, c: Col): ReactNode => {
    if (c.id === "price") return <td key={c.id} className="r">{h.price == null ? <Dash why="No price in the stored report." /> : priceText(h.price)}</td>;
    if (c.id === "change") return <td key={c.id} className="r">{h.changePct == null ? <Dash why="No change in the stored report." /> : <span className={h.changePct > 0 ? "pfx-up" : h.changePct < 0 ? "pfx-down" : ""}>{changeText(h.changePct)}</span>}</td>;
    if (c.id === "cap") return <td key={c.id} className="r">{h.marketCapCr == null ? <Dash why="No market cap in the stored report." /> : `₹${money(h.marketCapCr)} Cr`}</td>;
    if (c.id === "score") return <td key={c.id} className="c"><Chip v={scoreOf(h, model).value} big why={scoreWhy(h, model) || undefined} /></td>;
    if (c.id.startsWith("p_") || c.id.startsWith("f_")) { const k = c.id.slice(2), d = parts.find((x) => x.id === k); return <td key={c.id} className="c"><Chip v={d?.get(h)} why={`${c.label}: not scored for this company`} /></td>; }
    if (c.id.startsWith("t_")) { const t = h[("prism" as const)]?.[c.id.slice(2) as "shortTerm"]; return <td key={c.id} className="r">{t ? <span title={t.word}>{t.word}</span> : <Dash why="Not calculated for this rating." />}</td>; }
    if (c.id === "yearEnd") { const s = h.financials[period]; return <td key={c.id}>{s.periodEnd ? monthYear(s.periodEnd) : <Dash why={blankWhy(h, "revenue", period) || "No statement is stored yet."} />}</td>; }
    if (c.id === "basis") return <td key={c.id}>{h.basis ? BASIS_WORD[h.basis] : <Dash why="The report does not say which statement it used." />}</td>;
    if (c.id in h.ratios) { const f = h.ratios[c.id as keyof Ready["ratios"]]; return <td key={c.id} className="r">{f.value == null ? <Dash why={f.why || "Not available."} /> : <span title={f.period || undefined}>{dash(f.value, 2)}</span>}</td>; }
    const s = h.financials[period][c.id as "revenue"];
    return <td key={c.id} className="r">{s?.value == null ? <Dash why={blankWhy(h, c.id, period) || "Not available."} /> : c.id === "tax_ratio" ? dash(s.value, 1) : money(s.value, c.id === "eps" ? 2 : 0)}</td>;
  };

  const row = (l: Line, indent = false): ReactNode => {
    const h = l.ov, m = meta[l.symbol];
    const name = l.name || (isReady(h) ? h.name : "") || m?.name || "";
    return (
      <tr key={l.symbol} className={indent ? "ind" : ""}>
        <td className="pfx-name"><Link to={`/stocks/${l.symbol}`}><b>{l.symbol}</b></Link>{long && letter.has(l.symbol) && <span className="pfx-letter sm" title={`Group ${letter.get(l.symbol)}`}>{letter.get(l.symbol)}</span>}<small>{name}</small></td>
        {tab === "overview" && !long && <td><span className="pfx-sec"><i className="pfx-dot" style={{ background: colors[secOf(l.symbol)] }} aria-hidden="true" />{secOf(l.symbol).replace(/ \(not classified\)$/, "")}</span></td>}
        {tab === "overview" && <td>{m ? SIZE_WORD[m.size] : MINUS}</td>}
        {isReady(h) ? cols.map((c) => cell(h, c)) : <td colSpan={cols.length} className="pfx-wait">{h ? (h.status === "preparing" ? "Preparing… " : "") + h.reason : p.state === "error" ? "Not loaded." : "Preparing…"}</td>}
        {tab === "overview" && <td className="r">{rest[l.symbol] != null ? short2(rest[l.symbol]) : <Dash why={page?.short_history.includes(l.symbol) ? "Under a year of weekly prices, so it is left out of the co-movement figures." : "Not available until the figures are ready."} />}</td>}
        <td className="r pfx-act">{p.actions(l.symbol)}</td>
      </tr>);
  };

  // long lists: grouped by sector, sector rows carry the aggregates
  const bySector = useMemo(() => {
    if (!long) return [];
    const order = page ? sectorOrder(page, mode) : [...new Set(shown.map((l) => secOf(l.symbol)))];
    return order.map((sec) => ({ sec, members: shown.filter((l) => secOf(l.symbol) === sec) })).filter((g) => g.members.length);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [long, page, mode, shown, meta]);
  const filtering = q.trim() !== "" || band != null;                     // a search or colour filter shows the matching shares at once
  const isOpen = (sec: string) => filtering || openSet.has(sec);
  const toggle = (sec: string) => setOpenSet((c) => { const n = new Set(c); if (n.has(sec)) n.delete(sec); else n.add(sec); return n; });
  const nCols = (tab === "overview" ? (long ? 2 : 3) : 1) + cols.length + (tab === "overview" ? 1 : 0) + 1;

  const avgOf = (ls: Line[], c: Col) => (c.id === "score" ? mean(ls.map((l) => scoreOf(l.ov, model).value)) : c.id.startsWith("p_") || c.id.startsWith("f_") ? mean(ls.map((l) => (isReady(l.ov) ? parts.find((d) => d.id === c.id.slice(2))?.get(l.ov) : null))) : undefined);
  const restAvg = (ls: Line[]) => mean(ls.map((l) => rest[l.symbol]));
  const foot = (ls: Line[], label: string, extra?: ReactNode) => (
    <tr className="pfx-avg"><th scope="row" colSpan={tab === "overview" ? (long ? 2 : 3) : 1}>{label}{extra}</th>
      {cols.map((c) => { const v = avgOf(ls, c); return <td key={c.id} className={c.id === "score" || c.id.startsWith("p_") || c.id.startsWith("f_") ? "c" : ""}>{v == null ? "" : <Chip v={v} big={c.id === "score"} />}</td>; })}
      {tab === "overview" && <td className="r">{restAvg(ls) == null ? "" : short2(restAvg(ls)!)}</td>}<td /></tr>);
  const th = (<tr>{head({ id: "share", label: "Share", sortable: false })}
    {tab === "overview" && !long && head({ id: "sector", label: "Sector", sortable: false })}
    {tab === "overview" && head({ id: "size", label: "Size", sortable: false })}
    {cols.map((c) => head({ id: c.id, label: tab === "overview" && (c.id.startsWith("p_") || c.id.startsWith("f_")) ? (parts.find((d) => d.id === c.id.slice(2))?.short ?? c.label) : c.id === "score" ? (model === "prism" ? "Prism" : "FinLit IQ") : c.label.replace(/ \(.*\)$/, ""), hint: c.hint ? `${c.label}. ${c.hint}` : c.label, num: c.num }))}
    {tab === "overview" && head({ id: "rest", label: "Moves with rest", hint: "A share's average correlation with the other shares in the list", num: true })}<th scope="col"><span className="sr-only">Actions</span></th></tr>);

  return (
    <section className="pfx-card pfx-wide" id="pf-shares" aria-labelledby="pfx-sh">
      <div className="pfx-h pfx-h-shares"><h2 id="pfx-sh">Your shares</h2>
        <div className="pfx-tabs" role="tablist" aria-label="Portfolio views">{TABS.map((t, i) => (
          <button key={t.id} type="button" role="tab" id={`pf-tab-${t.id}`} aria-selected={tab === t.id} aria-controls="pf-panel" tabIndex={tab === t.id ? 0 : -1} className={"pfx-pillbtn" + (tab === t.id ? " on" : "")} onClick={() => p.onTab(t.id)}
            onKeyDown={(e) => { const to = nextTab(TABS[i].id, e.key); if (to) { e.preventDefault(); p.onTab(to); document.getElementById(`pf-tab-${to}`)?.focus(); } }}>{t.label}</button>))}
          <button type="button" className="pfx-btn" onClick={p.onExport} disabled={!lines.length}>Export CSV</button></div></div>
      <div className="pfx-tools">
        <input className="pfx-search" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a share in your list" aria-label="Find a share in your list" />
        <div className="pfx-chipsrow" role="group" aria-label="Filter by score colour">
          <button type="button" className={"pfx-pillbtn" + (band == null ? " on" : "")} aria-pressed={band == null} onClick={() => setBand(null)}>All {lines.length}</button>
          {([["hi", "Green"], ["mid", "Orange"], ["lo", "Red"], ["na", "Not scored"]] as const).filter(([b]) => counts[b]).map(([b, l]) => <button key={b} type="button" className={"pfx-pillbtn bf-" + b + (band === b ? " on" : "")} aria-pressed={band === b} onClick={() => setBand(band === b ? null : b)}>{l} {counts[b]}</button>)}</div>
        {tab === "financials" && <div className="pfx-chipsrow" role="group" aria-label="Period shown">{([["year", "Latest year"], ["quarter", "Latest quarter"]] as const).map(([k, l]) => <button key={k} type="button" className={"pfx-pillbtn" + (period === k ? " on" : "")} aria-pressed={period === k} onClick={() => p.onPeriod(k)}>{l}</button>)}</div>}
        {long && <div className="pfx-chipsrow"><button type="button" className="pfx-link" onClick={() => setOpenSet(new Set(bySector.map((g) => g.sec)))}>Open all</button><button type="button" className="pfx-link" onClick={() => setOpenSet(new Set())}>Close all</button></div>}
        <span className="pfx-note pfx-count">{plural(shown.length, "share")}{shown.length !== lines.length ? ` of ${lines.length}` : ""} · limit {p.limit}</span>
      </div>
      {p.state === "error" && <p className="pfx-warn" role="alert">{p.errorText || "The scores could not be loaded. Try again in a moment."}</p>}
      <div id="pf-panel" role="tabpanel" aria-labelledby={`pf-tab-${tab}`}>
        <HScroll label="table"><table className={"pfx-table t-" + tab + (long ? " long" : "")}>
          <caption className="sr-only">{TABS.find((t) => t.id === tab)?.label} of your shares</caption>
          <thead>{th}</thead>
          <tbody>
            {!long && shown.map((l) => row(l))}
            {long && bySector.map(({ sec, members }) => { const open = isOpen(sec); return (
              <FragmentRows key={sec}>
                <tr className="pfx-secrow"><td colSpan={nCols}><button type="button" aria-expanded={open} onClick={() => toggle(sec)}>
                  <span className="car" aria-hidden="true">{open ? "▾" : "▸"}</span><i className="pfx-dot" style={{ background: colors[sec] }} aria-hidden="true" /><b>{sec.replace(/ \(not classified\)$/, "")}</b> <span className="n">{plural(members.length, "share")}</span>
                  {page && <span className="m">{pct(page.sector_weight[mode][sec] ?? 0)} of the list · {pct(page.sector_risk[mode][sec] ?? 0)} of the risk</span>}
                  {tab === "overview" && <span className="a"><Chip v={mean(members.map((l) => scoreOf(l.ov, model).value))} big /></span>}</button></td></tr>
                {open && members.map((l) => row(l, true))}
              </FragmentRows>); })}
            {!shown.length && <tr><td colSpan={nCols} className="pfx-empty">{lines.length ? "No share matches this filter." : "No shares yet."}</td></tr>}
          </tbody>
          {tab === "overview" && shown.length > 0 && <tfoot>{foot(shown, "List average")}</tfoot>}
        </table></HScroll>
      </div>
      <p className="pfx-fine">{tab === "overview" ? TABLE_FOOT : tab === "ratios" ? "These are the figures on each company's own page (the data provider's, with the period on hover). A dash says why on hover. Information only, not investment advice." : `The latest ${period === "year" ? "full year" : "quarter"} in each company's stored statements, in ₹ crore except EPS. Information only, not investment advice.`}</p>
      {p.state === "loading" && <p className="pfx-fine" role="status">Loading the scores…</p>}
    </section>
  );
}
const FragmentRows = ({ children }: { children: ReactNode }) => <>{children}</>;
