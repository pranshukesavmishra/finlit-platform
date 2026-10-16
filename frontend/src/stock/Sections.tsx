import { useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Icon } from "../lib/icons";
import { Gate, TierChip } from "../components/Gate";
import { Info } from "../components/Info";
import { PriceChart } from "../charts/PriceChart";
import { FinChart, type FinKind } from "../charts/FinChart";
import { RsiGauge, Spark } from "../charts/Small";
import { MINUS, cr, dateIN, fmtUnit, initials, nf, pct, signed } from "../lib/format";
import { prefetchStock, usePrice, type Financials, type Peers, type Ratios, type Segments, type Summary, type Table } from "../lib/api";
import { buckets, finTiles, yoy } from "./derive";
import { useUI } from "../lib/ui";
import { SegmentCard } from "./Sections2";
import { Plain } from "../components/Plain";

const css = (v: string) => `var(${v})`;
export function SectionHead({ id, no, icon, tier, title, sub, color }: { id: string; no: string; icon: string; tier?: "basic" | "bronze" | "gold"; title: string; sub?: string; color: string }) {
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
      <SectionHead id="notes" no="01 · Scorecard notes" icon="notes" tier="bronze" title="What the numbers say" sub="Plain-language findings from the statements, ratios and price history." color="--p-quality" />
      <Gate tier="bronze" title="See the full scorecard notes" points={["Strengths and watch-outs in plain English", "What drives each pillar score", "Updated with every result"]}>
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
export function PriceSection({ s, symbol, ratios }: { s: Summary; symbol: string; ratios?: Ratios }) {
  const [range, setRange] = useState("1Y");
  const [ind, setInd] = useState({ e50: true, e200: false, vol: true });
  const { has, setPlan } = useUI();
  const { data, isLoading, isError } = usePrice(symbol, range);
  const t = data?.technical, series = data?.series, c = series?.c || [];
  const chg = c.length > 1 ? (c[c.length - 1] / c[0] - 1) * 100 : null;
  const gold = has("gold"), e = (k: string, on: boolean) => gold ? on : k === "e50" ? true : k === "vol";
  return (
    <section className="block" style={{ "--sc": "var(--p-tech)" } as React.CSSProperties}>
      <SectionHead id="price" no="02 · Price & technicals" icon="line" tier="basic" title="How the stock has traded" sub="Daily closes up to one year, weekly closes beyond. Hover the chart for detail." color="--p-tech" />
      {chg != null && <Plain tone={chg >= 0 ? "good" : "warn"}>Over this period the price {chg >= 0 ? "rose" : "fell"} {nf(Math.abs(chg), 1)}%.{t?.vsEma200Pct != null && <> It trades {nf(Math.abs(t.vsEma200Pct), 1)}% {t.vsEma200Pct < 0 ? "below" : "above"} its 200-day average, which {t.vsEma200Pct < 0 ? "suggests the longer trend is weak" : "suggests the longer trend is healthy"}.</>}</Plain>}
      <div className="grid g3">
        <div className="card acc span2" style={{ "--ac": "var(--p-tech)" } as React.CSSProperties}>
          <div className="stats">
            {[["52W high", "₹" + nf(s.range52.high ?? 0)], ["52W low", "₹" + nf(s.range52.low ?? 0)], ["Range change", chg == null ? "—" : signed(chg)], ["vs 200-day average", t?.vsEma200Pct == null ? "—" : signed(t.vsEma200Pct)]].map(([k, v]) => <div className="stat" key={k}><div className="k">{k}</div><div className={"v " + (k === "Range change" || k.startsWith("vs") ? (v.includes("▼") ? "neg" : v.includes("▲") ? "pos" : "") : "")}>{v}</div></div>)}
          </div>
          <div className="tools">
            <div className="seg" role="group" aria-label="Range">{RANGES.map((r) => <button key={r} aria-pressed={range === r} onClick={() => setRange(r)}>{r}</button>)}</div>
            {gold ? <div className="seg" role="group" aria-label="Indicators">
              <button aria-pressed={ind.e50} onClick={() => setInd((x) => ({ ...x, e50: !x.e50 }))}>EMA 50</button><button aria-pressed={ind.e200} onClick={() => setInd((x) => ({ ...x, e200: !x.e200 }))}>EMA 200</button><button aria-pressed={ind.vol} onClick={() => setInd((x) => ({ ...x, vol: !x.vol }))}>Volume</button></div>
              : <span className="tier gold" style={{ cursor: "pointer" }} onClick={() => setPlan("gold")}>More indicators in Gold</span>}
          </div>
          {isLoading && <div className="skeleton" style={{ height: 340 }} />}
          {isError && <p className="muted">Price history is unavailable right now.</p>}
          {data && series && c.length > 1 && <PriceChart data={data} showEma50={e("e50", ind.e50)} showEma200={e("e200", ind.e200)} showVol={e("vol", ind.vol)} />}
          {data && !data.complete && <p className="faint" style={{ fontSize: 12, margin: "10px 0 0" }}>History for this company starts {data.startsAt ? dateIN(data.startsAt, { month: "short", year: "numeric" }) : "later"}, so this range is shorter than {range}.</p>}
          {data && <div className="legend"><span className={"chip " + ((chg ?? 0) >= 0 ? "up" : "down")}>{signed(chg)} over the period</span><span><i className="ln" style={{ background: "var(--line)" }} />Close</span>{e("e50", ind.e50) && <span><i className="ln" style={{ background: "var(--c2)" }} />EMA 50</span>}{e("e200", ind.e200) && <span><i className="ln" style={{ background: "var(--c3)" }} />EMA 200</span>}{e("vol", ind.vol) && <span><i style={{ background: "var(--c4)", opacity: 0.6 }} />Volume</span>}{data.provisionalLastBar && <span className="faint">Latest bar is the live quote</span>}</div>}
        </div>
        <Gate tier="gold" title="Advanced technical score" points={["RSI momentum gauge and trend signals", "Price vs 50- and 200-day averages", "Returns across every holding period"]}>
          <div className="card acc" style={{ "--ac": "var(--p-tech)", height: "100%" } as React.CSSProperties}>
            <div className="card-h"><h3><span className="ci"><Icon name="activity" /></span>Momentum</h3><TierChip tier="gold" /></div>
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

/* ---------------- Financials ---------------- */
export function FinancialsSection({ f }: { f?: Financials }) {
  const [kind, setKind] = useState<FinKind>("pl");
  if (!f) return <section className="block"><SectionHead id="financials" no="03 · Financials" icon="bars" tier="basic" title="Results over the years" color="--p-growth" /><div className="skeleton" style={{ height: 380 }} /></section>;
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
      <SectionHead id="financials" no="03 · Financials" icon="bars" tier="basic" title="Results over the years" sub={`${f.meta.statement === "consolidated" ? "Consolidated" : "Standalone"}, ₹ crore. L Cr = lakh crore. FY = April–March.`} color="--p-growth" />
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
      <div className="card acc" style={{ "--ac": "var(--p-growth)" } as React.CSSProperties}>
        <div className="tools">
          <div className="seg" role="tablist" aria-label="Statement">{([["pl", "Profit & loss"], ["bs", "Balance sheet"], ["cf", "Cash flow"], ["q", "Quarterly"]] as const).map(([k, l]) => <button key={k} aria-pressed={kind === k} onClick={() => setKind(k)}>{l}</button>)}</div>
          <span className="chip ghost">{tbl.periods[0]} – {tbl.periods[last]}</span>
        </div>
        <FinChart kind={kind} pl={f.yearly.pl} bs={f.yearly.bs} cf={f.yearly.cf} ql={f.quarterly.pl} />
        <div className="legend">{kind === "pl" || kind === "q" ? <><span><i style={{ background: "var(--c2)" }} />Revenue</span><span><i style={{ background: "var(--c3)" }} />Net profit</span><span><i className="ln" style={{ background: "var(--c4)" }} />Net margin</span><span><i style={{ background: "var(--c1)" }} />Latest period</span></>
          : kind === "bs" ? <><span><i style={{ background: "var(--c1)" }} />Equity + reserves</span><span><i style={{ background: "var(--c2)" }} />Borrowings</span><span><i style={{ background: "var(--c4)" }} />Other liabilities</span></>
            : <><span><i style={{ background: "var(--c3)" }} />Operating</span><span><i style={{ background: "var(--c2)" }} />Investing</span><span><i style={{ background: "var(--c4)" }} />Financing</span><span><i className="ln" style={{ background: "var(--c1)" }} />Free cash flow</span></>}</div>
        <div style={{ marginTop: 24 }}><div className="tw"><table>
          <thead><tr><th>₹ Cr</th>{tbl.periods.map((p, i) => <th key={p} className={i === last ? "latest" : ""}>{p}</th>)}{kind !== "cf" && <th>YoY</th>}<th>Trend</th></tr></thead>
          <tbody>{rows.map(([k, label, tot]) => { const v = tbl.rows[k], y = yoy(v); return (
            <tr key={k} className={tot ? "tot" : ""}><td>{label}</td>{v.map((x, i) => <td key={i} className={i === last ? "latest" : ""}>{x == null ? "—" : k === "eps" ? nf(x) : cr(x)}</td>)}{kind !== "cf" && <td className={y == null ? "" : y >= 0 ? "pos" : "neg"}>{y == null ? "—" : signed(y, 1)}</td>}<td><Spark values={v} color="var(--muted)" w={76} h={24} /></td></tr>); })}</tbody>
        </table></div></div>
      </div>
    </section>
  );
}

/* ---------------- Ratios ---------------- */
const TREND_KEYS: [string, string, string][] = [["gross_margin", "Gross margin", "--p-growth"], ["operating_margin", "Operating margin", "--p-profit"], ["net_margin", "Net margin", "--p-tech"], ["roe", "Return on equity", "--p-quality"], ["roce", "Return on capital", "--p-balance"]];
const GROUP_COLOR: Record<string, string> = { valuation: "--p-quality", returns: "--p-quality", margins: "--p-profit", growth: "--p-growth", leverage: "--p-balance", liquidity: "--p-balance", efficiency: "--p-profit", shareholder: "--gold-deep", quality: "--p-quality" };
const GROUP_ICON: Record<string, string> = { valuation: "tag", returns: "quality", margins: "profit", growth: "growth", leverage: "balance", liquidity: "balance", efficiency: "activity", shareholder: "coins", quality: "quality" };
const GOLD_GROUPS = new Set(["leverage", "liquidity", "efficiency", "quality", "shareholder"]);
const DUPES: Record<string, string> = { sales_cagr: "revenue_cagr_5y", profit_cagr: "profit_cagr_5y", npm: "net_margin", opm: "operating_margin" };

export function RatiosSection({ r }: { r?: Ratios }) {
  const { has, setPlan } = useUI();
  if (!r) return <section className="block"><SectionHead id="ratios" no="04 · Ratios" icon="gauge" tier="basic" title="Valuation, quality and safety" color="--p-profit" /><div className="skeleton" style={{ height: 300 }} /></section>;
  const hist = r.history;
  return (
    <section className="block" style={{ "--sc": "var(--p-profit)" } as React.CSSProperties}>
      <SectionHead id="ratios" no="04 · Ratios" icon="gauge" tier="basic" title="Valuation, quality and safety" sub="Latest value with its period. Select i for what it means and how to read it." color="--p-profit" />
      <Plain>Ratios turn big numbers into fair comparisons. A lower P/E means you pay less for each rupee of profit. A higher ROE means the company earns more from shareholders' money. Lower debt means more safety.</Plain>
      <Gate tier="bronze" title="Historical trend for each parameter" points={["Eight years of margins and returns", "Spot improvement or deterioration", "Median and low for every series"]}>
        <div style={{ marginBottom: 16 }}>
          <div className="label" style={{ marginBottom: 10, display: "flex", gap: 8, alignItems: "center" }}>Historical trend · {hist.periods[0]}–{hist.periods[hist.periods.length - 1]} <TierChip tier="bronze" /></div>
          <div className="grid g5">
            {TREND_KEYS.filter(([k]) => hist.rows[k]).map(([k, label, col]) => {
              const v = hist.rows[k], nn = v.filter((x): x is number => x != null), med = [...nn].sort((a, b) => a - b)[Math.floor(nn.length / 2)];
              return <div className="sm hover-lift" key={k}><div className="k">{label}</div><div className="v" style={{ color: css(col) }}>{pct(nn[nn.length - 1])}</div><div className="s">Median {nf(med)}% · low {nf(Math.min(...nn))}%</div><Spark values={v} color={css(col)} w={200} h={64} /></div>;
            })}
          </div>
        </div>
      </Gate>
      <div className="grid g3">
        {r.groups.filter((g) => g.keys.length).map((g) => {
          const keys = g.keys.filter((k) => !(DUPES[k] && r.latest[DUPES[k]]));
          const gold = GOLD_GROUPS.has(g.id) && !has("gold");
          const rows = (gold ? keys.slice(0, 2) : keys);
          return (
            <div className="card acc hover-lift" key={g.id} style={{ "--ac": css(GROUP_COLOR[g.id] || "--gold") } as React.CSSProperties}>
              <div className="card-h"><h3><span className="ci"><Icon name={GROUP_ICON[g.id] || "info"} /></span>{g.label}</h3></div>
              {rows.map((k) => { const e = r.latest[k], gl = r.glossary[k]; return (
                <div className="mrow" key={k}><span className="k">{e.label} <Info g={gl} /></span><span className="v">{fmtUnit(e.value, e.unit)}<span className="unit" style={{ marginLeft: 6, fontSize: 11 }}>{e.period === "latest" ? "" : e.period}</span></span></div>); })}
              {gold && keys.length > 2 && <div className="more-gold" role="button" tabIndex={0} onClick={() => setPlan("gold")} onKeyDown={(e) => e.key === "Enter" && setPlan("gold")}><Icon name="crown" /><span><b>+{keys.length - 2} more ratios</b> in detailed ratio analysis · Gold</span></div>}
            </div>);
        })}
      </div>
      <Gate tier="gold" title="Detailed ratio analysis" points={["Every ratio with its history", "Quality, growth, solvency and efficiency", "Full multi-year table"]}>
        <div className="card acc" style={{ marginTop: 16, "--ac": "var(--p-profit)" } as React.CSSProperties}>
          <div className="card-h"><h3><span className="ci"><Icon name="table" /></span>Ratio history</h3><TierChip tier="gold" /></div>
          <div className="tw"><table>
            <thead><tr><th>Ratio</th>{hist.periods.map((p, i) => <th key={p} className={i === hist.periods.length - 1 ? "latest" : ""}>{p}</th>)}<th>Trend</th></tr></thead>
            <tbody>{Object.entries(hist.rows).filter(([k]) => r.glossary[k]?.label).map(([k, v]) => <tr key={k}><td>{r.glossary[k].label}</td>{v.map((x, i) => <td key={i} className={i === v.length - 1 ? "latest" : ""}>{x == null ? <span className="faint">—</span> : nf(x)}</td>)}<td><Spark values={v} color="var(--muted)" w={76} h={24} /></td></tr>)}</tbody>
          </table></div>
          <ValuationHistory r={r} />
        </div>
      </Gate>
    </section>
  );
}

function ValuationHistory({ r }: { r: Ratios }) {
  const [k, setK] = useState<"pe" | "pb" | "ps">("pe");
  const vh = r.valuationHistory, v = vh.rows[k] || [], nn = v.filter((x): x is number => x != null), mean = nn.reduce((a, b) => a + b, 0) / (nn.length || 1), max = Math.max(...nn, 1);
  if (!nn.length) return null;
  return (
    <div style={{ marginTop: 24 }}>
      <div className="tools"><div className="label">Valuation history</div><div className="seg">{(["pe", "pb", "ps"] as const).map((x) => <button key={x} aria-pressed={k === x} onClick={() => setK(x)}>{x === "pe" ? "P/E" : x === "pb" ? "P/B" : "P/S"}</button>)}</div></div>
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${vh.periods.length}, 1fr)`, gap: 8, alignItems: "end", height: 150 }}>
        {vh.periods.map((p, i) => <div key={p} style={{ display: "grid", gap: 4, justifyItems: "center", alignContent: "end", height: "100%" }}>
          <span className="faint" style={{ fontSize: 11 }}>{v[i] == null ? "" : nf(v[i] as number, 1) + "×"}</span>
          <div style={{ width: "100%", maxWidth: 46, height: `${((v[i] || 0) / max) * 100}%`, borderRadius: "6px 6px 2px 2px", background: (v[i] || 0) > mean ? "var(--c4)" : "var(--c2)", opacity: 0.85 }} /><span className="faint" style={{ fontSize: 11 }}>{p}</span></div>)}
      </div>
      <div className="legend"><span><i style={{ background: "var(--c4)" }} />Above its {nn.length}-year average ({nf(mean, 1)}×)</span><span><i style={{ background: "var(--c2)" }} />Below average</span></div>
    </div>
  );
}

/* ---------------- Peers ---------------- */
export function PeersSection({ p, self }: { p?: Peers; self: string }) {
  const nav = useNavigate(); const qc = useQueryClient();
  const items = (p?.items || p?.symbols.map((s) => ({ symbol: s, name: null })) || []) as NonNullable<Peers["items"]>;
  if (!p || !items.length) return null;
  const all = [...items.filter((i) => i.symbol !== self)];
  return (
    <section className="block" style={{ "--sc": "var(--gold-deep)" } as React.CSSProperties}>
      <SectionHead id="peers" no="06 · Peers" icon="layers" tier="basic" title="Companies in the same space" sub="Select a company to open its report." color="--gold-deep" />
      <div className="card acc" style={{ padding: 12, "--ac": "var(--gold)" } as React.CSSProperties}>
        {all.map((i) => (
          <a key={i.symbol} className="peer" href={`/stocks/${i.symbol}`} onMouseEnter={() => prefetchStock(qc, i.symbol)} onClick={(e) => { e.preventDefault(); nav(`/stocks/${i.symbol}`); }}>
            <span className="av" style={{ background: "linear-gradient(140deg,#60A5FA,#2563EB)" }}>{initials(i.symbol)}</span>
            <span style={{ minWidth: 0 }}><span className="nm">{i.name || i.symbol}</span><span className="tk">{i.symbol}</span></span>
            <span className="bar">{i.overall != null && <b style={{ width: `${i.overall}%`, background: "linear-gradient(90deg,color-mix(in srgb,var(--gold) 40%,transparent),var(--gold))" }} />}</span>
            <span className="mc">{i.overall != null ? <>Score {i.overall}</> : i.market_cap != null ? <>₹{nf(i.market_cap, 0)}<span className="unit">Cr</span></> : "Open"}</span>
          </a>
        ))}
      </div>
    </section>
  );
}

/* ---------------- Gold insights ---------------- */
export function InsightsSection({ s, r, seg, tech }: { s: Summary; r?: Ratios; seg?: Segments; tech?: { rsi14: number | null } }) {
  const b = useMemo(() => buckets(s, r, tech), [s, r, tech]);
  return (
    <section className="block" style={{ "--sc": "var(--t-gold)" } as React.CSSProperties}>
      <SectionHead id="insights" no="07 · Gold insights" icon="crown" tier="gold" title="Buckets, triggers and segments" sub="Where this company sits in FinLit's stock buckets, and what to watch next." color="--t-gold" />
      <Plain>Buckets are quick labels. <b>Size</b> says how big the company is, <b>Style</b> how the market prices it, <b>Income</b> how much it pays out, and <b>Momentum</b> how the price has moved lately. Triggers are the things most worth watching next.</Plain>
      <Gate tier="gold" title="Unlock Gold insights" points={["Stock bucketing by size, style and theme", "Key triggers and sector benchmarking", "Revenue segmentation by segment"]}>
        <div className="grid g2">
          <div className="card acc" style={{ "--ac": "var(--t-gold)" } as React.CSSProperties}>
            <div className="card-h"><h3><span className="ci"><Icon name="layers" /></span>Stock buckets</h3><span className="s">From FinLit filters</span></div>
            <div className="buckets">{b.map(([ic, k, v, c]) => <div className="bucket" key={k} style={{ "--bc": css(c) } as React.CSSProperties}><span className="bi"><Icon name={ic} /></span><span><span className="k" style={{ display: "block" }}>{k}</span><span className="v">{v}</span></span></div>)}</div>
            <div className="label" style={{ margin: "22px 0 12px" }}>Key triggers to watch</div>
            <ul className="trig">{[...s.watchouts.slice(0, 2), ...s.strengths.slice(0, 1)].map((n, i) => <li key={n.key} style={{ "--tc": css(["--p-profit", "--p-tech", "--p-balance"][i % 3]) } as React.CSSProperties}><span className="ti"><Icon name={["profit", "activity", "users"][i % 3]} /></span><span><b>{n.title}</b><span className="d">{n.text}</span></span></li>)}</ul>
          </div>
          <SegmentCard seg={seg} />
        </div>
      </Gate>
    </section>
  );
}

void MINUS;
