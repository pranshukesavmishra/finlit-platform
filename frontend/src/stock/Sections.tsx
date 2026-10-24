import { HScroll } from "../components/HScroll";
import { useContext, useMemo, useState } from "react";
import { fromYears, priceFrom } from "../lib/chartAxis";
import { Icon } from "../lib/icons";
import { Gate, OpenAccess, TierChip } from "../components/Gate";
import { Info } from "../components/Info";
import { PriceChart } from "../charts/PriceChart";
import { IntradayChart } from "../charts/IntradayChart";
import { FinChart, type FinKind } from "../charts/FinChart";
import { RsiGauge, Spark } from "../charts/Small";
import { ChartHelp } from "../components/ChartHelp";
import { MINUS, cr, dateIN, nf, signed } from "../lib/format";
import { useIsFetching } from "@tanstack/react-query";
import { useBasis, setBasis } from "../lib/basis";
import { useIntraday, usePrice, type ApiError, type Financials, type Intraday, type IntradayRange, type Ratios, type Summary, type Table } from "../lib/api";
import { barSpan, changePct, istDay, status as intradayStatus } from "../lib/intraday";
import { useAuth } from "../lib/auth";
import { finTiles, yoy } from "./derive";
import { PL_INFO, PL_LABEL, plCell } from "./plDefinitions";
import { useUI, type Plan } from "../lib/ui";
import { Plain } from "../components/Plain";

const css = (v: string) => `var(${v})`;
export function SectionHead({ id, no, icon, tier, title, sub, color }: { id: string; no: string; icon: string; tier?: "basic" | "silver" | "gold"; title: string; sub?: string; color: string }) {
  return (
    <div className="sh" id={id} style={{ "--sc": `var(${color})` } as React.CSSProperties}>
      <div className="sh-l"><div className="sh-ic"><Icon name={icon} /></div><div><div className="no">{no} {tier && <TierChip tier={tier} />}</div><h2>{title}</h2></div></div>
      {sub && <p className="hide-sm">{sub}</p>}
    </div>
  );
}

/* ---------------- Notes ---------------- */
export function Notes({ s }: { s: Summary }) {
  const list = (items: Summary["strengths"]) => (
    <ul>{items.length ? items.map((n, i) => <li key={n.key}><span className="n">{i + 1}</span><span><b>{n.title}</b>: {n.text}</span></li>) : <li><span className="n">–</span><span className="muted">Nothing stands out.</span></li>}</ul>
  );
  return (
    <section className="block" style={{ "--sc": "var(--p-quality)" } as React.CSSProperties}>
      <SectionHead id="notes" no="02 · Scorecard notes" icon="notes" tier="silver" title="What the numbers say" sub="Plain-language findings from the statements, ratios and price history." color="--p-quality" />
      <Gate tier="silver" title="See the full scorecard notes" points={["Strengths and watch-outs in plain English", "What drives each pillar score", "Updated with every result"]}>
        <div className="grid g2">
          <div className="card acc note hover-lift" style={{ "--ac": "var(--p-quality)" } as React.CSSProperties}><div className="card-h"><h3><span className="ci"><Icon name="check" /></span>Strengths</h3><span className="chip up">{s.strengths.length}</span></div>{list(s.strengths)}</div>
          <div className="card acc note hover-lift" style={{ "--ac": "var(--p-tech)" } as React.CSSProperties}><div className="card-h"><h3><span className="ci"><Icon name="alert" /></span>Watch-outs</h3><span className="chip down">{s.watchouts.length}</span></div>{list(s.watchouts)}</div>
        </div>
      </Gate>
    </section>
  );
}

/* ---------------- Price & technicals ---------------- */
const RANGES = ["1M", "6M", "1Y", "3Y", "5Y", "MAX"];
/** Intraday ranges (Dhan) and the plan each needs; every one needs a signed-in account, except on the free example company. */
const INTRA: [IntradayRange, Plan][] = [["1D", "basic"], ["5D", "silver"], ["1M", "silver"]];
const CAP: React.CSSProperties = { fontSize: 11, padding: "0 6px 0 8px", alignSelf: "center", whiteSpace: "nowrap" };
export function PriceSection({ s, symbol, ratios }: { s: Summary; symbol: string; ratios?: Ratios }) {
  const [range, setRange] = useState("1Y"), [from, setFrom] = useState<number | undefined>();
  const [intra, setIntra] = useState<IntradayRange | null>(null);
  const [ind, setInd] = useState({ e50: true, e200: false, vol: true });
  const { has, upgrade } = useUI();
  const { user } = useAuth();
  const open = useContext(OpenAccess);
  const mayIntra = (tier: Plan) => open || (!!user && has(tier));
  const { data: full, isLoading, isError } = usePrice(symbol, from ? "MAX" : range);
  const iq = useIntraday(symbol, intra ?? "1D", !!intra);
  const idata = intra && iq.data?.range === intra ? iq.data : undefined;
  const data = useMemo(() => (full ? priceFrom(full, from) : full), [full, from]);
  const t = data?.technical, series = data?.series, c = series?.c || [];
  const chg = intra ? (idata?.series ? changePct(idata) : null) : c.length > 1 ? (c[c.length - 1] / c[0] - 1) * 100 : null;
  const gold = has("gold"), e = (k: string, on: boolean) => gold ? on : k === "e50" ? true : k === "vol";
  const pickIntra = (r: IntradayRange, tier: Plan) => {
    if (mayIntra(tier)) { setIntra(r); setFrom(undefined); return; }
    upgrade(tier, tier === "basic" ? "Intraday charts come with a free account." : "The 5D and 1M intraday charts are part of Silver.");
  };
  return (
    <section className="block" style={{ "--sc": "var(--p-tech)" } as React.CSSProperties}>
      <SectionHead id="price" no="03 · Price & technicals" icon="line" tier="basic" title="How the stock has traded" sub="Intraday bars from Dhan for 1D, 5D and 1M; daily closes up to one year, weekly closes beyond. Hover the chart for detail." color="--p-tech" />
      {intra && idata?.series && chg != null && <Plain tone={chg >= 0 ? "good" : "warn"}>Since the open {idata.sessions.length > 1 ? "of " + istDay(idata.sessions[0]) : "on " + istDay(idata.session ?? "")}, the price {chg >= 0 ? "rose" : "fell"} {nf(Math.abs(chg), 2)}%.</Plain>}
      {!intra && chg != null && <Plain tone={chg >= 0 ? "good" : "warn"}>Over this period the price {chg >= 0 ? "rose" : "fell"} {nf(Math.abs(chg), 1)}%.{t?.vsEma200Pct != null && <> It trades {nf(Math.abs(t.vsEma200Pct), 1)}% {t.vsEma200Pct < 0 ? "below" : "above"} its 200-day average, which {t.vsEma200Pct < 0 ? "suggests the longer trend is weak" : "suggests the longer trend is healthy"}.</>}</Plain>}
      <div className="grid g3">
        <div className="card acc span2" style={{ "--ac": "var(--p-tech)" } as React.CSSProperties}>
          <div className="stats">
            {[["52W high", s.range52.high == null ? "—" : "₹" + nf(s.range52.high)], ["52W low", s.range52.low == null ? "—" : "₹" + nf(s.range52.low)], [intra ? "Since the open" : "Range change", chg == null ? "—" : signed(chg)], ["vs 200-day average", t?.vsEma200Pct == null ? "—" : signed(t.vsEma200Pct)]].map(([k, v]) => <div className="stat" key={k}><div className="k">{k}</div><div className={"v " + (k === "Range change" || k === "Since the open" || k.startsWith("vs") ? (v.includes("▼") ? "neg" : v.includes("▲") ? "pos" : "") : "")}>{v}</div></div>)}
          </div>
          <div className="tools">
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, minWidth: 0, maxWidth: "100%" }}>
              <div className="seg" role="group" aria-label="Intraday range"><span className="faint" style={CAP}>Intraday</span>{INTRA.map(([r, tier]) => { const ok = mayIntra(tier); return <button key={r} aria-pressed={intra === r} aria-label={ok ? `${r} intraday` : `${r} intraday (${tier === "basic" ? "sign in" : "Silver plan"})`} onClick={() => pickIntra(r, tier)}>{!ok && <Icon name="lock" />}{r}</button>; })}</div>
              <div className="seg" role="group" aria-label="Range"><span className="faint" style={CAP}>Daily</span>{RANGES.map((r) => <button key={r} aria-pressed={!intra && !from && range === r} onClick={() => { setRange(r); setFrom(undefined); setIntra(null); }}>{r}</button>)}</div>
              <label className="faint" style={{ fontSize: 12 }}>From year <select aria-label="From year" value={intra ? "" : from ?? ""} onChange={(e) => { setFrom(e.target.value ? Number(e.target.value) : undefined); setIntra(null); }}><option value="">Any</option>{fromYears().map((y) => <option key={y} value={y}>{y}</option>)}</select></label><ChartHelp id="price-section" /></div>
            {gold ? <div className="seg" role="group" aria-label="Indicators">
              {!intra && <><button aria-pressed={ind.e50} onClick={() => setInd((x) => ({ ...x, e50: !x.e50 }))}>EMA 50</button><button aria-pressed={ind.e200} onClick={() => setInd((x) => ({ ...x, e200: !x.e200 }))}>EMA 200</button></>}<button aria-pressed={ind.vol} onClick={() => setInd((x) => ({ ...x, vol: !x.vol }))}>Volume</button></div>
              : <span className="tier gold" style={{ cursor: "pointer" }} onClick={() => upgrade("gold", "More indicators come with Gold.")}>More indicators in Gold</span>}
          </div>
          {intra ? <IntradayBody q={iq} data={idata} showVol={e("vol", ind.vol)} chg={chg} /> : <>
          {isLoading && <div className="skeleton" style={{ height: 340 }} />}
          {isError && <p className="muted">Price history is unavailable right now.</p>}
          {data && series && c.length > 1 && <PriceChart data={data} showEma50={e("e50", ind.e50)} showEma200={e("e200", ind.e200)} showVol={e("vol", ind.vol)} />}
          {data && !data.complete && <p className="faint" style={{ fontSize: 12, margin: "10px 0 0" }}>History for this company starts {data.startsAt ? dateIN(data.startsAt, { month: "short", year: "numeric" }) : "later"}, so this range is shorter than {range}.</p>}
          {data && <div className="legend"><span className={"chip " + ((chg ?? 0) >= 0 ? "up" : "down")}>{signed(chg)} over the period</span><span><i className="ln" style={{ background: "var(--line)" }} />Close</span>{e("e50", ind.e50) && <span><i className="ln" style={{ background: "var(--c2)" }} />EMA 50</span>}{e("e200", ind.e200) && <span><i className="ln" style={{ background: "var(--c3)" }} />EMA 200</span>}{e("vol", ind.vol) && <span><i style={{ background: "var(--c4)", opacity: 0.6 }} />Volume</span>}{data.provisionalLastBar && <span className="faint">Latest bar is the live quote</span>}</div>}
          </>}
        </div>
        <Gate tier="gold" title="Advanced technical score" points={["RSI momentum gauge and trend signals", "Price vs 50- and 200-day averages", "Returns across every holding period"]}>
          <div className="card acc" style={{ "--ac": "var(--p-tech)", height: "100%" } as React.CSSProperties}>
            <div className="card-h"><h3><span className="ci"><Icon name="activity" /></span>Momentum<ChartHelp id="momentum" /></h3><TierChip tier="gold" /></div>
            {t?.rsi14 != null && <RsiGauge value={t.rsi14} />}
            <div className="mrow" style={{ marginTop: 6 }}><span className="k">What is RSI? <Info g={ratios?.glossary.rsi14} /></span><span className="v faint" style={{ fontWeight: 400, fontSize: 13 }}>0 to 100 scale</span></div>
            <div className="mrow"><span className="k">vs 50-day average</span><span className={"v " + ((t?.vsEma50Pct ?? 0) < 0 ? "neg" : "pos")}>{signed(t?.vsEma50Pct)}</span></div>
            <div className="mrow"><span className="k">vs 200-day average</span><span className={"v " + ((t?.vsEma200Pct ?? 0) < 0 ? "neg" : "pos")}>{signed(t?.vsEma200Pct)}</span></div>
            <div className="label" style={{ margin: "16px 0 6px" }}>Total return (price + dividends)</div>
            <ReturnBars rows={s.returns} />
          </div>
        </Gate>
      </div>
    </section>
  );
}

/** The intraday chart with what it shows (session, source, as-of time), or why it cannot be shown. */
function IntradayBody({ q, data, showVol, chg }: { q: { isPending: boolean; isError: boolean; error: ApiError | null }; data?: Intraday; showVol: boolean; chg: number | null }) {
  if (!data && q.isError) return <p className="muted">{q.error?.body.detail || "Intraday prices are unavailable right now."}</p>;
  if (!data) return <div className="skeleton" style={{ height: 340 }} />;
  const st = intradayStatus(data), sr = data.series, n = sr?.t.length ?? 0;
  return (
    <>
      <div className="faint" style={{ fontSize: 12, margin: "0 0 10px", display: "flex", flexWrap: "wrap", gap: "2px 12px" }}><b style={{ color: "var(--text)", fontWeight: 600 }}>{st.title}</b><span>{st.asOf}</span></div>
      {st.note && <p className={data.stale ? "neg" : "faint"} style={{ fontSize: 12, margin: "0 0 10px" }}>{st.note}</p>}
      {!data.available && <p className="muted">{data.detail || "No recent trades."}</p>}
      {sr && n > 1 && <IntradayChart data={data} showVol={showVol} />}
      {sr && n === 1 && <p className="muted">One price bar so far in this session: ₹{nf(sr.c[0])}, {barSpan(sr.t[0], data.interval)} IST.</p>}
      {sr && n > 0 && <div className="legend"><span className={"chip " + ((chg ?? 0) >= 0 ? "up" : "down")}>{signed(chg)} since the open</span><span><i className="ln" style={{ background: "var(--line)" }} />Close</span>{showVol && <span><i style={{ background: "var(--c4)", opacity: 0.6 }} />Volume</span>}<span className="faint">Times are Indian (IST)</span></div>}
    </>
  );
}

function ReturnBars({ rows }: { rows: Summary["returns"] }) {
  const have = rows.filter((r) => r.total != null);
  const max = Math.max(...have.map((r) => Math.abs(r.total as number)), 1);
  return (
    <div>
      {rows.map((r) => (
        <div className="rrow" key={r.period}><span className="muted">{r.period}</span>
          <div className="rtrack">{r.total != null && <b style={r.total >= 0 ? { left: "50%", width: `${(Math.abs(r.total) / max) * 50}%`, background: "linear-gradient(90deg,color-mix(in srgb,var(--gain) 45%,transparent),var(--gain))" } : { right: "50%", width: `${(Math.abs(r.total) / max) * 50}%`, background: "linear-gradient(270deg,color-mix(in srgb,var(--loss) 45%,transparent),var(--loss))" }} />}</div>
          <span className={r.total == null ? "faint" : r.total >= 0 ? "pos" : "neg"} style={{ textAlign: "right", fontWeight: 600, whiteSpace: "nowrap" }}>{r.total == null ? "n/a" : signed(r.total)}</span></div>
      ))}
      <p className="faint" style={{ fontSize: 12, margin: "10px 0 0" }}>“n/a” means this company's price history does not cover that period.</p>
    </div>
  );
}

/* ---------------- Standalone / consolidated ---------------- */
/** Consolidated = the company and everything it owns; standalone = the parent company alone. Chosen per company; every section follows it. */
export function BasisToggle({ symbol, shown }: { symbol: string; shown?: "consolidated" | "standalone" }) {
  const b = useBasis(symbol), busy = useIsFetching({ queryKey: ["stock", symbol.toUpperCase()] }) > 0;
  return (
    <span className="seg basis" role="group" aria-label="Which accounts to show">
      {([["consolidated", "Consolidated"], ["standalone", "Standalone"]] as const).map(([k, l]) => (
        <button key={k} type="button" aria-pressed={b === k} onClick={() => setBasis(symbol, k)} title={k === "consolidated" ? "The company and all it owns, added up" : "The parent company alone"}>{l}</button>
      ))}
      {busy && <em className="faint" style={{ fontSize: 11.5, marginLeft: 8 }}>Loading…</em>}
      {shown && shown !== b && <em className="faint" style={{ fontSize: 11.5, marginLeft: 8 }}>This company publishes {shown} accounts only.</em>}
    </span>
  );
}

/* ---------------- Financials ---------------- */
export function FinancialsSection({ f }: { f?: Financials }) {
  const [kind, setKind] = useState<FinKind>("pl");
  const basis = useBasis(f?.meta.symbol ?? "");
  if (!f) return <section className="block"><SectionHead id="financials" no="05 · Financials" icon="bars" tier="basic" title="Results over the years" color="--p-growth" /><div className="skeleton" style={{ height: 380 }} /></section>;
  const tiles = finTiles(f), tbl: Table = kind === "q" ? f.quarterly.pl : f.yearly[kind];
  const ROWS: Record<string, [string, string, boolean?][]> = {
    pl: [["revenue", "Revenue"], ["other_income", "Other income"], ["expenses", "Expenses"], ["operating_profit", "Operating profit", true], ["finance_costs", "Interest"], ["depreciation", "Depreciation"], ["profit_before_tax", "Profit before tax", true], ["tax", "Tax"], ["net_profit", "Net profit", true], ["eps", "EPS (₹)"]],
    bs: [["equity_capital", "Equity capital"], ["reserves", "Reserves"], ["total_equity", "Total equity", true], ["borrowings", "Borrowings"], ["other_liabilities", "Other liabilities"], ["total_liabilities", "Total liabilities", true], ["fixed_assets", "Fixed assets"], ["cwip", "Capital WIP"], ["investments", "Investments"], ["inventories", "Inventories"], ["receivables", "Receivables"], ["cash", "Cash"], ["total_assets", "Total assets", true]],
    cf: [["operating", "Cash from operations"], ["investing", "Cash from investing"], ["financing", "Cash from financing"], ["net_cash_flow", "Net cash flow", true], ["capex", "Capital expenditure"], ["free_cash_flow", "Free cash flow", true], ["dividends_paid", "Dividends paid"]],
  };
  const rows = ROWS[kind === "q" ? "pl" : kind].filter(([k]) => tbl.rows[k]);
  const last = tbl.periods.length - 1;
  return (
    <section className="block" style={{ "--sc": "var(--p-growth)" } as React.CSSProperties}>
      <SectionHead id="financials" no="05 · Financials" icon="bars" tier="basic" title="Results over the years" sub={`${f.meta.statement === "consolidated" ? "Consolidated" : "Standalone"}, ₹ crore. L Cr = lakh crore. FY = April–March.`} color="--p-growth" />
      {(() => { const [rv, np, , mg] = tiles; return rv.delta != null && np.delta != null ? <Plain tone={np.delta >= 0 ? "good" : "warn"}>Sales {rv.delta >= 0 ? "grew" : "fell"} {nf(Math.abs(rv.delta), 1)}% last year and profit {np.delta >= 0 ? "rose" : "fell"} {nf(Math.abs(np.delta), 1)}%.{typeof mg.value === "number" && <> Out of every ₹100 of sales, about ₹{nf(mg.value, 1)} is kept as profit.</>}</Plain> : null; })()}
      <div className="grid g4" style={{ marginBottom: 16 }}>
        {tiles.map((t) => (
          <div className="ftile hover-lift" key={t.k} style={{ "--fc": css(t.color) } as React.CSSProperties}>
            <div className="k"><Icon name={t.icon} />{t.k} · {t.fy}</div>
            <div className="v">{t.value == null ? "—" : t.unit === "cr" ? "₹" + cr(t.value) + (Math.abs(t.value) >= 100000 ? " Cr" : " Cr") : nf(t.value) + "%"}</div>
            <div className="row"><span className={"chip " + ((t.delta ?? 0) >= 0 ? "up" : "down")}>{t.delta == null ? "—" : signed(t.delta, 1, t.suffix)} YoY</span><Spark values={t.series} color={`var(${t.color})`} w={96} h={34} /></div>
          </div>
        ))}
      </div>
      {f.yearly.pl.periods.length > 0 && f.yearly.pl.periods.length <= 3 && <p className="faint" style={{ fontSize: 12.5, margin: "0 0 10px" }}>Our data provider holds only {f.yearly.pl.periods.length} year{f.yearly.pl.periods.length === 1 ? "" : "s"} of {basis} statements for this company (it may be newly listed, or have started publishing these accounts recently). The Consolidated / Standalone switch above shows the other set.</p>}
      <div className="card acc" style={{ "--ac": "var(--p-growth)" } as React.CSSProperties}>
        <div className="tools">
          <BasisToggle symbol={f.meta.symbol} shown={f.meta.statement} />
          <div className="seg" role="group" aria-label="Statement">{([["pl", "Profit & loss"], ["bs", "Balance sheet"], ["cf", "Cash flow"], ["q", "Quarterly"]] as const).map(([k, l]) => <button key={k} aria-pressed={kind === k} onClick={() => setKind(k)}>{l}</button>)}</div>
          <span className="chip ghost">{tbl.periods[0]} – {tbl.periods[last]}</span>
        </div>
        <FinChart kind={kind} pl={f.yearly.pl} bs={f.yearly.bs} cf={f.yearly.cf} ql={f.quarterly.pl} />
        <div className="legend">{kind === "pl" || kind === "q" ? <><span><i style={{ background: "var(--c2)" }} />Revenue</span><span><i style={{ background: "var(--c3)" }} />Net profit</span><span><i className="ln" style={{ background: "var(--c4)" }} />Net margin</span><span><i style={{ background: "var(--c1)" }} />Latest period</span></>
          : kind === "bs" ? <><span><i style={{ background: "var(--c1)" }} />Equity + reserves</span><span><i style={{ background: "var(--c2)" }} />Borrowings</span><span><i style={{ background: "var(--c4)" }} />Other liabilities</span></>
            : <><span><i style={{ background: "var(--c3)" }} />Operating</span><span><i style={{ background: "var(--c2)" }} />Investing</span><span><i style={{ background: "var(--c4)" }} />Financing</span><span><i className="ln" style={{ background: "var(--c1)" }} />Free cash flow</span></>}</div>
        <div style={{ marginTop: 24 }}><HScroll className="" label="table"><table>
          <thead><tr><th>₹ Cr</th>{tbl.periods.map((p, i) => <th key={p} className={i === last ? "latest" : ""}>{p}</th>)}{kind === "q" ? <><th>vs last qtr</th><th>vs year ago</th></> : kind !== "cf" && <th>vs last year</th>}<th>Trend</th></tr></thead>
          <tbody>{rows.map(([k, label, tot]) => { const v = tbl.rows[k], y = yoy(v), y4 = kind === "q" ? yoy(v, 4) : null; const cell = (g: number | null) => <td className={g == null ? "" : g >= 0 ? "pos" : "neg"}>{g == null ? "—" : signed(g, 1)}</td>; return (
            <tr key={k} className={tot ? "tot" : ""} data-row-key={k}><td>{kind === "bs" || kind === "cf" ? label : (PL_LABEL[k] ?? label)}{(kind === "pl" || kind === "q") && PL_INFO[k] && <> <Info g={PL_INFO[k]} /></>}</td>{v.map((x, i) => <td key={i} className={i === last ? "latest" : ""}>{plCell(k, x)}</td>)}{kind === "q" ? <>{cell(y)}{cell(y4)}</> : kind !== "cf" && cell(y)}<td><Spark values={v} color="var(--muted)" w={76} h={24} /></td></tr>); })}</tbody>
        </table></HScroll></div>
      </div>
    </section>
  );
}

void MINUS;
