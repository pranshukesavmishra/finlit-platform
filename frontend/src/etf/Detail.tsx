// /etfs/:symbol: one ETF. Price and day change, price returns, a chart, risk in plain words, the NAV check, and what our data does not have.
import { Link, useParams, useSearchParams } from "react-router";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import {
  CATEGORY_TERM, COL_BY, RANGES, RANGE_LABEL, day, fallReading, move, pct, premiumReading, rangePosition, rangeReading, rupee, summaryOfSeries, traded, useEtf, useTray, volReading,
  MAX_COMPARE, type EtfDetail, type RangeKey,
} from "../lib/etf";
import { MINUS, nf } from "../lib/format";
import { Blank, DataNote, ErrorState, GlossInfo, Skeleton, Tone } from "./common";
import { EtfChart } from "./EtfChart";
import { EtfFacts } from "./Facts";
import { EtfHoldings } from "./Holdings";
import { ReturnsBlock } from "./Returns";

const isRange = (v: string | null): v is RangeKey => !!v && (RANGES as readonly string[]).includes(v);

export function EtfDetailPage() {
  const { symbol = "" } = useParams();
  const sym = symbol.toUpperCase();
  const [sp, setSp] = useSearchParams();
  const rangeParam = sp.get("range")?.toUpperCase() ?? null;
  const range: RangeKey = isRange(rangeParam) ? rangeParam : "1Y";
  const { data, isLoading, isError, error, refetch } = useEtf(sym, range);
  useDocTitle(data ? `${data.name} (${data.symbol})` : `${sym} ETF`, data ? `${data.name}: price, returns and risk. Information only, not investment advice.` : undefined);
  const tray = useTray();

  if (isError && (error as { status?: number }).status === 404) {
    return <div className="wrap etf-page"><div className="etf-state"><h2>We do not have an ETF with the symbol {sym}</h2><p>Check the spelling, or search the full list.</p><Link className="btn primary" to="/etfs">All ETFs</Link></div></div>;
  }
  if (isError && !data) return <div className="wrap etf-page"><ErrorState what="This ETF" onRetry={() => refetch()} /></div>;
  if (isLoading || !data) return <div className="wrap etf-page"><Skeleton rows={6} /></div>;
  const d = data;
  const termKey = d.category ? CATEGORY_TERM[d.category] : undefined;

  return (
    <div className="wrap etf-page etf-detail">
      <nav className="etf-crumb" aria-label="Breadcrumb"><Link to="/etfs">← All ETFs</Link></nav>
      <header className="etf-head">
        <div>
          <h1>{d.name}</h1>
          <div className="etf-ids">
            <span className="chip ghost mono">{d.symbol}</span><span className="chip ghost mono" title="ISIN">{d.isin}</span>
            {d.categoryLabel ? <span className="chip gold">{d.categoryLabel}{termKey && <GlossInfo name={termKey} fallback={d.categoryLabel} />}</span> : <span className="chip ghost" title="The fund's name does not say clearly what it follows">Category not clear from the name</span>}
            {d.fundHouse && <span className="chip ghost">{d.fundHouse}</span>}
          </div>
        </div>
        <div className="etf-quote">
          <div className="etf-price">{rupee(d.price)}</div>
          <div className={"etf-chg"}><Tone v={d.changePct}>{move(d.changePct)}</Tone><span className="faint"> vs previous close {rupee(d.previousClose)}</span></div>
          <div className="faint etf-asof">Close on {day(d.priceDate)}{d.priceNote ? ` · ${d.priceNote}` : ""}</div>
          <button className={"btn" + (tray.has(d.symbol) ? " on" : "")} aria-pressed={tray.has(d.symbol)} disabled={!tray.has(d.symbol) && tray.full} onClick={() => tray.toggle(d.symbol)}>
            <Icon name="compare" />{tray.has(d.symbol) ? "In your comparison" : tray.full ? `Compare is full (${MAX_COMPARE})` : "Add to compare"}</button>
          {tray.tray.length >= 2 && tray.has(d.symbol) && <Link className="etf-link" to={`/etfs/compare?symbols=${tray.tray.join(",")}`}>Compare {tray.tray.length} ETFs →</Link>}
        </div>
      </header>

      <ReturnsBlock head={d.headline} asOf={d.priceDate} />

      <section className="card etf-sec" aria-labelledby="h-chart">
        <div className="card-h"><h3 id="h-chart"><span className="ci"><Icon name="line" /></span>Price chart</h3>
          <div className="etf-ranges-btns" role="group" aria-label="Chart range">{RANGES.map((r) => {
            const a = d.ranges[r];
            return <button key={r} className={"chip-b" + (r === range ? " on" : "")} aria-pressed={r === range} disabled={a && !a.available && r !== range} title={a && !a.available ? a.why ?? undefined : undefined}
              onClick={() => setSp((p) => { const n = new URLSearchParams(p); n.set("range", r); return n; }, { replace: true })}>{RANGE_LABEL[r]}</button>;
          })}</div></div>
        {d.series.available ? (
          <>
            <EtfChart mode="price" series={[{ key: d.symbol, label: d.symbol, points: d.series.points, color: "var(--k1)" }]} summary={summaryOfSeries(d.name, d.series)} caption={`${d.name} closing price, ${RANGE_LABEL[range]}`} />
            <p className="faint etf-cap">Closing prices{d.series.grain === "weekly" ? ", last close of each week" : ", one point a day"}, {day(d.series.from)} to {day(d.series.to)}. Price only: dividends are not included.</p>
          </>) : <div className="etf-state small"><p><b>No chart for {RANGE_LABEL[range]}.</b> {d.series.why}</p></div>}
        {d.breakNote && <p className="etf-warn" role="note"><Icon name="alert" /><span>{d.breakNote}</span></p>}
      </section>

      <EtfHoldings symbol={d.symbol} />

      <section className="etf-risk" aria-labelledby="h-risk">
        <h2 id="h-risk" className="etf-h2">Risk, in plain words</h2>
        <div className="card etf-sec" aria-labelledby="h-ret">
          <div className="card-h"><h3 id="h-ret">Other periods <GlossInfo name="Price return" fallback={COL_BY.ret1y.help} /></h3><span className="s">price return to {day(d.priceDate)}</span></div>
          <div className="tw"><table className="etf-ret">
            <caption className="sr-only">Price return over 1 month, 6 months and 3 years</caption>
            <thead><tr><th scope="col">Period</th><th scope="col" className="num">Total price change</th><th scope="col" className="num">A year <GlossInfo name="CAGR (compound annual growth rate)" fallback="The yearly rate that gives the same total change." /></th></tr></thead>
            <tbody>{d.returns.filter((r) => ["1m", "6m", "3y"].includes(r.key)).map((r) => (
              <tr key={r.key}>
                <th scope="row">{r.label}</th>
                <td className="num">{r.price == null ? <Blank why={r.why ?? "Not enough price history"} /> : <Tone v={r.price}>{pct(r.price)}</Tone>}</td>
                <td className="num">{r.key === "3y" ? (r.annualised == null ? <Blank why={r.why ?? "Not enough price history"} /> : <Tone v={r.annualised}>{pct(r.annualised)}</Tone>) : <span className="faint" title="Shown for 3 years and longer">·</span>}</td>
              </tr>))}</tbody>
          </table></div>
          {d.returns.some((r) => ["1m", "6m", "3y"].includes(r.key) && r.price == null) && <ul className="etf-why">{d.returns.filter((r) => ["1m", "6m", "3y"].includes(r.key) && r.price == null).map((r) => <li key={r.key}><b>{r.label}:</b> {r.why ?? "Not enough price history"}</li>)}</ul>}
          {d.category === "liquid" && <p className="etf-info"><Icon name="info" />Some liquid ETFs pay out their income as dividends, so their price return can look close to zero while holders still received that income. Price return does not count payouts.</p>}
        </div>
        <div className="etf-grid3">
          <div className="card etf-sec">
            <div className="card-h"><h3>Volatility <GlossInfo name="Volatility" fallback={COL_BY.vol1y.help} /></h3><span className="s">last year</span></div>
            {d.risk.vol1y.value == null ? <p className="etf-big"><Blank why={d.risk.vol1y.why ?? "Not enough price history"} /></p> : <p className="etf-big">{pct(d.risk.vol1y.value, 1)}<small> a year</small></p>}
            <p className="etf-say">{volReading(d.risk.vol1y.value) ?? d.risk.vol1y.why}</p>
            {d.risk.vol1y.days != null && <p className="faint etf-small">From {d.risk.vol1y.days} daily price changes. Higher means a bumpier ride.</p>}
          </div>
          <div className="card etf-sec">
            <div className="card-h"><h3>Largest fall <GlossInfo name="Drawdown" fallback={COL_BY.mdd1y.help} /></h3><span className="s">high to later low</span></div>
            <table className="etf-mini"><tbody>{d.risk.drawdowns.map((x) => (
              <tr key={x.key}><th scope="row">{x.label}</th><td className="num">{x.value == null ? <Blank why={x.why ?? "Not enough price history"} /> : <Tone v={x.value}>{pct(x.value, 1)}</Tone>}</td></tr>))}</tbody></table>
            <p className="etf-say">{(() => { const last = [...d.risk.drawdowns].reverse().find((x) => x.value != null); return last ? fallReading(last) : "Not enough price history for a largest-fall figure."; })()}</p>
          </div>
          <div className="card etf-sec">
            <div className="card-h"><h3>52-week range <GlossInfo name="52-week high and low" fallback={COL_BY.from52.help} /></h3><span className="s">daily high and low</span></div>
            {d.risk.range52.high == null ? <p className="etf-big"><Blank why="Not enough price history" /></p> : (
              <>
                <div className="etf-bar" role="img" aria-label={`The price is ${nf(rangePosition(d.price, d.risk.range52.high, d.risk.range52.low) ?? 0, 0)} percent of the way from the 52-week low to the high`}>
                  <i style={{ left: `${rangePosition(d.price, d.risk.range52.high, d.risk.range52.low) ?? 0}%` }} /></div>
                <div className="etf-bar-l"><span>{rupee(d.risk.range52.low)}<small>low</small></span><span>{rupee(d.risk.range52.high)}<small>high</small></span></div>
                <p className="etf-say">{rangeReading(d.price, d.risk.range52.high, d.risk.range52.low)}</p>
                {d.risk.range52.why && <p className="faint etf-small">{d.risk.range52.why}</p>}
              </>)}
          </div>
        </div>
      </section>

      <div className="etf-grid2">
        <section className="card etf-sec" aria-labelledby="h-nav">
          <div className="card-h"><h3 id="h-nav"><span className="ci"><Icon name="balance" /></span>NAV and premium <GlossInfo name="Premium and discount to NAV" fallback="How far the exchange price is above or below the fund's net asset value on the same day." /></h3><span className="s">AMFI</span></div>
          <Nav d={d} />
        </section>
        <section className="card etf-sec" aria-labelledby="h-facts">
          <div className="card-h"><h3 id="h-facts"><span className="ci"><Icon name="id" /></span>Key facts</h3></div>
          <dl className="etf-facts">{d.facts.map((f) => (
            <div key={f.label}><dt>{f.label}{f.source && <small> ({f.source})</small>}</dt>
              <dd>{f.unit === "INR" ? <>{traded(Number(f.value))} <GlossInfo name="Traded value (turnover)" fallback={COL_BY.turnover.help} /></> : String(f.value)}{f.note && <small className="faint"> {f.note}</small>}</dd></div>))}</dl>
        </section>
      </div>

      <EtfFacts symbol={d.symbol} />

      <DataNote asOf={d.asOf} updatedAt={d.updatedAt} source={d.source} />
    </div>
  );
}

function Nav({ d }: { d: EtfDetail }) {
  if (!d.nav) return <p>No NAV was found for this ETF in AMFI's daily file, so there is no premium or discount to show.</p>;
  const n = d.nav, reading = premiumReading(n);
  return (
    <>
      <div className="etf-navrow"><div><span className="label">NAV</span><b>{rupee(n.value, 4)}</b><small>on {day(n.date)}</small></div>
        <div><span className="label">Premium / discount</span><b>{n.premium == null ? <Blank why={n.premiumWhy ?? "Not available"} /> : <Tone v={n.premium}>{n.premium > 0 ? "+" : n.premium < 0 ? MINUS : ""}{nf(Math.abs(n.premium), 2)}%</Tone>}</b><small>that day's exchange close against NAV</small></div></div>
      {reading ? <p className="etf-say">{reading}</p> : <p className="etf-say">{n.premiumWhy}</p>}
      {d.premiumWide && <p className="etf-info"><Icon name="info" />The exchange price and the NAV are far apart. Check the fund house's notices before relying on either figure. See “Premium and discount to NAV” in the glossary.</p>}
      <p className="faint etf-small">NAV is published by the fund house through AMFI once a day. The premium is only worked out when the ETF traded on the NAV's own day.</p>
    </>
  );
}
