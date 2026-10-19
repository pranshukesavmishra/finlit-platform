import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { Icon } from "../lib/icons";
import { dateIN, nf, signed, MINUS } from "../lib/format";
import { qs, useGold, usePremium } from "../lib/premium";
import { useUniverse } from "../lib/screener";
import { useDocTitle } from "../lib/title";
import { GoldLock, PremiumHead } from "./Premium";

type Pt = { period: string; value: number | null; change?: number | null };
type HRow = { category?: string; label?: string; unit?: string; history?: Pt[]; children?: HRow[] };
type Statement = { units_in?: string; income_statement?: HRow[]; cash_flow?: HRow[]; balance_sheet?: HRow[]; history?: Record<string, string | number | null>[] };
type Fund = {
  instrument?: { symbol?: string; name?: string }; statementType?: string; generatedAt?: string; sources?: Record<string, string>;
  quote?: { price?: number; change?: number; changePct?: number; timestamp?: string };
  highlights?: { label: string; value: number | null; benchmark?: number | null; period?: string }[];
  ratios?: { name: string; company_value: number | null; sector_value?: number | null }[];
  profitabilityRatios?: HRow[]; incomeStatement?: Statement; balanceSheet?: Statement; cashFlow?: Statement;
  shareholding?: HRow[]; shareholdingDetails?: HRow[]; ownershipStructure?: HRow[]; revenueSegments?: HRow[];
  corporateActions?: { type?: string; name?: string; purpose?: string; ex_date?: string; amount?: number | string | null; ratio?: string | null }[];
  competitors?: { name?: string; symbol?: string; sector?: string }[];
};

const SECTIONS = [["snapshot", "Snapshot"], ["income", "Income statement"], ["balance", "Balance sheet"], ["cash", "Cash flow"], ["ratios", "Ratios"], ["owners", "Shareholders"], ["peers", "Peers & actions"]] as const;
const val = (v: unknown) => (typeof v === "number" ? (v < 0 ? MINUS : "") + nf(v, Math.abs(v) >= 1000 ? 0 : 2) : v == null || v === "" ? MINUS : String(v));
const name = (r: HRow) => (r.label || r.category || "").replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

/** Rows of {label, history[]} as a table: newest period on the right-hand side of the heading order given by the data. */
function HistTable({ rows, limit, note, growth = true }: { rows: HRow[]; limit: number; note?: string; growth?: boolean }) {
  const periods = useMemo(() => { const seen: string[] = []; for (const r of rows) for (const p of r.history || []) if (!seen.includes(p.period)) seen.push(p.period); return seen.slice(0, limit); }, [rows, limit]);
  if (!rows.length || !periods.length) return <div className="pm-empty">This statement has not been reported for this company.</div>;
  return (
    <div className="tw"><table className="pm-t"><thead><tr><th>{note || "Item"}</th>{periods.map((p) => <th key={p} className="n">{p}</th>)}{growth && periods.length > 1 && <th className="n">Change</th>}</tr></thead>
      <tbody>{rows.map((r, i) => {
        const by = new Map((r.history || []).map((p) => [p.period, p.value]));
        const a = by.get(periods[0]), b = by.get(periods[1]);
        const ch = typeof a === "number" && typeof b === "number" && b !== 0 ? ((a - b) / Math.abs(b)) * 100 : null;
        return <tr key={(r.category || r.label || "") + i}><td>{name(r)}</td>{periods.map((p) => <td key={p} className="n">{val(by.get(p))}</td>)}
          {growth && periods.length > 1 && <td className="n" style={{ color: ch == null ? undefined : ch >= 0 ? "var(--gain)" : "var(--loss)", whiteSpace: "nowrap" }}>{ch == null || !Number.isFinite(ch) ? MINUS : signed(ch, 1)}</td>}</tr>;
      })}</tbody></table></div>
  );
}

function Tree({ rows }: { rows: HRow[] }) {
  if (!rows.length) return <div className="pm-empty">Detailed shareholding is not available for this company.</div>;
  return <div className="pm-tree">{rows.map((r, i) => (
    <details key={i}><summary>{name(r)} <span className="faint">· {val(r.history?.[0]?.value)}% in {r.history?.[0]?.period || MINUS}</span></summary>
      {r.children?.length ? <ul>{r.children.slice(0, 60).map((c, j) => <li key={j}><span>{name(c)}</span><b>{val(c.history?.[0]?.value)}%</b></li>)}</ul> : <p className="faint" style={{ margin: "0 0 8px 18px" }}>No named holders are reported in this category.</p>}</details>))}</div>;
}

export function FundamentalsPage() {
  useDocTitle("Stock fundamental data dashboard", "Income statement, balance sheet, cash flow, ratios, named shareholders, peers and corporate actions for any listed company.");
  const gold = useGold();
  const [params, setParams] = useSearchParams();
  const company = params.get("c") || "", statement = params.get("s") === "standalone" ? "standalone" : "consolidated", period = params.get("p") === "quarterly" ? "quarterly" : "yearly";
  const [text, setText] = useState(company), [open, setOpen] = useState(false), [sec, setSec] = useState<(typeof SECTIONS)[number][0]>("snapshot");
  const universe = useUniverse();
  const sug = useMemo(() => {
    const t = text.trim().toLowerCase(); if (t.length < 1 || t === company.toLowerCase()) return [];
    return (universe.data?.rows || []).filter((r) => r.symbol.toLowerCase().startsWith(t) || (r.name || "").toLowerCase().includes(t)).slice(0, 8);
  }, [text, company, universe.data]);
  const set = (o: Record<string, string>) => { const n = new URLSearchParams(params); for (const [k, v] of Object.entries(o)) v ? n.set(k, v) : n.delete(k); setParams(n, { replace: true }); };
  const { data, isLoading, isError, error, refetch, isFetching } = usePremium<Fund>(`/fundamentals${qs({ query: company, statement_type: statement, period })}`, gold && company.length >= 2);
  if (!gold) return <><PremiumHead eyebrow="Gold dashboard" title="Stock Fundamental Data Dashboard" /><GoldLock title="Stock Fundamental Data Dashboard" /></>;
  const limit = period === "quarterly" ? 10 : 8;
  const status = (error as { status?: number } | null)?.status;
  return (
    <>
      <PremiumHead eyebrow="Gold dashboard" title="Stock Fundamental Data Dashboard"><p>Search any listed company for its full statements, ratios and named shareholders. <Link to="/premium">All Gold dashboards</Link></p></PremiumHead>
      <div className="wrap" style={{ paddingBottom: 56 }}>
        <div className="pm-bar" style={{ alignItems: "center" }}>
          <div className="pm-search" style={{ flex: 1, minWidth: 260 }}><Icon name="search" />
            <input value={text} onChange={(e) => { setText(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}
              onKeyDown={(e) => { if (e.key === "Enter" && text.trim().length >= 2) { set({ c: sug[0]?.symbol || text.trim() }); setOpen(false); } }}
              placeholder="Search a company or symbol, for example RELIANCE" aria-label="Search a company" role="combobox" aria-expanded={open && sug.length > 0} aria-controls="pm-sug" />
            {open && sug.length > 0 && <div className="pm-sug" id="pm-sug" role="listbox">{sug.map((r) => <button key={r.symbol} role="option" aria-selected={false} onMouseDown={(e) => e.preventDefault()} onClick={() => { setText(r.symbol); set({ c: r.symbol }); setOpen(false); }}><b>{r.symbol}</b><small>{r.name}</small></button>)}</div>}</div>
          <div className="pm-seg" role="group" aria-label="Statement type">{(["consolidated", "standalone"] as const).map((s) => <button key={s} aria-pressed={statement === s} onClick={() => set({ s: s === "consolidated" ? "" : s })}>{s === "consolidated" ? "Consolidated" : "Standalone"}</button>)}</div>
          <div className="pm-seg" role="group" aria-label="Period">{(["yearly", "quarterly"] as const).map((s) => <button key={s} aria-pressed={period === s} onClick={() => set({ p: s === "yearly" ? "" : s })}>{s === "yearly" ? "Yearly" : "Quarterly"}</button>)}</div>
        </div>
        {!company ? (
          <div className="pm-empty"><b>Pick a company to begin.</b><p>Try <button className="alx-link" onClick={() => { setText("RELIANCE"); set({ c: "RELIANCE" }); }}>RELIANCE</button>, <button className="alx-link" onClick={() => { setText("TCS"); set({ c: "TCS" }); }}>TCS</button> or <button className="alx-link" onClick={() => { setText("HDFCBANK"); set({ c: "HDFCBANK" }); }}>HDFCBANK</button>.</p></div>
        ) : isError ? (
          <div className="state"><h2>{status === 404 ? "We could not find that company" : "This company's data is not available right now"}</h2><p>{status === 404 ? "Check the symbol and try again." : "The data provider did not answer. Please try again in a moment."}</p>{status !== 404 && <button className="btn" onClick={() => refetch()}>Try again</button>}</div>
        ) : isLoading || !data ? <div className="skeleton" style={{ height: 420 }} aria-busy="true" aria-label="Loading company data" /> : (
          <>
            <div className="pm-meta" style={{ justifyContent: "space-between" }}>
              <span><b style={{ color: "var(--text)", fontSize: 18 }}>{data.instrument?.name || data.instrument?.symbol}</b> · {data.instrument?.symbol} · {data.statementType === "standalone" ? "Standalone" : "Consolidated"} {period === "quarterly" ? "quarterly" : "yearly"} figures{data.quote?.price ? <> · ₹{nf(data.quote.price)}{typeof data.quote.changePct === "number" && <> <span style={{ color: data.quote.changePct >= 0 ? "var(--gain)" : "var(--loss)" }}>{signed(data.quote.changePct)}</span></>}</> : null}</span>
              <span>{data.generatedAt ? "Updated " + dateIN(data.generatedAt) : ""}{isFetching ? " · refreshing…" : ""} · <Link to={`/stocks/${data.instrument?.symbol || company}`}>Open full research page</Link></span></div>
            <div className="pm-tabs" role="tablist" aria-label="Sections">{SECTIONS.map(([id, label]) => <button key={id} role="tab" aria-selected={sec === id} onClick={() => setSec(id)}>{label}</button>)}</div>
            {sec === "snapshot" && (<>
              <div className="pm-cards">{(data.highlights || []).map((h) => <div className="pm-kpi" key={h.label}><small>{h.label}{h.period ? ` · ${h.period}` : ""}</small><b>{val(h.value)}</b>{/revenue|profit/i.test(h.label) && data.incomeStatement?.units_in && <i>{data.incomeStatement.units_in}</i>}{h.benchmark != null && <i>Sector: {val(h.benchmark)}</i>}</div>)}</div>
              {!(data.highlights || []).length && <div className="pm-empty">No headline figures were reported.</div>}
              <div className="pm-sec"><h2>Revenue by segment</h2><HistTable rows={data.revenueSegments || []} limit={limit} /></div></>)}
            {sec === "income" && <><p className="pm-meta">Amounts in {data.incomeStatement?.units_in || "the company's reporting unit"}.</p><HistTable rows={data.incomeStatement?.income_statement || []} limit={limit} /></>}
            {sec === "balance" && <><p className="pm-meta">Amounts in {data.balanceSheet?.units_in || "the company's reporting unit"}.</p><HistTable rows={data.balanceSheet?.balance_sheet || []} limit={limit} /></>}
            {sec === "cash" && <><p className="pm-meta">Amounts in {data.cashFlow?.units_in || "the company's reporting unit"}.</p><HistTable rows={data.cashFlow?.cash_flow || []} limit={limit} /></>}
            {sec === "ratios" && (<>
              <div className="tw"><table className="pm-t"><thead><tr><th>Ratio</th><th className="n">Company</th><th className="n">Sector</th></tr></thead>
                <tbody>{(data.ratios || []).map((r) => <tr key={r.name}><td>{r.name}</td><td className="n">{val(r.company_value)}</td><td className="n">{val(r.sector_value)}</td></tr>)}</tbody></table></div>
              {!(data.ratios || []).length && <div className="pm-empty">No ratios were reported.</div>}
              <div className="pm-sec"><h2>Profitability over time</h2><HistTable rows={data.profitabilityRatios || []} limit={limit} /></div></>)}
            {sec === "owners" && (<>
              <h2 className="pm-sec" style={{ marginTop: 0, font: "500 22px var(--serif)" }}>Shareholding pattern</h2><HistTable rows={data.shareholding || []} limit={limit} note="Holder group, % held" growth={false} />
              <div className="pm-sec"><h2>Structure summary and promoter pledge</h2><HistTable rows={data.ownershipStructure || []} limit={limit} growth={false} /></div>
              <div className="pm-sec"><h2>Named shareholders</h2><Tree rows={data.shareholdingDetails || []} /></div></>)}
            {sec === "peers" && (<>
              <h2 className="pm-sec" style={{ marginTop: 0, font: "500 22px var(--serif)" }}>Peers</h2>
              {(data.competitors || []).length ? <div className="tw"><table className="pm-t"><thead><tr><th>Company</th><th>Symbol</th><th>Sector</th></tr></thead><tbody>{data.competitors!.map((c, i) => <tr key={i}><td>{c.name || MINUS}</td><td>{c.symbol ? <Link to={`/premium/fundamentals?c=${encodeURIComponent(c.symbol)}`} onClick={() => { setText(c.symbol!); }}>{c.symbol}</Link> : MINUS}</td><td>{c.sector || MINUS}</td></tr>)}</tbody></table></div> : <div className="pm-empty">No peers were reported.</div>}
              <div className="pm-sec"><h2>Dividends and corporate actions</h2>
                {(data.corporateActions || []).length ? <div className="tw"><table className="pm-t"><thead><tr><th>Type</th><th>Detail</th><th>Ex-date</th><th className="n">Amount / ratio</th></tr></thead><tbody>{data.corporateActions!.slice(0, 40).map((a, i) => <tr key={i}><td>{a.type || MINUS}</td><td className="wrapc">{a.name || a.purpose || MINUS}</td><td>{a.ex_date ? dateIN(String(a.ex_date).slice(0, 10)) : MINUS}</td><td className="n">{a.amount != null && a.amount !== "" ? val(Number(a.amount)) : a.ratio || MINUS}</td></tr>)}</tbody></table></div> : <div className="pm-empty">No corporate actions were reported.</div>}</div></>)}
            <p className="pm-meta" style={{ marginTop: 22 }}>Figures come from company filings through FinEdge. Missing values show a dash. General information, not investment advice.</p>
          </>)}
      </div>
    </>
  );
}
