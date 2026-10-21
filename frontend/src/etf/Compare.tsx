// /etfs/compare?symbols=A,B: two to four ETFs side by side, with their prices rebased to 100 on one chart. No ranking, no "winner": the figures speak.
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import {
  COL_BY, MAX_COMPARE, RANGES, RANGE_LABEL, day, move, parseSymbols, pct, rupee, traded, useEtfCompare, useEtfSearch, useTray, type EtfItem, type RangeKey,
} from "../lib/etf";
import { nf } from "../lib/format";
import { Blank, DataNote, ErrorState, GlossInfo, Skeleton, Tone } from "./common";
import { EtfChart } from "./EtfChart";

const COLORS = ["var(--k1)", "var(--k2)", "var(--k3)", "var(--k7)"];
const DASHES = [undefined, "7 4", "2 3", "10 3 2 3"];

type Row = { label: string; get: (i: EtfItem) => string | number | null; text: (i: EtfItem) => string; why?: (i: EtfItem) => string; tone?: boolean; sub?: (i: EtfItem) => string | null; term?: () => React.ReactNode };
const colRow = (key: string, label?: string): Row => {
  const c = COL_BY[key];
  return { label: label ?? c.label, get: (i) => c.get(i), text: (i) => c.text(i), why: (i) => i.why?.[c.why ?? ""] ?? "Not enough price history", tone: c.num && key !== "price" && key !== "turnover" };
};
/** Exactly three return rows: 1 day, 1 year, 5 years. The 5-year row is the total change; the yearly rate is a small line under it. */
const GROUPS: { title: string; rows: Row[] }[] = [
  { title: "About", rows: [
    { label: "Category", get: (i) => i.categoryLabel, text: (i) => i.categoryLabel ?? "—", why: () => "The fund's name does not say clearly what it follows" },
    { label: "Fund house", get: (i) => i.fundHouse, text: (i) => i.fundHouse ?? "—", why: () => "Not found in AMFI's register" },
    { label: "ISIN", get: (i) => i.isin, text: (i) => i.isin },
    { label: "Price history in our data from", get: (i) => i.firstDate, text: (i) => day(i.firstDate) }] },
  { title: "Price", rows: [colRow("price", "Last close"),
    { label: "Previous close", get: (i) => i.previousClose, text: (i) => rupee(i.previousClose) }, { label: "Close date", get: (i) => i.priceDate, text: (i) => day(i.priceDate) }] },
  { title: "Price return (dividends not included)", rows: [
    { label: "1 day", get: (i) => i.changePct, text: (i) => move(i.changePct), why: (i) => i.why?.change ?? "No previous close to compare with", tone: true },
    colRow("ret1y", "1 year"),
    { label: "5 years (total)", get: (i) => i.ret5y, text: (i) => pct(i.ret5y), why: (i) => i.why?.ret_5y ?? "Not enough price history", tone: true,
      sub: (i) => (i.ret5y != null && i.cagr5y != null ? `about ${pct(i.cagr5y)} a year` : null) }] },
  { title: "NAV and trading", rows: [
    { label: "NAV (AMFI)", get: (i) => i.nav, text: (i) => rupee(i.nav, 4), why: () => "No NAV found in AMFI's file" },
    { label: "NAV date", get: (i) => i.navDate, text: (i) => day(i.navDate), why: () => "No NAV found in AMFI's file" },
    { label: "Premium / discount to NAV", get: (i) => i.premium, text: (i) => pct(i.premium), why: (i) => i.why?.nav_premium ?? "No NAV found in AMFI's file", tone: true },
    { label: "Traded value a day (20-session average)", get: (i) => i.avgTurnover, text: (i) => traded(i.avgTurnover), why: () => "Too few trading days to average" }] },
];

export function EtfComparePage() {
  useDocTitle("Compare ETFs", "Put two to four ETFs side by side: 1-day, 1-year and 5-year price return, NAV and a chart of how each moved. Information only.");
  const [sp, setSp] = useSearchParams();
  const tray = useTray();
  const urlSyms = useMemo(() => parseSymbols(sp.get("symbols")), [sp]);
  const rangeParam = (sp.get("range") || "").toUpperCase();
  const range: RangeKey = (RANGES as readonly string[]).includes(rangeParam) ? (rangeParam as RangeKey) : "1Y";
  const setSyms = (s: string[]) => setSp((p) => { const n = new URLSearchParams(p); if (s.length) n.set("symbols", s.join(",")); else n.delete("symbols"); return n; }, { replace: true });
  // opened without a link: start from the ETFs chosen on the list page
  useEffect(() => { if (!sp.has("symbols") && tray.tray.length) setSyms(tray.tray); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);
  useEffect(() => { if (sp.has("symbols") && urlSyms.join() !== tray.tray.join()) tray.set(urlSyms); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [urlSyms.join()]);
  const { data, isLoading, isError, error, refetch } = useEtfCompare(urlSyms, range);

  const items = data?.items ?? [];
  const lines = items.map((it, k) => ({ key: it.symbol, label: it.symbol, points: data?.series[it.symbol] ?? [], color: COLORS[k], dash: DASHES[k] })).filter((l) => l.points.length > 1);
  const blanks = items.flatMap((it) => GROUPS.flatMap((g) => g.rows.filter((r) => r.get(it) == null && r.why).map((r) => ({ sym: it.symbol, label: r.label, why: r.why!(it) }))));
  const notFound = isError && (error as { status?: number })?.status === 404;

  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap">        <div className="eyebrow">Compare ETFs</div><h1>ETFs, side by side.</h1>
        <p>Choose two to four ETFs. The chart rebases each price to 100 on the same day, so you can see how they moved relative to each other. Information only.</p></div></section>
      <div className="wrap etf-page">
        <div className="card etf-sec">
          <div className="card-h"><h3><span className="ci"><Icon name="layers" /></span>Choose ETFs</h3><Link className="etf-link" to="/etfs">Browse the full list →</Link></div>
          <Picker chosen={urlSyms} onChange={setSyms} />
        </div>

        {urlSyms.length < 2 ? (
          <div className="etf-state"><h2>Pick at least two ETFs</h2><p>Search above, or open the <Link to="/etfs">ETF list</Link> and press “+ Compare” on the ones you want.</p></div>
        ) : notFound ? (
          <div className="etf-state"><h2>One of these symbols is not an ETF we have</h2><p>{(error as { message?: string }).message}</p></div>
        ) : isError && !data ? <ErrorState what="The comparison" onRetry={() => refetch()} /> : isLoading || !data ? <Skeleton rows={6} /> : (
          <>
            <section className="card etf-sec" aria-labelledby="h-cc">
              <div className="card-h"><h3 id="h-cc"><span className="ci"><Icon name="line" /></span>Price, rebased to 100</h3>
                <div className="etf-ranges-btns" role="group" aria-label="Chart range">{RANGES.map((r) => (
                  <button key={r} className={"chip-b" + (r === range ? " on" : "")} aria-pressed={r === range} onClick={() => setSp((p) => { const n = new URLSearchParams(p); n.set("range", r); return n; }, { replace: true })}>{RANGE_LABEL[r]}</button>))}</div></div>
              {lines.length >= 2 ? (
                <>
                  <EtfChart mode="index" series={lines} caption={`Prices of ${lines.map((l) => l.label).join(", ")} rebased to 100 on ${day(data.start)}`}
                    summary={`Prices rebased to 100 on ${day(data.start)}. ` + lines.map((l) => `${l.label} ends at ${nf(l.points[l.points.length - 1][1], 1)}.`).join(" ")} />
                  <ul className="etf-legend">{lines.map((l) => { const end = l.points[l.points.length - 1][1]; return (
                    <li key={l.key}><svg width="34" height="10" aria-hidden="true"><line x1="1" x2="33" y1="5" y2="5" stroke={l.color} strokeWidth="3" strokeDasharray={l.dash} /></svg><b>{l.label}</b><span className="faint">ends at {nf(end, 1)}</span><Tone v={end - 100}>{move(end - 100, 1)}</Tone></li>); })}</ul>
                  <p className="faint etf-cap">Each line starts at 100 on {day(data.start)} and shows the closing price after that, so 112 means the price is 12% higher than on the start day. Price only: dividends are not included.</p>
                </>) : <div className="etf-state small"><p>These ETFs do not share enough price history for a chart over {RANGE_LABEL[range]}.</p></div>}
              {data.notes.map((n) => <p key={n} className="etf-info"><Icon name="info" />{n}</p>)}
            </section>

            <section className="card etf-sec" aria-labelledby="h-ct">
              <div className="card-h"><h3 id="h-ct"><span className="ci"><Icon name="table" /></span>The figures</h3><span className="s">as of {day(data.asOf)}</span></div>
              <div className="tw etf-tw" tabIndex={0} role="region" aria-label="Comparison table. Scroll sideways for more ETFs.">
                <table className="etf-table etf-cmp">
                  <caption className="sr-only">Figures for {items.map((i) => i.symbol).join(", ")}</caption>
                  <thead><tr><th scope="col" className="etf-first">Figure</th>{items.map((i, k) => (
                    <th key={i.symbol} scope="col" className="num"><svg width="22" height="8" aria-hidden="true"><line x1="1" x2="21" y1="4" y2="4" stroke={COLORS[k]} strokeWidth="3" strokeDasharray={DASHES[k]} /></svg>
                      <Link to={`/etfs/${encodeURIComponent(i.symbol)}`}>{i.symbol}</Link><small>{i.name}</small>
                      <button className="etf-x" aria-label={`Remove ${i.symbol} from the comparison`} onClick={() => setSyms(urlSyms.filter((s) => s !== i.symbol))}>×</button></th>))}</tr></thead>
                  {GROUPS.map((g) => (
                    <tbody key={g.title}>
                      <tr className="etf-grp"><th colSpan={items.length + 1} scope="colgroup">{g.title}</th></tr>
                      {g.rows.map((r) => (
                        <tr key={r.label}><th scope="row" className="etf-first">{r.label}{r.label.startsWith("5 years") && <GlossInfo name="Price return" fallback={COL_BY.ret5y.help} />}{r.label.startsWith("Premium") && <GlossInfo name="Premium and discount to NAV" fallback="Exchange close against the NAV of the same day." />}</th>
                          {items.map((i) => { const v = r.get(i); return (
                            <td key={i.symbol} className="num">{v == null ? <Blank why={r.why ? r.why(i) : "Not available"} /> : r.tone ? <Tone v={Number(v)}>{r.text(i)}</Tone> : r.text(i)}{v != null && r.sub?.(i) && <small className="etf-cell-sub">{r.sub(i)}</small>}</td>); })}</tr>))}
                    </tbody>))}
                </table>
              </div>
              {blanks.length > 0 && (
                <details className="etf-blanks"><summary>Why some figures are blank ({blanks.length})</summary>
                  <ul>{blanks.map((b) => <li key={b.sym + b.label}><b>{b.sym}</b>, {b.label}: {b.why}</li>)}</ul></details>)}
            </section>
          </>)}
        <DataNote asOf={data?.asOf} updatedAt={data?.updatedAt} source={data?.source} />
      </div>
    </>
  );
}

/** Type to find an ETF (same forgiving search as the list), press Enter or a result to add it. Up to four. */
function Picker({ chosen, onChange }: { chosen: string[]; onChange: (s: string[]) => void }) {
  const [q, setQ] = useState("");
  const [dq, setDq] = useState("");
  useEffect(() => { const h = window.setTimeout(() => setDq(q.trim()), 200); return () => window.clearTimeout(h); }, [q]);
  const { data, isFetching } = useEtfSearch(dq);
  const hits = (data?.items ?? []).filter((i) => !chosen.includes(i.symbol));
  const add = (s: string) => { if (chosen.length >= MAX_COMPARE) return; onChange([...chosen, s]); setQ(""); setDq(""); };
  return (
    <div className="etf-picker">
      <ul className="etf-chips" aria-label="Chosen ETFs">{chosen.map((s) => <li key={s}><span className="mono">{s}</span><button aria-label={`Remove ${s}`} onClick={() => onChange(chosen.filter((x) => x !== s))}>×</button></li>)}
        {chosen.length === 0 && <li className="faint">None chosen yet</li>}</ul>
      {chosen.length >= MAX_COMPARE ? <p className="faint">You are comparing the most this page can show ({MAX_COMPARE}). Remove one to add another.</p> : (
        <>
          <label className="etf-search"><Icon name="search" /><span className="sr-only">Search for an ETF to add</span>
            <input type="search" value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && hits[0]) { e.preventDefault(); add(hits[0].symbol); } }}
              placeholder="Add an ETF: name, symbol or fund house" autoComplete="off" spellCheck={false} maxLength={60} /></label>
          {dq && (
            <ul className="etf-hits" aria-label="Search results" aria-busy={isFetching}>
              {hits.map((i) => <li key={i.symbol}><button onClick={() => add(i.symbol)}><b>{i.name}</b><span className="mono faint">{i.symbol}{i.categoryLabel ? ` · ${i.categoryLabel}` : ""}</span><span className="etf-addl">+ Add</span></button></li>)}
              {!isFetching && hits.length === 0 && <li className="faint etf-nohit">No other ETF matches “{dq}”.</li>}
            </ul>)}
        </>)}
    </div>
  );
}
