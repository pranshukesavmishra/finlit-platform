import { HScroll } from "../components/HScroll";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { StackArea } from "../charts/Atlas";
import { Donut } from "../charts/Small";
import { LineChart } from "../charts/LineChart";
import { MiniBars } from "../charts/MiniBars";
import { Icon } from "../lib/icons";
import { dateIN, nf, signed, MINUS } from "../lib/format";
import { downloadCsv, pushRecent, qs, readRecent, useGold, usePremium, useSlashFocus } from "../lib/premium";
import { useUniverse } from "../lib/screener";
import { useSection, type Financials, type Ratios as StockRatios, type Table as StockTable } from "../lib/api";
import { ProfitabilityRatios } from "../stock/ProfitabilityRatios";
import { DuPont } from "../stock/DuPont";
import { ProfitReality } from "../stock/ProfitReality";
import { useDocTitle } from "../lib/title";
import { GoldLock, PremiumHead } from "./Premium";
import { ChartHelp } from "../components/ChartHelp";

type Pt = { period: string; value: number | null; change?: number | null };
type HRow = { category?: string; label?: string; unit?: string; history?: Pt[]; children?: HRow[] };
type Statement = { units_in?: string; income_statement?: HRow[]; cash_flow?: HRow[]; balance_sheet?: HRow[] };
type Fund = {
  instrument?: { symbol?: string; name?: string }; statementType?: string; generatedAt?: string;
  quote?: { price?: number; change?: number; changePct?: number; timestamp?: string };
  highlights?: { label: string; value: number | null; benchmark?: number | null; period?: string }[];
  ratios?: { name: string; company_value: number | null; sector_value?: number | null }[];
  profitabilityRatios?: HRow[]; incomeStatement?: Statement; balanceSheet?: Statement; cashFlow?: Statement;
  shareholding?: HRow[]; shareholdingDetails?: HRow[]; ownershipStructure?: HRow[]; revenueSegments?: HRow[];
  corporateActions?: { type?: string; name?: string; purpose?: string; ex_date?: string; amount?: number | string | null; ratio?: string | null }[];
  competitors?: { name?: string; symbol?: string; sector?: string }[];
};

const SECTIONS = [["snapshot", "Snapshot"], ["income", "Income statement"], ["balance", "Balance sheet"], ["cash", "Cash flow"], ["ratios", "Ratios"], ["owners", "Shareholders"], ["peers", "Peers & actions"]] as const;
type Sec = (typeof SECTIONS)[number][0];
const PALETTE = ["var(--c1)", "var(--c2)", "var(--c3)", "var(--c4)", "var(--c5)", "var(--k6)", "var(--k7)", "var(--k8)"];
const val = (v: unknown) => (typeof v === "number" ? (v < 0 ? MINUS : "") + nf(Math.abs(v), Math.abs(v) >= 1000 ? 0 : 2) : v == null || v === "" ? MINUS : String(v));
const short = (v: number) => { const a = Math.abs(v); return (v < 0 ? MINUS : "") + (a >= 1e5 ? nf(a / 1e5, 1) + "L" : a >= 1e3 ? nf(a / 1e3, 1) + "k" : nf(a, a >= 100 ? 0 : 1)); };
const name = (r: HRow) => (r.label || r.category || "").replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
const find = (rows: HRow[] | undefined, re: RegExp) => (rows || []).find((r) => re.test(r.category || "") || re.test(r.label || ""));

/** Periods as the data gives them (newest first), capped. */
function periodsOf(rows: HRow[], limit: number) {
  const seen: string[] = [];
  for (const r of rows) for (const p of r.history || []) if (!seen.includes(p.period)) seen.push(p.period);
  return seen.slice(0, limit);
}
const series = (r: HRow | undefined, periods: string[]) => { const by = new Map((r?.history || []).map((p) => [p.period, p.value])); return periods.map((p) => by.get(p) ?? null); };

/** A statement table where every line can be charted: click a row and the chart above follows it. */
function Statement({ rows, limit, unit, file, growth = true, chart = true }: { rows: HRow[]; limit: number; unit?: string; file: string; growth?: boolean; chart?: boolean }) {
  const periods = useMemo(() => periodsOf(rows, limit), [rows, limit]);
  const [pick, setPick] = useState(0);
  useEffect(() => setPick(0), [rows]);
  if (!rows.length || !periods.length) return <div className="pm-empty">This has not been reported for this company.</div>;
  const row = rows[Math.min(pick, rows.length - 1)];
  const asc = [...periods].reverse(), vals = series(row, periods).reverse();
  const csv = () => downloadCsv(file, ["Item", ...periods], rows.map((r) => [name(r), ...series(r, periods)]));
  return (
    <>
      {chart && vals.some((v) => v != null) && (
        <div className="pm-chart card">
          <div className="pm-chart-h"><div><small>Charting</small><b>{name(row)} <ChartHelp id="fund-statement" /></b></div><span className="faint">{unit ? `In ${unit} · ` : ""}Click any line below to chart it</span></div>
          <MiniBars labels={asc} series={[{ key: "v", label: name(row), values: vals, color: "var(--gold)" }]} fmt={short} height={190} w={720} highlight={asc.length - 1} />
        </div>)}
      <div className="pm-tools"><button className="alx-link" onClick={csv}><Icon name="table" /> Export CSV</button></div>
      <HScroll className="" label="table"><table className="pm-t pm-pick"><thead><tr><th>Item</th>{periods.map((p) => <th key={p} className="n">{p}</th>)}{growth && periods.length > 1 && <th className="n">Change</th>}</tr></thead>
        <tbody>{rows.map((r, i) => {
          const s = series(r, periods), a = s[0], b = s[1];
          const ch = typeof a === "number" && typeof b === "number" && b !== 0 ? ((a - b) / Math.abs(b)) * 100 : null;
          return (
            <tr key={(r.category || r.label || "") + i} className={chart && i === pick ? "on" : ""} onClick={chart ? () => setPick(i) : undefined} tabIndex={chart ? 0 : undefined}
              onKeyDown={chart ? (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setPick(i); } } : undefined} aria-selected={chart ? i === pick : undefined}>
              <td>{name(r)}</td>{s.map((v, j) => <td key={j} className="n">{val(v)}</td>)}
              {growth && periods.length > 1 && <td className="n" style={{ color: ch == null ? undefined : ch >= 0 ? "var(--gain)" : "var(--loss)", whiteSpace: "nowrap" }}>{ch == null || !Number.isFinite(ch) ? MINUS : signed(ch, 1)}</td>}
            </tr>);
        })}</tbody></table></HScroll>
    </>
  );
}

function Tree({ rows }: { rows: HRow[] }) {
  const [q, setQ] = useState("");
  if (!rows.length) return <div className="pm-empty">Detailed shareholding is not available for this company.</div>;
  const s = q.trim().toLowerCase();
  return (
    <>
      <div className="pm-bar"><label>Find a shareholder<input value={q} onChange={(e) => setQ(e.target.value)} placeholder="e.g. Life Insurance" /></label></div>
      <div className="pm-tree">{rows.map((r, i) => {
        const kids = (r.children || []).filter((c) => !s || name(c).toLowerCase().includes(s));
        if (s && !kids.length && !name(r).toLowerCase().includes(s)) return null;
        return (
          <details key={i} open={!!s}><summary>{name(r)} <span className="faint">· {val(r.history?.[0]?.value)}% in {r.history?.[0]?.period || MINUS}</span></summary>
            {kids.length ? <ul>{kids.slice(0, 80).map((c, j) => <li key={j}><span>{name(c)}</span><b>{val(c.history?.[0]?.value)}%</b></li>)}</ul> : <p className="faint" style={{ margin: "0 0 8px 18px" }}>No named holders are reported in this category.</p>}
          </details>);
      })}</div>
    </>
  );
}

function Snapshot({ d, limit }: { d: Fund; limit: number }) {
  const pl = d.incomeStatement?.income_statement || [];
  const rev = find(pl, /^revenue|net_sales|total_income|interest_earned/i), np = find(pl, /net_profit|^pat$/i);
  const periods = periodsOf([rev, np].filter(Boolean) as HRow[], limit), asc = [...periods].reverse();
  const r = series(rev, periods).reverse(), p = series(np, periods).reverse();
  const margin = r.map((v, i) => (v && p[i] != null ? ((p[i] as number) / v) * 100 : null));
  const unit = d.incomeStatement?.units_in;
  const mv = margin.filter((v): v is number => v != null), mSpan = mv.length ? Math.max(...mv) - Math.min(...mv) : 0;
  const cagr = (() => { const f = r.find((v) => v != null && v > 0), l = [...r].reverse().find((v) => v != null && v > 0), n = r.filter((v) => v != null).length - 1; return f && l && n > 0 ? (Math.pow(l / f, 1 / n) - 1) * 100 : null; })();
  return (
    <>
      <div className="pm-cards">{(d.highlights || []).map((h) => {
        const vs = typeof h.value === "number" && typeof h.benchmark === "number" && h.benchmark !== 0 ? ((h.value - h.benchmark) / Math.abs(h.benchmark)) * 100 : null;
        return <div className="pm-kpi" key={h.label}><small>{h.label}{h.period ? ` · ${h.period}` : ""}</small><b>{val(h.value)}</b>
          {h.benchmark != null ? <i>Sector {val(h.benchmark)}{vs != null && <span className="chip ghost" style={{ marginLeft: 6, height: 20 }}>{vs >= 0 ? "above" : "below"} by {nf(Math.abs(vs), 0)}%</span>}</i>
            : /revenue|profit/i.test(h.label) && unit ? <i>{unit}</i> : null}</div>;
      })}</div>
      {!(d.highlights || []).length && <div className="pm-empty">No headline figures were reported.</div>}
      {asc.length > 1 && (
        <div className="pm-two">
          <div className="pm-chart card"><div className="pm-chart-h"><div><small>Growth</small><b>Revenue and net profit <ChartHelp id="fund-growth" /></b></div><span className="faint">{unit ? `In ${unit}` : ""}{cagr != null ? ` · revenue ${signed(cagr, 1)} a year` : ""}</span></div>
            <div className="pm-duo">
              <div><p className="pm-sub">Revenue</p><MiniBars labels={asc} series={[{ key: "r", label: "Revenue", values: r, color: "var(--c1)" }]} fmt={short} height={170} w={360} highlight={asc.length - 1} /></div>
              <div><p className="pm-sub">Net profit</p><MiniBars labels={asc} series={[{ key: "p", label: "Net profit", values: p, color: "var(--gold)" }]} fmt={short} height={170} w={360} highlight={asc.length - 1} /></div>
            </div></div>
          <div className="pm-chart card"><div className="pm-chart-h"><div><small>Quality</small><b>Net margin <ChartHelp id="fund-margin" /></b></div><span className="faint">Profit kept from each ₹100 of sales</span></div>
            <LineChart periods={asc} series={[{ key: "m", label: "Net margin", color: "var(--c3)", values: margin }]} fmt={(x) => nf(x, mSpan < 0.05 ? 3 : mSpan < 1 ? 2 : 1) + "%"} height={200} area /></div>
        </div>)}
      <div className="pm-sec"><h2>Revenue by segment</h2><Statement rows={d.revenueSegments || []} limit={limit} unit={unit} file={`${d.instrument?.symbol}-segments`} /></div>
    </>
  );
}

/** The eleven yearly margin and return ratios, from FinLit's own stored ratio history (the same provider data the stock page uses;
 *  complete for every loaded company), newest year first as the statement tables expect. */
const PROFITABILITY: [string, string][] = [["gross_margin", "Gross margin %"], ["operating_margin", "Operating margin %"], ["ebitda_margin", "EBITDA margin %"], ["ebit_margin", "EBIT margin %"],
  ["pretax_margin", "Pre-tax margin %"], ["net_margin", "Net margin %"], ["effective_tax_rate", "Effective tax rate %"], ["roe", "Return on equity %"], ["roce", "Return on capital %"],
  ["roa", "Return on assets %"], ["rota", "Return on tangible assets %"]];
const fyLabel = (p: string) => (/^FY\d{2}$/.test(p) ? `Mar 20${p.slice(2)}` : p);
function profitabilityRows(r?: StockRatios): HRow[] {
  const h = r?.history;
  if (!h?.periods?.length) return [];
  return PROFITABILITY.filter(([k]) => h.rows[k]?.some((v) => v != null))
    .map(([k, label]) => ({ label, history: h.periods.map((p, i) => ({ period: fyLabel(p), value: h.rows[k][i] ?? null })).reverse() }));
}

/** FinLit's own stored statements, shaped like the gateway's rows (newest period first). Used when the gateway sends nothing for a statement
 *  that FinLit already holds, so a tab never says "not reported" for a company whose report has the figures. */
const STMT: Record<"income" | "balance" | "cash", [string, string][]> = {
  income: [["revenue", "Revenue"], ["other_income", "Other income"], ["expenses", "Expenses"], ["operating_profit", "Operating profit"], ["finance_costs", "Interest"], ["depreciation", "Depreciation"], ["profit_before_tax", "Profit before tax"], ["tax", "Tax"], ["net_profit", "Net profit"], ["eps", "EPS"]],
  balance: [["equity_capital", "Equity capital"], ["reserves", "Reserves"], ["total_equity", "Total equity"], ["borrowings", "Borrowings"], ["other_liabilities", "Other liabilities"], ["total_liabilities", "Total liabilities"], ["fixed_assets", "Fixed assets"], ["cwip", "Capital work in progress"], ["investments", "Investments"], ["inventories", "Inventories"], ["receivables", "Receivables"], ["cash", "Cash"], ["total_assets", "Total assets"]],
  cash: [["operating", "Cash from operations"], ["investing", "Cash from investing"], ["financing", "Cash from financing"], ["net_cash_flow", "Net cash flow"], ["capex", "Capital expenditure"], ["free_cash_flow", "Free cash flow"], ["dividends_paid", "Dividends paid"]],
};
function storedRows(f: Financials | undefined, kind: keyof typeof STMT, quarterly: boolean): HRow[] {
  const t: StockTable | undefined = !f ? undefined : quarterly ? (kind === "income" ? f.quarterly.pl : undefined) : kind === "income" ? f.yearly.pl : kind === "balance" ? f.yearly.bs : f.yearly.cf;
  if (!t?.periods?.length) return [];
  return STMT[kind].filter(([k]) => t.rows[k]?.some((x) => x != null))
    .map(([k, label]) => ({ label, history: t.periods.map((p, i) => ({ period: fyLabel(p), value: t.rows[k][i] ?? null })).reverse() }));
}

function Ratios({ d, limit }: { d: Fund; limit: number }) {
  const rows = d.ratios || [];
  const sym = (d.instrument?.symbol || "").toUpperCase();
  const mine = useSection<StockRatios>(sym, "ratios", !!sym);
  const own = useMemo(() => profitabilityRows(mine.data), [mine.data]);
  return (
    <>
      {rows.length ? (
        <>
          <div className="pm-tools"><button className="alx-link" onClick={() => downloadCsv(`${d.instrument?.symbol}-ratios`, ["Ratio", "Company", "Sector"], rows.map((r) => [r.name, r.company_value, r.sector_value]))}><Icon name="table" /> Export CSV</button></div>
          <HScroll className="" label="table"><table className="pm-t"><thead><tr><th>Ratio</th><th className="n">Company</th><th className="n">Sector</th><th>Company against sector</th></tr></thead>
            <tbody>{rows.map((r) => {
              const c = r.company_value, s = r.sector_value, max = Math.max(Math.abs(c ?? 0), Math.abs(s ?? 0), 1e-9);
              return <tr key={r.name}><td>{r.name}</td><td className="n">{val(c)}</td><td className="n">{val(s)}</td>
                <td style={{ minWidth: 180 }}>{c != null && s != null ? <div className="pm-vs" aria-label={`Company ${val(c)}, sector ${val(s)}`}><span style={{ width: `${(Math.abs(c) / max) * 100}%` }} className="co" /><span style={{ width: `${(Math.abs(s) / max) * 100}%` }} className="se" /></div> : <span className="faint">{MINUS}</span>}</td></tr>;
            })}</tbody></table></HScroll>
          <p className="pm-legend"><i style={{ background: "var(--gold)" }} />Company <i style={{ background: "var(--faint)" }} />Sector</p>
        </>) : <div className="pm-empty">No ratios were reported.</div>}
      <div className="pm-sec"><h2>Profitability ratios <ChartHelp id="profit-ratios" /></h2>{mine.data?.history?.periods?.length ? <ProfitabilityRatios periods={mine.data.history.periods} rows={mine.data.history.rows as Record<string, (number | null)[]>} />  : <Statement rows={own.length ? own : d.profitabilityRatios || []} limit={limit} unit="%" file={`${d.instrument?.symbol}-profitability`} />}</div>{mine.data?.history?.periods?.length ? <DuPont symbol={sym} lender={false} /> : null}{mine.data?.history?.periods?.length ? <ProfitReality symbol={sym} lender={false} /> : null}
    </>
  );
}

function Owners({ d, limit }: { d: Fund; limit: number }) {
  const rows = d.shareholding || [];
  const periods = periodsOf(rows, limit), asc = [...periods].reverse();
  const parts = rows.map((r, i) => ({ label: name(r), value: r.history?.[0]?.value ?? 0, color: PALETTE[i % PALETTE.length] })).filter((p) => p.value > 0);
  return (
    <>
      {parts.length > 0 && (
        <div className="pm-two">
          <div className="pm-chart card"><div className="pm-chart-h"><div><small>Today</small><b>Who owns the company <ChartHelp id="fund-own-donut" /></b></div><span className="faint">{periods[0]}</span></div>
            <div style={{ display: "flex", gap: 20, alignItems: "center", flexWrap: "wrap" }}><div style={{ width: 190 }}><Donut slices={parts.map((x) => ({ v: x.value, color: x.color.replace(/^var\((.*)\)$/, "$1") }))} centerValue={nf(parts[0].value, 1) + "%"} centerLabel={parts[0].label} /></div>
              <ul className="pm-keys">{parts.map((p) => <li key={p.label}><i style={{ background: p.color }} />{p.label}<b>{nf(p.value, 2)}%</b></li>)}</ul></div></div>
          {asc.length > 1 && <div className="pm-chart card"><div className="pm-chart-h"><div><small>Trend</small><b>How ownership has moved <ChartHelp id="fund-own-trend" /></b></div><span className="faint">{asc[0]} to {asc[asc.length - 1]}</span></div>
            <StackArea periods={asc} series={rows.map((r, i) => ({ key: r.category || String(i), label: name(r), values: series(r, periods).reverse(), color: PALETTE[i % PALETTE.length] }))} w={620} /></div>}
        </div>)}
      <div className="pm-sec"><h2>Shareholding pattern</h2><Statement rows={rows} limit={limit} file={`${d.instrument?.symbol}-shareholding`} growth={false} chart={false} /></div>
      <div className="pm-sec"><h2>Structure summary and promoter pledge</h2><Statement rows={d.ownershipStructure || []} limit={limit} file={`${d.instrument?.symbol}-structure`} growth={false} chart={false} /></div>
      <div className="pm-sec"><h2>Named shareholders</h2><Tree rows={d.shareholdingDetails || []} /></div>
    </>
  );
}

export function FundamentalsPage() {
  useDocTitle("Stock fundamental data dashboard", "Income statement, balance sheet, cash flow, ratios, named shareholders, peers and corporate actions for any listed company.");
  const gold = useGold();
  const [params, setParams] = useSearchParams();
  const company = params.get("c") || "", statement = params.get("s") === "standalone" ? "standalone" : "consolidated", period = params.get("p") === "quarterly" ? "quarterly" : "yearly";
  const sec = (SECTIONS.find(([id]) => id === params.get("t"))?.[0] || "snapshot") as Sec;
  const [text, setText] = useState(company), [open, setOpen] = useState(false), [active, setActive] = useState(0);
  const [recent, setRecent] = useState<string[]>(readRecent);
  const box = useRef<HTMLInputElement>(null); useSlashFocus(box);
  const universe = useUniverse();
  const sug = useMemo(() => {
    const t = text.trim().toLowerCase(); if (!t || t === company.toLowerCase()) return [];
    const rows = universe.data?.rows || [];
    return [...rows.filter((r) => r.symbol.toLowerCase().startsWith(t)), ...rows.filter((r) => !r.symbol.toLowerCase().startsWith(t) && (r.name || "").toLowerCase().includes(t))].slice(0, 8);
  }, [text, company, universe.data]);
  const set = (o: Record<string, string>) => { const n = new URLSearchParams(params); for (const [k, v] of Object.entries(o)) v ? n.set(k, v) : n.delete(k); setParams(n, { replace: true }); };
  const choose = (sym: string) => { setText(sym); set({ c: sym }); setOpen(false); setActive(0); };
  const { data, isLoading, isError, error, refetch, isFetching } = usePremium<Fund>(`/fundamentals${qs({ query: company, statement_type: statement, period })}`, gold && company.length >= 2);
  useEffect(() => { const s = data?.instrument?.symbol; if (s) { pushRecent(s); setRecent(readRecent()); } }, [data?.instrument?.symbol]);
  const stored = useSection<Financials>((data?.instrument?.symbol || "").toUpperCase(), "financials", !!data?.instrument?.symbol).data;
  if (!gold) return <><PremiumHead eyebrow="Gold dashboard" title="Stock Fundamental Data Dashboard" /><GoldLock title="Stock Fundamental Data Dashboard" /></>;
  const limit = period === "quarterly" ? 10 : 8;
  const status = (error as { status?: number } | null)?.status;
  const sym = data?.instrument?.symbol || company;
  const quarterly = period === "quarterly", unitNote = "₹ crore, from FinLit's stored statements";
  const gateIncome = data?.incomeStatement?.income_statement || [], gateBalance = data?.balanceSheet?.balance_sheet || [], gateCash = data?.cashFlow?.cash_flow || [];
  return (
    <>
      <PremiumHead eyebrow="Gold dashboard" title="Stock Fundamental Data Dashboard"><p>Search any listed company for its full statements, ratios and named shareholders. Press <kbd>/</kbd> to search. <Link to="/premium">All Gold dashboards</Link></p></PremiumHead>
      <div className="wrap" style={{ paddingBottom: 56 }}>
        <div className="pm-bar" style={{ alignItems: "center" }}>
          <div className="pm-search" style={{ flex: 1, minWidth: 260 }}><Icon name="search" />
            <input ref={box} value={text} onChange={(e) => { setText(e.target.value); setOpen(true); setActive(0); }} onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown" && sug.length) { e.preventDefault(); setActive((active + 1) % sug.length); }
                else if (e.key === "ArrowUp" && sug.length) { e.preventDefault(); setActive((active - 1 + sug.length) % sug.length); }
                else if (e.key === "Escape") setOpen(false);
                else if (e.key === "Enter" && text.trim().length >= 2) choose(sug[active]?.symbol || text.trim().toUpperCase());
              }}
              placeholder="Search a company or symbol, for example RELIANCE" aria-label="Search a company" role="combobox" aria-expanded={open && sug.length > 0} aria-controls="pm-sug" aria-autocomplete="list"
              aria-activedescendant={open && sug[active] ? `pm-o-${sug[active].symbol}` : undefined} />
            {open && sug.length > 0 && <div className="pm-sug" id="pm-sug" role="listbox">{sug.map((r, i) => <button key={r.symbol} id={`pm-o-${r.symbol}`} role="option" aria-selected={i === active} className={i === active ? "on" : ""} onMouseDown={(e) => e.preventDefault()} onClick={() => choose(r.symbol)}><b>{r.symbol}</b><small>{r.name}</small><small style={{ marginLeft: "auto" }}>{r.sector || ""}</small></button>)}</div>}</div>
          <div className="pm-seg" role="group" aria-label="Statement type">{(["consolidated", "standalone"] as const).map((s) => <button key={s} aria-pressed={statement === s} onClick={() => set({ s: s === "consolidated" ? "" : s })}>{s === "consolidated" ? "Consolidated" : "Standalone"}</button>)}</div>
          <div className="pm-seg" role="group" aria-label="Period">{(["yearly", "quarterly"] as const).map((s) => <button key={s} aria-pressed={period === s} onClick={() => set({ p: s === "yearly" ? "" : s })}>{s === "yearly" ? "Yearly" : "Quarterly"}</button>)}</div>
        </div>
        {recent.length > 0 && <div className="pm-recent" aria-label="Recently viewed"><span className="faint">Recent</span>{recent.map((s) => <button key={s} className={"fchip" + (s === sym ? " on" : "")} onClick={() => choose(s)}>{s}</button>)}</div>}
        {!company ? (
          <div className="pm-empty"><b>Pick a company to begin.</b><p>Try {["RELIANCE", "TCS", "HDFCBANK"].map((s, i) => <span key={s}>{i ? ", " : ""}<button className="alx-link" onClick={() => choose(s)}>{s}</button></span>)}.</p></div>
        ) : isError ? (
          <div className="state"><h2>{status === 404 ? "We could not find that company" : "This company's data is not available right now"}</h2><p>{status === 404 ? "Check the symbol and try again." : "The data provider did not answer. Please try again in a moment."}</p>{status !== 404 && <button className="btn" onClick={() => refetch()}>Try again</button>}</div>
        ) : isLoading || !data ? (
          <div aria-busy="true" aria-label="Loading company data"><div className="pm-cards">{Array.from({ length: 6 }, (_, i) => <div key={i} className="skeleton" style={{ height: 96 }} />)}</div><div className="skeleton" style={{ height: 300 }} /></div>
        ) : (
          <>
            <div className="pm-co card">
              <span className="av" aria-hidden="true">{(data.instrument?.name || sym).slice(0, 2).toUpperCase()}</span>
              <div><h2>{data.instrument?.name || sym}</h2><p className="faint">{sym} · {data.statementType === "standalone" ? "Standalone" : "Consolidated"} · {period === "quarterly" ? "Quarterly" : "Yearly"} figures{data.generatedAt ? " · Updated " + dateIN(data.generatedAt) : ""}{isFetching ? " · refreshing…" : ""}</p></div>
              {data.quote?.price ? <div className="pm-px"><b>₹{nf(data.quote.price)}</b>{typeof data.quote.changePct === "number" && <span style={{ color: data.quote.changePct >= 0 ? "var(--gain)" : "var(--loss)" }}>{signed(data.quote.changePct)}</span>}</div> : null}
              <div className="pm-co-a"><Link className="btn" to={`/stocks/${sym}`}><Icon name="search" /> Research page</Link><Link className="btn" to={`/premium/report/${sym}`}><Icon name="notes" /> Premium report</Link></div>
            </div>
            <div className="pm-tabs" role="tablist" aria-label="Sections">{SECTIONS.map(([id, label]) => <button key={id} role="tab" aria-selected={sec === id} onClick={() => set({ t: id === "snapshot" ? "" : id })}>{label}</button>)}</div>
            {sec === "snapshot" && <Snapshot d={data} limit={limit} />}
            {sec === "income" && <Statement rows={gateIncome.length ? gateIncome : storedRows(stored, "income", quarterly)} limit={limit} unit={gateIncome.length ? data.incomeStatement?.units_in : unitNote} file={`${sym}-income-${period}`} />}
            {sec === "balance" && <Statement rows={gateBalance.length ? gateBalance : storedRows(stored, "balance", quarterly)} limit={limit} unit={gateBalance.length ? data.balanceSheet?.units_in : unitNote} file={`${sym}-balance-${period}`} />}
            {sec === "cash" && <Statement rows={gateCash.length ? gateCash : storedRows(stored, "cash", quarterly)} limit={limit} unit={gateCash.length ? data.cashFlow?.units_in : unitNote} file={`${sym}-cashflow-${period}`} />}
            {sec === "ratios" && <Ratios d={data} limit={limit} />}
            {sec === "owners" && <Owners d={data} limit={limit} />}
            {sec === "peers" && (<>
              <h2 className="pm-h2">Peers</h2>
              {(data.competitors || []).length ? <div className="pm-peers">{data.competitors!.map((c, i) => <button key={i} className="pm-peer" onClick={() => c.symbol && choose(c.symbol)} disabled={!c.symbol}><span className="av mini" aria-hidden="true">{(c.name || c.symbol || "?").slice(0, 2).toUpperCase()}</span><span><b>{c.symbol || MINUS}</b><small>{c.name}</small><small className="faint">{c.sector}</small></span><Icon name="arrow" /></button>)}</div> : <div className="pm-empty">No peers were reported.</div>}
              <div className="pm-sec"><h2>Dividends and corporate actions</h2>
                {(data.corporateActions || []).length ? <HScroll className="" label="table"><table className="pm-t"><thead><tr><th>Type</th><th>Detail</th><th>Ex-date</th><th className="n">Amount / ratio</th></tr></thead><tbody>{data.corporateActions!.slice(0, 40).map((a, i) => <tr key={i}><td><span className={"chip " + (/divid/i.test(a.type || "") ? "up" : "info")}>{a.type || MINUS}</span></td><td className="wrapc">{a.name || a.purpose || MINUS}</td><td>{a.ex_date ? dateIN(String(a.ex_date).slice(0, 10)) : MINUS}</td><td className="n">{a.amount != null && a.amount !== "" ? "₹" + val(Number(a.amount)) : a.ratio || MINUS}</td></tr>)}</tbody></table></HScroll> : <div className="pm-empty">No corporate actions were reported.</div>}</div></>)}
            <p className="pm-meta" style={{ marginTop: 22 }}>Figures come from company filings through FinEdge. Missing values show a dash. General information, not investment advice.</p>
          </>)}
      </div>
    </>
  );
}
