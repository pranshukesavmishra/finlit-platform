import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { Icon } from "../lib/icons";
import { dateIN, nf, MINUS } from "../lib/format";
import { prefetchMarkets, qs, useGold, usePremium, type Feed, type MarketSection } from "../lib/premium";
import { useDocTitle } from "../lib/title";
import { GoldLock, PremiumHead } from "./Premium";

type Row = Record<string, string | number | null | undefined>;
type Col = { key: string; label: string; num?: boolean; wide?: boolean; fmt?: (v: string | number | null | undefined, r: Row) => React.ReactNode };

const txt = (v: unknown) => (v == null || v === "" ? MINUS : String(v));
const dt = (v: unknown) => (v ? dateIN(String(v).slice(0, 10)) : MINUS);
const n2 = (v: unknown) => (typeof v === "number" ? nf(v) : MINUS);
const pc = (v: unknown) => (typeof v === "number" ? <span style={{ color: v >= 0 ? "var(--gain)" : "var(--loss)" }}>{(v > 0 ? "▲ +" : v < 0 ? "▼ " + MINUS : "") + nf(v)}%</span> : MINUS);
const doc = (v: unknown) => (v ? <a href={String(v)} target="_blank" rel="noopener noreferrer">Open document</a> : MINUS);

const TABS: { id: MarketSection | "commodities"; label: string }[] = [
  { id: "ipo", label: "IPO calendar" }, { id: "results", label: "Results calendar" }, { id: "announcements", label: "Announcements" },
  { id: "transcripts", label: "Call transcripts" }, { id: "indices", label: "Index prices" }, { id: "valuations", label: "Index valuation" }, { id: "commodities", label: "Commodities" },
];

const COLS: Record<string, Col[]> = {
  ipo: [{ key: "company_name", label: "Company" }, { key: "security_type", label: "Type" }, { key: "ipo_status", label: "Status" }, { key: "start_date", label: "Opens", fmt: dt }, { key: "end_date", label: "Closes", fmt: dt },
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

function Table({ cols, rows, q }: { cols: Col[]; rows: Row[]; q: string }) {
  const [page, setPage] = useState(0);
  const shown = useMemo(() => { const s = q.trim().toLowerCase(); return s ? rows.filter((r) => Object.values(r).some((v) => String(v ?? "").toLowerCase().includes(s))) : rows; }, [rows, q]);
  useEffect(() => setPage(0), [q, rows]);
  const pages = Math.max(1, Math.ceil(shown.length / PAGE));
  if (!shown.length) return <div className="pm-empty">Nothing matches. Try a wider date range or clear the search.</div>;
  return (
    <>
      <div className="tw"><table className="pm-t"><thead><tr>{cols.map((c) => <th key={c.key} className={c.num ? "n" : ""}>{c.label}</th>)}</tr></thead>
        <tbody>{shown.slice(page * PAGE, page * PAGE + PAGE).map((r, i) => <tr key={i}>{cols.map((c) => <td key={c.key} className={(c.num ? "n " : "") + (c.wide ? "wrapc" : "")}>{c.fmt ? c.fmt(r[c.key], r) : txt(r[c.key])}</td>)}</tr>)}</tbody></table></div>
      <div className="pm-pager"><span>{shown.length} rows</span><button className="btn" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button><span>Page {page + 1} of {pages}</span><button className="btn" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>Next</button></div>
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
          <p className="pm-meta"><Icon name="check" /> Updated {data?.fetchedAt ? new Date(data.fetchedAt).toLocaleString("en-IN", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "just now"} · Source: {data?.provider || "FinEdge"}{isFetching ? " · refreshing…" : ""}</p>
          <Table cols={COLS[section]} rows={data?.items || []} q={q} />
        </>)}
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
              <Table cols={[{ key: "label", label: "Month" }, { key: "value", label: "Index level", num: true, fmt: n2 }]} rows={rows as unknown as Row[]} q="" />
            </>)}</div>
        </div>)}
    </section>
  );
}

/** The week in four numbers, from the same saved feeds the tabs use (already loading when the page opens). */
function Glance({ go }: { go: (t: (typeof TABS)[number]["id"]) => void }) {
  const ipo = usePremium<Feed<Row>>("/markets/ipo"), res = usePremium<Feed<Row>>("/markets/results"), ann = usePremium<Feed<Row>>("/markets/announcements"), idx = usePremium<Feed<Row>>("/markets/indices");
  const week = Date.now() + 7 * 864e5;
  const open = (ipo.data?.items || []).filter((r) => /open|live|current/i.test(String(r.ipo_status || ""))).length;
  const soon = (ipo.data?.items || []).filter((r) => /upcoming|forthcoming/i.test(String(r.ipo_status || ""))).length;
  const due = (res.data?.items || []).filter((r) => r.expected_result_date && new Date(String(r.expected_result_date)).getTime() <= week).length;
  const nifty = (idx.data?.items || []).find((r) => /^nifty ?50$/i.test(String(r.index_name || r.index_symbol || "")));
  const k = (v: React.ReactNode, ready: boolean) => (ready ? v : <span className="skeleton" style={{ display: "inline-block", width: 60, height: 26 }} />);
  return (
    <div className="pm-cards" aria-label="This week at a glance">
      <button className="pm-kpi pm-kpi-btn" onClick={() => go("ipo")}><small>IPOs open now</small><b>{k(open, !!ipo.data)}</b><i>{ipo.data ? `${soon} upcoming` : " "}</i></button>
      <button className="pm-kpi pm-kpi-btn" onClick={() => go("results")}><small>Results due this week</small><b>{k(due, !!res.data)}</b><i>{res.data ? `${res.data.items.length} in the calendar` : " "}</i></button>
      <button className="pm-kpi pm-kpi-btn" onClick={() => go("announcements")}><small>Announcements, last 7 days</small><b>{k(ann.data?.items.length ?? 0, !!ann.data)}</b><i>Filings and board outcomes</i></button>
      <button className="pm-kpi pm-kpi-btn" onClick={() => go("indices")}><small>NIFTY 50</small><b>{k(nifty && typeof nifty.close_price === "number" ? nf(nifty.close_price) : MINUS, !!idx.data)}</b><i>{nifty ? pc(nifty.change_pct) : "Index close"}</i></button>
    </div>
  );
}

export function MarketsPage() {
  useDocTitle("Market events & index dashboard", "IPO and results calendars, announcements, call transcripts, index prices and valuations, and commodity trends.");
  const gold = useGold(); const qc = useQueryClient();
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>(() => (TABS.find((t) => t.id === location.hash.slice(1))?.id) || "ipo");
  useEffect(() => { if (gold) prefetchMarkets(qc); }, [gold, qc]);
  useEffect(() => { history.replaceState(null, "", "#" + tab); }, [tab]);
  if (!gold) return <><PremiumHead eyebrow="Gold dashboard" title="Market Events & Index Dashboard" /><GoldLock title="Market Events & Index Dashboard" /></>;
  return (
    <>
      <PremiumHead eyebrow="Gold dashboard" title="Market Events & Index Dashboard"><p>The week ahead in one place: new issues, results, company announcements, how the indices are valued, and where commodities are heading. <Link to="/premium">All Gold dashboards</Link></p></PremiumHead>
      <div className="wrap" style={{ paddingBottom: 56 }}>
        <Glance go={setTab} />
        <div className="pm-tabs" role="tablist" aria-label="Market dashboard sections">{TABS.map((t) => <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => setTab(t.id)}>{t.label}</button>)}</div>
        {tab === "commodities" ? <Commodities /> : <Feed key={tab} section={tab} />}
        <p className="pm-meta" style={{ marginTop: 22 }}>General information, not investment advice. Index prices are end-of-day values.</p>
      </div>
    </>
  );
}
