import { useMemo, useState, type CSSProperties, type ReactNode } from "react";
import { Icon } from "../lib/icons";
import { Gate } from "../components/Gate";
import { MiniBars } from "../charts/MiniBars";
import { LineChart } from "../charts/LineChart";
import { AreaSeries, Box, Candles, Donut, Dumbbell, HeatGrid, Histo, RankBars, Slope, StackArea, Timeline, Treemap, Waterfall, type BoxRow, type Step } from "../charts/Atlas";
import { usePrice, useSection, type Events, type Financials, type Meta, type Ownership, type Peers, type Ratios, type Summary, type Table } from "../lib/api";
import { MINUS, cr, nf } from "../lib/format";
import { SectionHead } from "./Sections";

type N = number | null;
export type Stats = {
  meta?: Meta; available: boolean; locked?: boolean; sessions?: number; from?: string; to?: string; cagrPct?: number | null;
  monthly?: { years: number[]; rows: Record<string, N[]> };
  drawdown?: { t: string[]; dd: N[]; max: { pct: number | null; date: string | null }; current: number | null };
  volatility?: { t: string[]; vol: N[]; window: number; current: number | null; median: number | null };
  histogram?: { counts: number[]; from: number; binWidth: number; days: number; upShare: number; best: number; worst: number; clipped: number };
  box?: { years: (BoxRow & { days: number })[] };
};

const TABS = [["price", "Price"], ["pl", "Profit & loss"], ["bs", "Balance sheet"], ["cf", "Cash flow"], ["own", "Ownership"], ["val", "Valuation"], ["ev", "Events & peers"]] as const;
type Tab = (typeof TABS)[number][0];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const crf = (v: number) => (v < 0 ? MINUS : "") + (Math.abs(v) >= 1000 ? cr(Math.abs(v)) : nf(v, 0));
const pc = (v: number, d = 1) => (v < 0 ? MINUS : "") + nf(v, d) + "%";
const sg = (v: number, d = 0) => (v > 0 ? "+" : v < 0 ? MINUS : "") + nf(v, d) + "%";
const row = (t: Table | undefined, k: string) => (t?.rows[k] || []) as N[];
const C = (n: number) => `var(--c${n})`;

function Card({ title, sub, icon = "line", children, full, note }: { title: string; sub?: string; icon?: string; children: ReactNode; full?: boolean; note?: ReactNode }) {
  return (
    <div className={"card acc cl" + (full ? " full" : "")} style={{ "--ac": "var(--gold)" } as CSSProperties}>
      <div className="card-h"><h3><span className="ci"><Icon name={icon} /></span>{title}</h3>{sub && <span className="s">{sub}</span>}</div>
      {children}{note && <p className="cl-note">{note}</p>}
    </div>
  );
}
const Soon = ({ children }: { children: ReactNode }) => <p className="muted cl-empty">{children}</p>;

/* ---------------------------------------------------------------- price */
function PriceTab({ symbol }: { symbol: string }) {
  const [range, setRange] = useState("6M");
  const px = usePrice(symbol, range).data?.series;
  const stats = useSection<Stats>(symbol, "stats").data;
  const ok = stats?.available;
  const rows = useMemo(() => (stats?.monthly?.years || []).map((y) => ({ label: String(y), values: stats!.monthly!.rows[String(y)] })), [stats]);
  return (
    <>
      <Card title="Price, moving averages and volume" sub="Candles up to a year" full note="Green candles closed higher than they opened, red lower. The dashed line is the 50-day average; the solid line (Gold) is the 200-day average.">
        <div className="seg" role="group" aria-label="Candle range" style={{ marginBottom: 10 }}>{["1M", "6M", "1Y"].map((r) => <button key={r} aria-pressed={range === r} onClick={() => setRange(r)}>{r}</button>)}</div>
        {px && px.o && px.h && px.l ? <Candles t={px.t} o={px.o} h={px.h} l={px.l} c={px.c} v={px.v} ema50={px.ema50} ema200={px.ema200} /> : <div className="skeleton" style={{ height: 300 }} />}
      </Card>
      <Gate tier="bronze" title="Price statistics" points={["Monthly returns calendar", "Drawdown and volatility", "How big a typical day's move is"]}>
        {stats && !ok && !stats.locked ? <Soon>Not enough price history yet for these charts.</Soon> : (
          <div className="cl-grid">
            <Card title="Monthly returns" sub="Green months rose, red months fell" icon="growth" full note={stats?.cagrPct != null ? `Since ${stats?.from?.slice(0, 4)} the price has ${stats.cagrPct >= 0 ? "grown" : "fallen"} about ${pc(Math.abs(stats.cagrPct))} a year.` : undefined}>
              {rows.length ? <HeatGrid cols={MONTHS} rows={rows} cap={12} fmt={(v) => sg(v, 1).replace("%", "")} label="Monthly returns by year" /> : <div className="skeleton" style={{ height: 180 }} />}
            </Card>
            <Card title="Distance from the running high" sub="0% means a new high" icon="growth" note={stats?.drawdown ? `Deepest fall from a high: ${pc(stats.drawdown.max.pct ?? 0)} (${stats.drawdown.max.date}). Today the price is ${pc(Math.abs(stats.drawdown.current ?? 0))} below its high.` : undefined}>
              {stats?.drawdown ? <AreaSeries t={stats.drawdown.t} v={stats.drawdown.dd} fmt={(x) => pc(x, 0)} color="var(--loss)" ceil={0} /> : <div className="skeleton" style={{ height: 200 }} />}
            </Card>
            <Card title="How bumpy the ride is" sub={`${stats?.volatility?.window ?? 60}-session volatility, a year`} icon="gauge" note={stats?.volatility?.current != null ? `Now ${pc(stats.volatility.current, 0)} a year; the usual level is about ${pc(stats.volatility.median ?? 0, 0)}. Higher means bigger swings.` : undefined}>
              {stats?.volatility ? <AreaSeries t={stats.volatility.t} v={stats.volatility.vol} fmt={(x) => pc(x, 0)} color="var(--c1)" floor={0} ref={stats.volatility.median != null ? { y: stats.volatility.median, label: "usual" } : undefined} /> : <div className="skeleton" style={{ height: 200 }} />}
            </Card>
            <Card title="How big a typical day's move is" sub="Share of sessions by daily change" icon="bars" note={stats?.histogram ? `${nf(stats.histogram.upShare, 1)}% of sessions closed higher. Best day ${sg(stats.histogram.best, 1)}, worst ${sg(stats.histogram.worst, 1)}.` : undefined}>
              {stats?.histogram ? <Histo counts={stats.histogram.counts} from={stats.histogram.from} binWidth={stats.histogram.binWidth} /> : <div className="skeleton" style={{ height: 200 }} />}
            </Card>
            <Card title="Daily moves by year" sub="Calm years have short boxes" icon="layers">
              {stats?.box ? <Box years={stats.box.years} /> : <div className="skeleton" style={{ height: 240 }} />}
            </Card>
          </div>
        )}
      </Gate>
    </>
  );
}

/* ---------------------------------------------------------------- profit & loss */
function PlTab({ f }: { f?: Financials }) {
  const pl = f?.yearly.pl;
  if (!pl || pl.periods.length < 2) return <Soon>Profit and loss history is not available yet.</Soon>;
  const n = pl.periods.length, last = n - 1, r = (k: string) => row(pl, k);
  const rev = r("revenue"), exp = r("expenses"), op = r("operating_profit"), oi = r("other_income"), fin = r("finance_costs"), dep = r("depreciation"), ex = r("exceptional_items"), pbt = r("profit_before_tax"), tax = r("tax"), np = r("net_profit"), eps = r("eps");
  const v = (a: N[]) => a[last] ?? 0;
  const steps: Step[] = [{ label: "Revenue", value: v(rev), total: true }, { label: "Expenses", value: -Math.abs(v(exp)) }, { label: "Operating profit", value: v(op), total: true }, { label: "Other income", value: v(oi) },
    { label: "Interest", value: -Math.abs(v(fin)) }, { label: "Depreciation", value: -Math.abs(v(dep)) }, ...(Math.abs(v(ex)) > 0.5 ? [{ label: "One-offs", value: v(ex) }] : []), { label: "Profit before tax", value: v(pbt), total: true }, { label: "Tax", value: -Math.abs(v(tax)) }, { label: "Net profit", value: v(np), total: true }];
  const share = (a: N[]) => a.map((x, i) => (x != null && rev[i] ? (Math.abs(x) / (rev[i] as number)) * 100 : null));
  const chg = (a: N[]) => a.map((x, i) => (i && x != null && a[i - 1] ? ((x - (a[i - 1] as number)) / Math.abs(a[i - 1] as number)) * 100 : null)).slice(1);
  const growth: [string, N[]][] = [["Revenue", rev], ["Expenses", exp], ["Operating profit", op], ["Other income", oi], ["Interest", fin], ["Depreciation", dep], ["Profit before tax", pbt], ["Tax", tax], ["Net profit", np], ["EPS", eps]];
  return (
    <div className="cl-grid">
      <Card title={`From ${pl.periods[last]} revenue to net profit`} sub={`₹ Crore · ${pl.periods[last]}`} icon="profit" full note="Blue bars are totals, green adds to profit and red takes away. The steps show exactly where each rupee of revenue goes before it becomes profit.">
        <Waterfall steps={steps} fmt={crf} />
      </Card>
      <Card title="Where each ₹100 of revenue goes" sub="Share of revenue by year" icon="pie" note="The green slice is what is left as profit. A growing green slice means the business keeps more of each sale.">
        <MiniBars w={560} mode="stack" labels={pl.periods} fmt={(x) => nf(x, 0) + "%"} height={210} dim={false} series={[
          { key: "np", label: "Net profit", values: share(np).map((x) => (x != null ? Math.max(0, x) : x)), color: "var(--gain)" }, { key: "tax", label: "Tax", values: share(tax), color: C(4) },
          { key: "dep", label: "Depreciation", values: share(dep), color: C(3) }, { key: "fin", label: "Interest", values: share(fin), color: C(5) }, { key: "exp", label: "Expenses", values: share(exp).map((x, i) => (x != null && rev[i] ? Math.min(x, 100) : x)), color: C(1) }]} />
        <div className="lg"><span><i style={{ background: "var(--gain)" }} />Net profit</span><span><i style={{ background: C(4) }} />Tax</span><span><i style={{ background: C(3) }} />Depreciation</span><span><i style={{ background: C(5) }} />Interest</span><span><i style={{ background: C(1) }} />Expenses</span></div>
      </Card>
      <Card title="Earnings per share" sub="₹ per share, each year" icon="coins" note="Earnings per share is profit divided by the number of shares. It is the figure most closely tied to the share price.">
        <LineChart periods={pl.periods} series={[{ key: "eps", label: "EPS", color: "var(--gold)", values: eps }]} fmt={(x) => "₹" + nf(x, 1)} area height={210} />
      </Card>
      <Card title="Year-on-year growth by line" sub="Percent change on the year before" icon="growth" full note="Green is growth, red is decline. For costs (expenses, interest, tax) green means the cost rose, which can be fine when revenue rose faster.">
        <HeatGrid cols={pl.periods.slice(1)} cap={40} fmt={(x) => sg(x, 0)} label="Year on year growth by line item" rows={growth.map(([label, a]) => ({ label, values: chg(a) }))} />
      </Card>
    </div>
  );
}

/* ---------------------------------------------------------------- balance sheet */
function BsTab({ f }: { f?: Financials }) {
  const bs = f?.yearly.bs;
  if (!bs || bs.periods.length < 2) return <Soon>Balance sheet history is not available yet.</Soon>;
  const n = bs.periods.length, last = n - 1, g = (k: string) => row(bs, k);
  const ta = g("total_assets");
  const parts: [string, string, string][] = [["Plant & equipment", "fixed_assets", C(1)], ["Work in progress", "cwip", C(3)], ["Investments", "investments", C(2)], ["Inventories", "inventories", C(4)], ["Receivables", "receivables", C(5)], ["Cash", "cash", "var(--gain)"]];
  const other = ta.map((t, i) => (t == null ? null : Math.max(0, t - parts.reduce((a, [, k]) => a + (g(k)[i] ?? 0), 0))));
  const assets = [...parts.map(([label, k, color]) => ({ key: k, label, values: g(k), color })), { key: "other", label: "Other assets", values: other, color: "var(--s3)" }];
  const funding = [{ key: "eq", label: "Owners' money", values: g("total_equity"), color: C(1) }, { key: "bo", label: "Borrowings", values: g("borrowings"), color: "var(--loss)" }, { key: "ol", label: "Other liabilities", values: g("other_liabilities"), color: C(4) }];
  const pct = (series: typeof funding) => series.map((s) => ({ ...s, values: s.values.map((x, i) => (x != null && ta[i] ? (x / (ta[i] as number)) * 100 : null)) }));
  const tree = assets.map((a) => ({ label: a.label, value: Math.max(0, (a.values[last] as number) ?? 0), color: a.color })).filter((x) => x.value > 0);
  return (
    <div className="cl-grid">
      <Card title="What the company owns" sub="Total assets by kind, ₹ Crore" icon="building" note="Assets are everything the company controls. A big slice of cash and investments gives it room to move; a big slice of work in progress means projects not yet earning.">
        <MiniBars w={560} mode="stack" labels={bs.periods} fmt={crf} height={230} dim={false} series={assets} />
        <div className="lg">{assets.map((a) => <span key={a.key}><i style={{ background: a.color }} />{a.label}</span>)}</div>
      </Card>
      <Card title="How it is paid for" sub="Share of total assets" icon="balance" note="Owners' money is safe funding. Borrowings must be repaid with interest, so a shrinking red slice lowers risk.">
        <MiniBars w={560} mode="stack" labels={bs.periods} fmt={(x) => nf(x, 0) + "%"} height={230} dim={false} series={pct(funding)} />
        <div className="lg">{funding.map((a) => <span key={a.key}><i style={{ background: a.color }} />{a.label}</span>)}</div>
      </Card>
      <Card title={`${bs.periods[last]} assets at a glance`} sub="Box size is share of total assets" icon="layers" full>
        {tree.length ? <Treemap items={tree} fmt={(x) => "₹" + crf(x) + " Cr"} /> : <Soon>No breakdown available.</Soon>}
      </Card>
    </div>
  );
}

/* ---------------------------------------------------------------- cash flow */
function CfTab({ f }: { f?: Financials }) {
  const cf = f?.yearly.cf;
  if (!cf || cf.periods.length < 2) return <Soon>Cash flow history is not available yet.</Soon>;
  const last = cf.periods.length - 1, g = (k: string) => row(cf, k), v = (k: string) => g(k)[last] ?? 0;
  const steps: Step[] = [{ label: "Operations", value: v("operating") }, { label: "Investing", value: v("investing") }, { label: "Financing", value: v("financing") }, { label: "Net change in cash", value: v("net_cash_flow"), total: true }];
  return (
    <div className="cl-grid">
      <Card title="Operating, investing and financing cash flow" sub="₹ Crore" icon="coins" note="Cash from operations should be positive and healthy. Investing is usually negative because the company spends on growth; financing shows borrowing, repayments and dividends.">
        <MiniBars w={560} mode="group" labels={cf.periods} fmt={crf} height={230} dim={false} series={[{ key: "o", label: "Operations", values: g("operating"), color: "var(--gain)" }, { key: "i", label: "Investing", values: g("investing"), color: C(3) }, { key: "f", label: "Financing", values: g("financing"), color: C(5) }]} />
        <div className="lg"><span><i style={{ background: "var(--gain)" }} />Operations</span><span><i style={{ background: C(3) }} />Investing</span><span><i style={{ background: C(5) }} />Financing</span></div>
      </Card>
      <Card title={`${cf.periods[last]} cash bridge`} sub="₹ Crore" icon="profit" note="How the year's three streams add up to the change in cash.">
        <Waterfall w={560} steps={steps} fmt={crf} height={250} />
      </Card>
      <Card title="Free cash flow against capex" sub="What is left after investing in the business" icon="growth" full note="Free cash flow is cash from operations minus capital spending. It is the money available for dividends, debt repayment or buybacks.">
        <MiniBars w={1000} mode="group" labels={cf.periods} fmt={crf} height={210} dim={false} series={[{ key: "fcf", label: "Free cash flow", values: g("free_cash_flow"), color: "var(--gold)" }, { key: "cx", label: "Capex", values: g("capex").map((x) => (x == null ? x : -Math.abs(x))), color: C(4) }]} />
        <div className="lg"><span><i style={{ background: "var(--gold)" }} />Free cash flow</span><span><i style={{ background: C(4) }} />Capex (spending)</span></div>
      </Card>
    </div>
  );
}

/* ---------------------------------------------------------------- ownership */
const OWN: Record<string, [string, string]> = { promoters: ["Promoters", C(1)], fii: ["Foreign investors", C(2)], dii: ["Indian institutions", C(3)], public: ["Public", C(4)], government: ["Government", C(5)] };
function OwnTab({ o }: { o?: Ownership }) {
  if (!o || o.periods.length < 2) return <Soon>Shareholding history is not available yet.</Soon>;
  const keys = Object.keys(o.series).filter((k) => OWN[k] && o.series[k].some((x) => x != null));
  const last = o.periods.length - 1;
  const series = keys.map((k) => ({ key: k, label: OWN[k][0], values: o.series[k], color: OWN[k][1] }));
  const first = (k: string) => (o.series[k].find((x) => x != null) as number) ?? 0;
  const parts = keys.map((k) => ({ label: OWN[k][0], value: (o.series[k][last] as number) ?? 0, color: OWN[k][1] })).filter((x) => x.value > 0);
  const changes = o.latest.filter((l) => l.change1yPts != null && OWN[l.key]).map((l) => ({ label: OWN[l.key][0], value: l.change1yPts as number }));
  return (
    <div className="cl-grid">
      <Card title="Who owns the company, quarter by quarter" sub="Share of shares held" icon="users" full note="Each band is one group's share; together they always make 100%. Rising institutional bands often signal growing professional interest.">
        <StackArea periods={o.periods} series={series} />
        <div className="lg">{series.map((s) => <span key={s.key}><i style={{ background: s.color }} />{s.label}</span>)}</div>
      </Card>
      <Card title="Latest ownership mix" sub={o.asOf ? `As of ${o.asOf}` : undefined} icon="pie"><Donut parts={parts} center={nf(parts[0]?.value ?? 0, 1) + "%"} sub={parts[0]?.label} /></Card>
      <Card title={`Change since ${o.periods[0]}`} sub="Share of shares held, then and now" icon="layers">
        <Slope aLabel={o.periods[0]} bLabel={o.periods[last]} fmt={(x) => nf(x, 1) + "%"} rows={keys.map((k) => ({ label: OWN[k][0], a: first(k), b: (o.series[k][last] as number) ?? 0, color: OWN[k][1] }))} />
      </Card>
      {changes.length > 0 && <Card title="Change over the last year" sub="Percentage points" icon="growth" full><RankBars diverging rows={changes} fmt={(x) => (x > 0 ? "+" : x < 0 ? MINUS : "") + nf(x, 2) + " pts"} /></Card>}
    </div>
  );
}

/* ---------------------------------------------------------------- valuation */
function ValTab({ r }: { r?: Ratios }) {
  const vh = r?.valuationHistory;
  const rows = (["pe", "pb", "ps"] as const).map((k) => {
    const hist = ((vh?.rows?.[k] as N[] | undefined) || []).filter((x): x is number => x != null && x > 0).sort((a, b) => a - b);
    const now = r?.latest?.[k]?.value;
    return hist.length >= 3 && now != null ? { label: { pe: "Price to earnings (P/E)", pb: "Price to book (P/B)", ps: "Price to sales (P/S)" }[k], a: hist[Math.floor(hist.length / 2)], b: now } : null;
  }).filter((x): x is { label: string; a: number; b: number } => !!x);
  return (
    <div className="cl-grid">
      <Gate tier="gold" title="Valuation against its own history" points={["Today's multiples against the multi-year median", "Spot cheap and expensive stretches", "P/E, P/B and P/S side by side"]}>
        <Card title="Today against the usual level" sub="Multi-year median → now" icon="tag" full note="If the new value sits to the right of the old one, the stock is dearer than it has usually been; to the left, cheaper. Cheap is not always good: check the quality scores too.">
          {rows.length ? <Dumbbell rows={rows} aLabel="Usual (median)" bLabel="Now" fmt={(x) => nf(x, 1) + "×"} /> : <Soon>Valuation history is not available yet.</Soon>}
        </Card>
      </Gate>
    </div>
  );
}

/* ---------------------------------------------------------------- events & peers */
const kind = (t: string) => (/dividend/i.test(t) ? "dividend" : /bonus/i.test(t) ? "bonus" : /split/i.test(t) ? "split" : /right/i.test(t) ? "rights" : "other");
function EvTab({ e, p, s }: { e?: Events; p?: Peers; s: Summary }) {
  const events = (e?.actions || []).map((a) => ({ date: a.date, label: a.title, kind: kind(a.type) }));
  const peers = (p?.items || []).filter((x) => x.market_cap != null).map((x) => ({ label: x.symbol, value: x.market_cap as number }));
  const self = s.quote.marketCapCr ?? s.profile.marketCapCr;
  const bars = self ? [...peers, { label: s.profile.symbol, value: self, self: true }].sort((a, b) => b.value - a.value) : peers;
  return (
    <div className="cl-grid">
      <Card title="Dividends, bonus and splits" sub="Corporate actions over time" icon="coins" full note="Gold dots on the line are cash dividends; larger dots above it are bonus issues, splits or rights offers.">
        {events.length ? <Timeline events={events} /> : <Soon>No corporate actions on record.</Soon>}
      </Card>
      <Card title="Market value against peers" sub="₹ Crore" icon="layers">{bars.length > 1 ? <RankBars rows={bars} fmt={(x) => "₹" + crf(x)} /> : <Soon>Peer values appear once the peer companies are loaded.</Soon>}</Card>
      <Card title="Share of the group's value" sub="Box size is market value" icon="pie">{bars.length > 1 ? <Treemap height={230} items={bars.map((b, i) => ({ label: b.label, value: b.value, color: "self" in b ? "var(--gold)" : C((i % 4) + 2) }))} fmt={(x) => "₹" + crf(x) + " Cr"} /> : <Soon>Peer values appear once the peer companies are loaded.</Soon>}</Card>
    </div>
  );
}

/* ---------------------------------------------------------------- section */
export function ChartLab({ s, symbol, f, r, o, e, p }: { s: Summary; symbol: string; f?: Financials; r?: Ratios; o?: Ownership; e?: Events; p?: Peers }) {
  const [tab, setTab] = useState<Tab>("price");
  return (
    <section className="block" style={{ "--sc": "var(--c1)" } as CSSProperties}>
      <SectionHead id="charts" no="Chart lab" icon="bars" tier="basic" title="See it in charts" sub="Price, profit, balance sheet, cash, ownership and valuation, each drawn to be read at a glance." color="--c1" />
      <div className="seg cl-tabs" role="group" aria-label="Chart topics">{TABS.map(([k, label]) => <button key={k} aria-pressed={tab === k} onClick={() => setTab(k)}>{label}</button>)}</div>
      {tab === "price" && <PriceTab symbol={symbol} />}
      {tab === "pl" && <PlTab f={f} />}
      {tab === "bs" && <BsTab f={f} />}
      {tab === "cf" && <CfTab f={f} />}
      {tab === "own" && <OwnTab o={o} />}
      {tab === "val" && <ValTab r={r} />}
      {tab === "ev" && <EvTab e={e} p={p} s={s} />}
    </section>
  );
}
