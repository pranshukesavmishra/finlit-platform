import { HScroll } from "../components/HScroll";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { Icon } from "../lib/icons";
import { dateIN, nf, num, MINUS } from "../lib/format";
import { downloadCsv, prefetchMarkets, qs, useGold, usePremium, type Feed, type MarketSection } from "../lib/premium";
import { LineChart } from "../charts/LineChart";
import { useDocTitle } from "../lib/title";
import { GoldLock, PremiumHead } from "./Premium";
import { useIndexHistory, useIndices, type IndexRow, type Stat } from "../lib/indices";
import { ChartHelp } from "../components/ChartHelp";

type Row = Record<string, string | number | null | undefined>;
type Col = { key: string; label: string; num?: boolean; wide?: boolean; fmt?: (v: string | number | null | undefined, r: Row) => React.ReactNode };

const txt = (v: unknown) => (v == null || v === "" ? MINUS : String(v));
const dt = (v: unknown) => (v ? dateIN(String(v).slice(0, 10)) : MINUS);
const n2 = (v: unknown) => (typeof v === "number" ? num(v) : MINUS);
const pc = (v: unknown) => (typeof v === "number" ? <span style={{ color: v >= 0 ? "var(--gain)" : "var(--loss)" }}>{(v > 0 ? "▲ +" : v < 0 ? "▼ " + MINUS : "") + nf(v)}%</span> : MINUS);
const status = (v: unknown) => { const t = String(v || ""); const k = /open|live|current/i.test(t) ? "up" : /upcoming|forthcoming/i.test(t) ? "gold" : /list/i.test(t) ? "info" : "ghost"; return t ? <span className={"chip " + k}>{t}</span> : MINUS; };
const doc = (v: unknown) => (v ? <a href={String(v)} target="_blank" rel="noopener noreferrer">Open document</a> : MINUS);

const TABS: { id: MarketSection | "commodities"; label: string }[] = [
  { id: "ipo", label: "IPO calendar" }, { id: "results", label: "Results calendar" }, { id: "announcements", label: "Announcements" },
  { id: "transcripts", label: "Call transcripts" }, { id: "indices", label: "Indices live" }, { id: "valuations", label: "Index valuation history" }, { id: "commodities", label: "Commodities" },
];

const COLS: Record<string, Col[]> = {
  ipo: [{ key: "company_name", label: "Company" }, { key: "security_type", label: "Type" }, { key: "ipo_status", label: "Status", fmt: status }, { key: "start_date", label: "Opens", fmt: dt }, { key: "end_date", label: "Closes", fmt: dt },
    { key: "price_range", label: "Price band", num: true }, { key: "issue_size", label: "Issue size", num: true }, { key: "subscription", label: "Subscription", num: true }, { key: "exchange", label: "Exchange" }],
  results: [{ key: "symbol", label: "Symbol" }, { key: "company_name", label: "Company" }, { key: "expected_result_date", label: "Expected result date", fmt: dt }],
  announcements: [{ key: "date", label: "Date", fmt: dt }, { key: "symbol", label: "Symbol" }, { key: "category", label: "Category" }, { key: "description", label: "Announcement", wide: true }, { key: "document_url", label: "Document", fmt: doc }],
  transcripts: [{ key: "date", label: "Date", fmt: dt }, { key: "symbol", label: "Symbol" }, { key: "category", label: "Category" }, { key: "description", label: "Call", wide: true }, { key: "document_url", label: "Transcript", fmt: doc }],
  indices: [{ key: "index_name", label: "Index" }, { key: "close_price", label: "Close", num: true, fmt: n2 }, { key: "change_pct", label: "Change", num: true, fmt: pc }, { key: "points_change", label: "Points", num: true, fmt: n2 },
    { key: "high_price", label: "High", num: true, fmt: n2 }, { key: "low_price", label: "Low", num: true, fmt: n2 }, { key: "pe", label: "P/E", num: true, fmt: n2 }, { key: "pb", label: "P/B", num: true, fmt: n2 }, { key: "div_yield", label: "Div. yield %", num: true, fmt: n2 }, { key: "quote_date", label: "As of", fmt: dt }],
  valuations: [{ key: "quote_date", label: "Date", fmt: dt }, { key: "close_price", label: "Close", num: true, fmt: n2 }, { key: "pe", label: "P/E", num: true, fmt: n2 }, { key: "pb", label: "P/B", num: true, fmt: n2 }, { key: "div_yield", label: "Div. yield %", num: true, fmt: n2 }],
};

const PAGE = 15;

function Loading() { return <div className="skeleton" style={{ height: 360 }} aria-busy="true" aria-label="Loading" />; }
function Problem({ e, retry }: { e: unknown; retry: () => void }) {
  const status = (e as { status?: number })?.status;
  return <div className="state"><h2>{status === 403 ? "This tool is part of Gold" : "This data is not available right now"}</h2><p>{status === 403 ? "Sign in with a Gold account to use it." : "The data provider did not answer. Nothing is wrong with your account."}</p>
    {status !== 403 && <button className="btn" onClick={retry}>Try again</button>}</div>;
}

function Table({ cols, rows, q, file }: { cols: Col[]; rows: Row[]; q: string; file?: string }) {
  const [page, setPage] = useState(0);
  const shown = useMemo(() => { const s = q.trim().toLowerCase(); return s ? rows.filter((r) => Object.values(r).some((v) => String(v ?? "").toLowerCase().includes(s))) : rows; }, [rows, q]);
  useEffect(() => setPage(0), [q, rows]);
  const pages = Math.max(1, Math.ceil(shown.length / PAGE));
  if (!shown.length) return <div className="pm-empty">Nothing matches. Try a wider date range or clear the search.</div>;
  return (
    <>
      {file && <div className="pm-tools"><button className="alx-link" onClick={() => downloadCsv(file, cols.map((c) => c.label), shown.map((r) => cols.map((c) => r[c.key] as string | number | null)))}><Icon name="table" /> Export CSV</button></div>}
      <HScroll className="" label="table"><table className="pm-t"><thead><tr>{cols.map((c) => <th key={c.key} className={c.num ? "n" : ""}>{c.label}</th>)}</tr></thead>
        <tbody>{shown.slice(page * PAGE, page * PAGE + PAGE).map((r, i) => <tr key={i}>{cols.map((c) => <td key={c.key} className={(c.num ? "n " : "") + (c.wide ? "wrapc" : "")}>{c.fmt ? c.fmt(r[c.key], r) : txt(r[c.key])}</td>)}</tr>)}</tbody></table></HScroll>
      <div className="pm-pager"><span>{shown.length} rows</span><button className="btn" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button><span>Page {page + 1} of {pages}</span><button className="btn" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>Next</button></div>
    </>
  );
}

/** Every index as a tile tinted by today's move: green up, red down, stronger colour for bigger moves. */
function Heat({ rows }: { rows: Row[] }) {
  const max = Math.max(...rows.map((r) => Math.abs(Number(r.change_pct) || 0)), 0.5);
  if (!rows.length) return null;
  return (
    <div className="pm-heat" aria-label="Index moves today">{rows.map((r) => {
      const c = typeof r.change_pct === "number" ? r.change_pct : null;
      return <div key={String(r.index_symbol || r.index_name)} className="pm-tile" style={{ "--tc": c == null ? "var(--faint)" : c >= 0 ? "var(--gain)" : "var(--loss)", "--ti": c == null ? 0 : 6 + (Math.abs(c) / max) * 22 } as React.CSSProperties}>
        <small title={String(r.index_name || "")}>{String(r.index_name || r.index_symbol)}</small><b>{typeof r.close_price === "number" ? nf(r.close_price) : MINUS}</b><span>{c == null ? MINUS : (c > 0 ? "▲ +" : c < 0 ? "▼ " + MINUS : "") + nf(Math.abs(c)) + "%"}</span></div>;
    })}</div>
  );
}

/** P/E through time against its own average, and a plain verdict on where it sits today. */
function Valuation({ rows, name }: { rows: Row[]; name: string }) {
  const asc = [...rows].reverse().filter((r) => typeof r.pe === "number");
  if (asc.length < 2) return null;
  const pe = asc.map((r) => r.pe as number), avg = pe.reduce((a, b) => a + b, 0) / pe.length, now = pe[pe.length - 1], gap = ((now - avg) / avg) * 100;
  const word = gap > 10 ? "Expensive against its own history" : gap < -10 ? "Cheap against its own history" : "Close to its usual valuation";
  return (
    <>
      <div className="pm-verdict"><span className={"chip " + (gap > 10 ? "down" : gap < -10 ? "up" : "gold")}>{word}</span>
        <span><b>P/E {nf(now, 1)}</b> <span className="faint">against an average of {nf(avg, 1)} over this period ({gap >= 0 ? "+" : MINUS}{nf(Math.abs(gap), 0)}%)</span></span></div>
      <div className="pm-chart card"><div className="pm-chart-h"><div><small>Valuation</small><b>{name} P/E <ChartHelp id="idx-pe-history" /></b></div><span className="faint">Dashed line is the average</span></div>
        <LineChart periods={asc.map((r) => (r.quote_date ? dateIN(String(r.quote_date).slice(0, 10), { day: "numeric", month: "short" }) : ""))} series={[{ key: "pe", label: "P/E", color: "var(--gold)", values: pe }]} fmt={(x) => nf(x, 1)} height={240} area avg={avg} /></div>
    </>
  );
}

function Feed({ section }: { section: MarketSection }) {
  const short = section === "announcements" || section === "transcripts";
  const [from, setFrom] = useState(""), [to, setTo] = useState(""), [symbol, setSymbol] = useState(""), [index, setIndex] = useState(""), [q, setQ] = useState("");
  const [applied, setApplied] = useState({ from: "", to: "", symbol: "" });
  const indices = usePremium<Feed<Row>>("/markets/indices", section === "valuations");
  const list = (indices.data?.items || []).map((r) => String(r.index_symbol || r.index_name || "")).filter(Boolean);
  if (section === "valuations" && !index && list.length) setIndex(list.find((x) => /nifty ?50$/i.test(x)) || list[0]);  // default to NIFTY 50
  const path = `/markets/${section}` + (section === "valuations" ? (index ? qs({ index_symbol: index, from_date: applied.from, to_date: applied.to }) : "") : qs({ from_date: applied.from, to_date: applied.to, symbol: applied.symbol }));
  const { data, isLoading, isError, error, refetch, isFetching } = usePremium<Feed<Row>>(path, section !== "valuations" || !!index);
  const apply = (e: React.FormEvent) => { e.preventDefault(); setApplied({ from, to, symbol: symbol.trim() }); };
  const maxDays = short ? 7 : 366;
  return (
    <section aria-label={TABS.find((t) => t.id === section)?.label}>
      <form className="pm-bar" onSubmit={apply}>
        {section !== "indices" && <><label>From<input type="date" value={from} onChange={(e) => setFrom(e.target.value)} max={to || undefined} /></label><label>To<input type="date" value={to} onChange={(e) => setTo(e.target.value)} min={from || undefined} /></label></>}
        {short && <label>Company symbol<input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder="e.g. RELIANCE" maxLength={30} /></label>}
        {section === "valuations" && <label>Index<select value={index} onChange={(e) => setIndex(e.target.value)}>{list.map((x) => <option key={x}>{x}</option>)}</select></label>}
        {section !== "indices" && <button className="btn primary" type="submit">Apply</button>}
        {section !== "indices" && (from || to || symbol) && <button className="btn" type="button" onClick={() => { setFrom(""); setTo(""); setSymbol(""); setApplied({ from: "", to: "", symbol: "" }); }}>Reset</button>}
        <label style={{ marginLeft: "auto" }}>Search these rows<input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Type to filter" /></label>
      </form>
      {section !== "indices" && <p className="pm-meta">{short ? "Up to 7 days at a time." : `Up to ${maxDays > 300 ? "a year" : maxDays + " days"} at a time.`} {section === "results" || section === "ipo" ? "Showing the next two weeks unless you choose dates." : ""}</p>}
      {isError ? <Problem e={error} retry={() => refetch()} /> : isLoading ? <Loading /> : (
        <>
          <p className="pm-meta"><Icon name="check" /> Updated {data?.fetchedAt ? new Date(data.fetchedAt).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "just now"} · Source: {data?.provider || "FinEdge"}{isFetching ? " · refreshing…" : ""}{section === "indices" && <> <ChartHelp id="idx-tiles" /></>}</p>
          {section === "indices" && <Heat rows={data?.items || []} />}
          {section === "valuations" && <Valuation rows={data?.items || []} name={index} />}
          <Table cols={COLS[section]} rows={data?.items || []} q={q} file={`finlit-${section}${index ? "-" + index : ""}`} />
        </>)}
    </section>
  );
}


/* ---------------------------------------------------------------- index prices and valuation history (/api/indices) */

const GROUPS = ["All", "Broad market", "Sector", "Strategy & theme", "Volatility"] as const;
const chg = (v: number | null) => (v == null ? MINUS : <span style={{ color: v >= 0 ? "var(--gain)" : "var(--loss)" }}>{(v > 0 ? "▲ +" : v < 0 ? "▼ " + MINUS : "") + nf(Math.abs(v))}%</span>);
const v2 = (v: number | null, d = 2) => (v == null ? MINUS : nf(v, d));
type IKey = "name" | "close" | "changePct" | "pe" | "pb" | "divYield";

/** Every NSE and BSE index: key indices as tiles, then a searchable, sortable table. A row opens its valuation history. */
function IndexPrices({ open }: { open: (code: string) => void }) {
  const { data, isLoading, isError, error, refetch, dataUpdatedAt } = useIndices();
  const [group, setGroup] = useState<(typeof GROUPS)[number]>("All"), [ex, setEx] = useState<"All" | "NSE" | "BSE">("All"), [q, setQ] = useState("");
  const [sort, setSort] = useState<{ k: IKey; d: 1 | -1 } | null>(null), [page, setPage] = useState(0);
  const rows = useMemo(() => {
    const t = q.trim().toLowerCase();
    const out = (data?.items || []).filter((r) => (group === "All" || r.group === group) && (ex === "All" || r.exchange === ex) && (!t || r.name.toLowerCase().includes(t) || r.code.toLowerCase().includes(t)));
    if (!sort) return out;
    return [...out].sort((a, b) => {
      const x = a[sort.k], y = b[sort.k];
      if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1;
      return (typeof x === "string" ? x.localeCompare(y as string) : (x as number) - (y as number)) * sort.d;
    });
  }, [data, group, ex, q, sort]);
  useEffect(() => setPage(0), [group, ex, q, sort]);
  if (isError) return <Problem e={error} retry={() => refetch()} />;
  if (isLoading || !data) return <Loading />;
  const key = data.key.map((c) => data.items.find((r) => r.code === c)).filter(Boolean) as IndexRow[];
  const pages = Math.max(1, Math.ceil(rows.length / PAGE));
  const th = (k: IKey, label: string, n = true) => <th className={n ? "n" : ""}><button className="pm-sort" onClick={() => setSort((s) => ({ k, d: s?.k === k ? (s.d === 1 ? -1 : 1) : k === "name" ? 1 : -1 }))}>{label} {sort?.k === k ? (sort.d > 0 ? "▲" : "▼") : ""}</button></th>;
  return (
    <section aria-label="Index prices">
      <p className="pm-meta"><span className={"pm-live" + (data.marketOpen ? " on" : "")} />{data.marketOpen ? "Market open · prices refresh every minute" : "Market closed · last prices"}{data.asOf ? ` · as of ${dateIN(data.asOf)}` : ""} · updated {new Date(dataUpdatedAt).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })} <ChartHelp id="idx-tiles" /></p>
      <div className="pm-heat" aria-label="Key indices">{key.map((r) => {
        const c = r.changePct;
        return <button key={r.code} className="pm-tile" onClick={() => r.code !== "INDVIX" && open(r.code)} title={r.code === "INDVIX" ? r.name : `Open ${r.name} valuation history`}
          style={{ "--tc": c == null ? "var(--faint)" : (r.code === "INDVIX" ? -c : c) >= 0 ? "var(--gain)" : "var(--loss)", "--ti": c == null ? 0 : 6 + Math.min(Math.abs(c), 3) * 7 } as React.CSSProperties}>
          <small>{r.name}</small><b>{v2(r.close)}</b><span>{c == null ? MINUS : (c > 0 ? "▲ +" : c < 0 ? "▼ " + MINUS : "") + nf(Math.abs(c)) + "%"}{r.points != null ? ` (${r.points > 0 ? "+" : ""}${nf(r.points)})` : ""}</span>
          {r.pe != null && <em>P/E {nf(r.pe, 1)}</em>}</button>;
      })}</div>
      <div className="pm-bar">
        <div className="pm-seg" role="group" aria-label="Kind of index">{GROUPS.map((g) => <button key={g} type="button" aria-pressed={group === g} onClick={() => setGroup(g)}>{g}</button>)}</div>
        <div className="pm-seg" role="group" aria-label="Exchange">{(["All", "NSE", "BSE"] as const).map((g) => <button key={g} type="button" aria-pressed={ex === g} onClick={() => setEx(g)}>{g}</button>)}</div>
        <label style={{ marginLeft: "auto" }}>Find an index<input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. Bank, IT, Midcap" /></label>
      </div>
      {!rows.length ? <div className="pm-empty">No index matches. Clear the search or pick another group.</div> : <>
        <div className="pm-tools"><button className="alx-link" onClick={() => downloadCsv("finlit-indices", ["Index", "Code", "Exchange", "Group", "Close", "Change %", "Points", "High", "Low", "P/E", "P/B", "Div. yield %", "Date"], rows.map((r) => [r.name, r.code, r.exchange, r.group, r.close, r.changePct, r.points, r.high, r.low, r.pe, r.pb, r.divYield, r.date]))}><Icon name="table" /> Export CSV</button></div>
        <HScroll className="" label="table"><table className="pm-t"><thead><tr>{th("name", "Index", false)}{th("close", "Close")}{th("changePct", "Change")}<th className="n">Points</th><th className="n">Day range</th>{th("pe", "P/E")}{th("pb", "P/B")}{th("divYield", "Div. yield %")}<th><span className="sr">Valuation history</span></th></tr></thead>
          <tbody>{rows.slice(page * PAGE, page * PAGE + PAGE).map((r) => (
            <tr key={r.code}><td><b>{r.name}</b><small className="faint" style={{ display: "block" }}>{r.exchange} · {r.group}</small></td><td className="n">{v2(r.close)}</td><td className="n">{chg(r.changePct)}</td><td className="n">{v2(r.points)}</td>
              <td className="n">{r.low != null && r.high != null ? `${nf(r.low)} – ${nf(r.high)}` : MINUS}</td><td className="n">{v2(r.pe, 1)}</td><td className="n">{v2(r.pb)}</td><td className="n">{v2(r.divYield)}</td>
              <td>{r.pe != null || r.pb != null ? <button className="alx-link" onClick={() => open(r.code)}>History</button> : null}</td></tr>))}</tbody></table></HScroll>
        <div className="pm-pager"><span>{rows.length} indices</span><button className="btn" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button><span>Page {page + 1} of {pages}</span><button className="btn" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>Next</button></div>
      </>}
    </section>
  );
}

const MEASURES = { pe: { label: "P/E", unit: "", d: 1, low: "cheaper", say: "Price for each rupee of the index's yearly profit." },
  pb: { label: "P/B", unit: "", d: 2, low: "cheaper", say: "Price against the book value of the index's companies." },
  dy: { label: "Dividend yield", unit: "%", d: 2, low: "dearer", say: "Yearly dividends as a share of the index level; a higher yield usually means a cheaper market." } } as const;
type Measure = keyof typeof MEASURES;

/** Where an index's valuation sits against its own last 1, 3 or 5 years: the line, its median, a one-standard-deviation band, and a plain verdict. */
function IndexValuation({ code, setCode }: { code: string; setCode: (c: string) => void }) {
  const feed = useIndices();
  const [years, setYears] = useState(5), [m, setM] = useState<Measure>("pe"), [find, setFind] = useState("");
  const { data, isLoading, isError, error, refetch, isFetching } = useIndexHistory(code, years);
  const list = useMemo(() => (feed.data?.items || []).filter((r) => r.pe != null || r.pb != null), [feed.data]);
  const pick = list.filter((r) => !find.trim() || r.name.toLowerCase().includes(find.trim().toLowerCase())).slice(0, 60);
  const st: Stat | null = data?.stats[m] ?? null;
  const rows = data?.rows || [];
  const series = rows.map((r) => r[m]);
  const verdict = (s: Stat) => {
    const z = s.sd ? (s.now - s.median) / s.sd : 0, cheapSide = m === "dy" ? z > 0 : z < 0, far = Math.abs(z) >= 1;
    return { word: Math.abs(z) < 0.5 ? "Close to its usual level" : cheapSide ? (far ? "Cheap against its own history" : "Slightly cheap against its own history") : far ? "Expensive against its own history" : "Slightly expensive against its own history",
      tone: Math.abs(z) < 0.5 ? "gold" : cheapSide ? "up" : "down" };
  };
  return (
    <section aria-label="Index valuation">
      <div className="pm-bar">
        <label>Index<select value={code} onChange={(e) => setCode(e.target.value)}>{(list.length ? list : [{ code, name: data?.name || code } as IndexRow]).map((r) => <option key={r.code} value={r.code}>{r.name}</option>)}</select></label>
        <label>Find<input value={find} onChange={(e) => setFind(e.target.value)} placeholder="Type to narrow, e.g. Bank" /></label>
        {find.trim() && <div className="pm-pick">{pick.map((r) => <button key={r.code} type="button" className="bandc" onClick={() => { setCode(r.code); setFind(""); }}>{r.name}</button>)}{!pick.length && <span className="faint">No index with that name.</span>}</div>}
        <div className="pm-seg" role="group" aria-label="Period">{[1, 3, 5].map((y) => <button key={y} type="button" aria-pressed={years === y} onClick={() => setYears(y)}>{y}Y</button>)}</div>
        <div className="pm-seg" role="group" aria-label="Measure">{(Object.keys(MEASURES) as Measure[]).map((k) => <button key={k} type="button" aria-pressed={m === k} onClick={() => setM(k)}>{MEASURES[k].label}</button>)}</div>
      </div>
      {isError ? <Problem e={error} retry={() => refetch()} /> : isLoading || !data ? <Loading /> : !st ? <div className="pm-empty">{data.name} has no {MEASURES[m].label} history from the data provider. Try P/B or another index.</div> : (() => {
        const v = verdict(st), f = (x: number) => nf(x, MEASURES[m].d) + MEASURES[m].unit;
        return <>
          <div className="pm-verdict"><span className={"chip " + v.tone}>{v.word}</span>
            <span><b>{data.name} {MEASURES[m].label} {f(st.now)}</b> <span className="faint">against a {years}-year median of {f(st.median)} · higher than on {nf(st.pctile, 0)}% of days{isFetching ? " · refreshing…" : ""}</span></span></div>
          <div className="pm-cards" aria-label="Range over the period">
            <div className="pm-kpi"><small>Now</small><b>{f(st.now)}</b><i>{data.to ? dateIN(data.to) : ""}</i></div>
            <div className="pm-kpi"><small>{years}-year median</small><b>{f(st.median)}</b><i>Average {f(st.mean)}</i></div>
            <div className="pm-kpi"><small>Usual range (±1 sd)</small><b style={{ fontSize: 21 }}>{f(Math.max(0, st.median - st.sd))} – {f(st.median + st.sd)}</b><i>Two days in three fall here</i></div>
            <div className="pm-kpi"><small>Low · High</small><b style={{ fontSize: 21 }}>{f(st.min)} · {f(st.max)}</b><i>{nf(st.n, 0)} trading days</i></div>
          </div>
          <div className="pm-chart card"><div className="pm-chart-h"><div><small>{MEASURES[m].say}</small><b>{data.name} {MEASURES[m].label}, last {years} year{years > 1 ? "s" : ""} <ChartHelp id="idx-valuation" /></b></div><span className="faint">Dashed: median · faint lines: usual range</span></div>
            <LineChart periods={rows.map((r) => dateIN(r.d, { day: "numeric", month: "short", year: "2-digit" }))} fmt={(x) => nf(x, MEASURES[m].d)} height={280} avg={st.median} avgLabel="Median"
              series={[{ key: m, label: MEASURES[m].label, color: "var(--gold)", values: series },
                { key: "hi", label: "Upper usual", color: "color-mix(in srgb, var(--muted) 45%, transparent)", values: rows.map(() => st.median + st.sd) },
                { key: "lo", label: "Lower usual", color: "color-mix(in srgb, var(--muted) 45%, transparent)", values: rows.map(() => Math.max(0, st.median - st.sd)) }]} /></div>
          <div className="pm-tools"><button className="alx-link" onClick={() => downloadCsv(`finlit-${data.code}-valuation-${years}y`, ["Date", "P/E", "P/B", "Dividend yield %"], rows.map((r) => [r.d, r.pe, r.pb, r.dy]))}><Icon name="table" /> Export CSV ({nf(rows.length, 0)} days)</button></div>
        </>;
      })()}
    </section>
  );
}

type Item = { code: string; name: string; weight: number | null };
type Hist = { history: { period: string; label: string; value: number | null }[]; changes: { period: string; value: number | null }[]; changesUnavailable?: boolean };

function Commodities() {
  const [cat, setCat] = useState<"monthly_index" | "core_infra">("monthly_index");
  const [picked, setPicked] = useState<Record<string, string>>({}); const [q, setQ] = useState("");
  const list = usePremium<{ items: Item[]; fetchedAt: string }>(`/commodities?category=${cat}`);
  const code = picked[cat] || list.data?.items?.[0]?.code || null;   // the first series is shown until the member picks one
  const setCode = (c: string) => setPicked({ ...picked, [cat]: c });
  const hist = usePremium<Hist>(`/commodities/${code}`, !!code);
  const items = (list.data?.items || []).filter((i) => i.name.toLowerCase().includes(q.trim().toLowerCase()));
  const rows = hist.data?.history || [];
  const latest = rows[0], prev = rows[1];
  return (
    <section aria-label="Commodities">
      <div className="pm-bar"><div className="pm-seg" role="group" aria-label="Series">{([["monthly_index", "Monthly commodity indices"], ["core_infra", "Eight core industries"]] as const).map(([k, l]) => <button key={k} aria-pressed={cat === k} onClick={() => setCat(k)}>{l}</button>)}</div>
        <label style={{ marginLeft: "auto" }}>Find a series<input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. steel" /></label></div>
      <p className="pm-meta">Values are monthly index levels, not rupee prices.</p>
      {list.isError ? <Problem e={list.error} retry={() => list.refetch()} /> : list.isLoading ? <Loading /> : (
        <div style={{ display: "grid", gap: 18, gridTemplateColumns: "minmax(220px, 320px) 1fr", alignItems: "start" }} className="pm-comm">
          <ul className="scr-sec" aria-label="Series" style={{ maxHeight: 460, overflow: "auto" }}>{items.map((i) => <li key={i.code}><label><input type="radio" name="com" checked={code === i.code} onChange={() => setCode(i.code)} /><span>{i.name}</span>{i.weight != null && <small className="faint" style={{ marginLeft: "auto" }}>{nf(i.weight, 1)}</small>}</label></li>)}{!items.length && <li className="faint">No series match.</li>}</ul>
          <div>{hist.isError ? <Problem e={hist.error} retry={() => hist.refetch()} /> : hist.isLoading || !code ? <Loading /> : (
            <>
              <div className="pm-cards"><div className="pm-kpi"><small>Latest ({latest?.label || MINUS})</small><b>{latest?.value != null ? nf(latest.value) : MINUS}</b></div>
                <div className="pm-kpi"><small>Change on last month</small><b>{latest?.value != null && prev?.value ? pc(((latest.value - prev.value) / prev.value) * 100) : MINUS}</b></div></div>
              {hist.data?.changesUnavailable && <p className="pm-meta">Provider percentage changes are unavailable right now. The history below is still correct.</p>}
              {rows.length > 1 && <div className="pm-chart card"><div className="pm-chart-h"><div><small>Trend</small><b>{list.data?.items.find((i) => i.code === code)?.name} <ChartHelp id="commodity-trend" /></b></div><span className="faint">Monthly index level</span></div>
                <LineChart periods={[...rows].reverse().map((r) => r.label)} series={[{ key: "v", label: "Index", color: "var(--gold)", values: [...rows].reverse().map((r) => r.value) }]} fmt={(x) => nf(x, 1)} height={230} area /></div>}
              <Table cols={[{ key: "label", label: "Month" }, { key: "value", label: "Index level", num: true, fmt: n2 }]} rows={rows as unknown as Row[]} q="" file={`finlit-commodity-${code}`} />
            </>)}</div>
        </div>)}
    </section>
  );
}

/** The week in four numbers, from the same saved feeds the tabs use (already loading when the page opens). */
function Glance({ go }: { go: (t: (typeof TABS)[number]["id"]) => void }) {
  const ipo = usePremium<Feed<Row>>("/markets/ipo"), res = usePremium<Feed<Row>>("/markets/results"), ann = usePremium<Feed<Row>>("/markets/announcements"), idx = useIndices();
  const week = Date.now() + 7 * 864e5;
  const open = (ipo.data?.items || []).filter((r) => /open|live|current/i.test(String(r.ipo_status || ""))).length;
  const soon = (ipo.data?.items || []).filter((r) => /upcoming|forthcoming/i.test(String(r.ipo_status || ""))).length;
  const now = Date.now() - 864e5;
  const due = (res.data?.items || []).filter((r) => { const t = r.expected_result_date ? new Date(String(r.expected_result_date)).getTime() : NaN; return t >= now && t <= week; }).length;
  const nifty = (idx.data?.items || []).find((r) => r.code === "NIF50");
  const k = (v: React.ReactNode, ready: boolean) => (ready ? v : <span className="skeleton" style={{ display: "inline-block", width: 60, height: 26 }} />);
  return (
    <div className="pm-cards" aria-label="This week at a glance">
      <button className="pm-kpi pm-kpi-btn" onClick={() => go("ipo")}><small>IPOs open now</small><b>{k(open, !!ipo.data)}</b><i>{ipo.data ? `${soon} upcoming` : " "}</i></button>
      <button className="pm-kpi pm-kpi-btn" onClick={() => go("results")}><small>Results due this week</small><b>{k(due, !!res.data)}</b><i>{res.data ? `${res.data.items.length} in the calendar` : " "}</i></button>
      <button className="pm-kpi pm-kpi-btn" onClick={() => go("announcements")}><small>Announcements, last 7 days</small><b>{k(ann.data?.items.length ?? 0, !!ann.data)}</b><i>Filings and board outcomes</i></button>
      <button className="pm-kpi pm-kpi-btn" onClick={() => go("indices")}><small>NIFTY 50</small><b>{k(nifty?.close != null ? nf(nifty.close) : MINUS, !!idx.data)}</b><i>{nifty ? pc(nifty.changePct) : "Index level"}{nifty?.pe != null ? ` · P/E ${nf(nifty.pe, 1)}` : ""}</i></button>
    </div>
  );
}

export function MarketsPage() {
  useDocTitle("Market events & index dashboard", "IPO and results calendars, announcements, call transcripts, index prices and valuations, and commodity trends.");
  const gold = useGold(); const qc = useQueryClient();
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>(() => (TABS.find((t) => t.id === location.hash.slice(1))?.id) || "ipo");
  const [idx, setIdx] = useState("NIF50");
  const openIndex = (c: string) => { setIdx(c); setTab("valuations"); window.scrollTo({ top: 0, behavior: "smooth" }); };
  useEffect(() => { if (gold) prefetchMarkets(qc); }, [gold, qc]);
  useEffect(() => { history.replaceState(history.state, "", "#" + tab); }, [tab]);   // keep the router's own state
  if (!gold) return <><PremiumHead eyebrow="Gold dashboard" title="Market Events & Index Dashboard" /><GoldLock title="Market Events & Index Dashboard" /></>;
  return (
    <>
      <PremiumHead eyebrow="Gold dashboard" title="Market Events & Index Dashboard"><p>The week ahead in one place: new issues, results, company announcements, how the indices are valued, and where commodities are heading. <Link to="/premium">All Gold dashboards</Link></p></PremiumHead>
      <div className="wrap" style={{ paddingBottom: 56 }}>
        <Glance go={setTab} />
        <div className="pm-tabs" role="tablist" aria-label="Market dashboard sections">{TABS.map((t) => <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}>{t.label}</button>)}</div>
        {tab === "commodities" ? <Commodities /> : tab === "indices" ? <IndexPrices open={openIndex} /> : tab === "valuations" ? <IndexValuation code={idx} setCode={setIdx} /> : <Feed key={tab} section={tab} />}
        <p className="pm-meta" style={{ marginTop: 22 }}>General information, not investment advice. Index levels refresh every minute while the market is open; valuations (P/E, P/B, dividend yield) are published once a day.</p>
      </div>
    </>
  );
}
