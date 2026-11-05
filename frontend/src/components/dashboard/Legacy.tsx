// Optional blocks of the earlier dashboard, kept for Customise (off in the default layout): quarter results, watchlist movers, second look, bands, DCF scenarios and Gold & silver.
// "Gold & silver today" shows MCX futures prices that come through Dhan, whose terms do not allow showing them on the site: it stays off until a licensed source is connected.
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { titleOf, subOf, codeNote } from "../../lib/companyLabel";
import { apiGet, type ApiError, type Financials } from "../../lib/api";
import { STATUS_TEXT, run, type DcfInputs } from "../../lib/dcf";
import { direction, inr, istTime, signedPct, useCommodities } from "../../lib/commodities";
import { TIER, useUI, type Plan } from "../../lib/ui";
import { BAND_LABEL, type Row } from "../../lib/screener";
import { DEMO } from "../../lib/demo";
import { signals } from "../../pages/Watchlist";
import { MiniBars } from "../../charts/MiniBars";
import { Icon } from "../../lib/icons";
import { MINUS, cr, nf } from "../../lib/format";

const sgn = (v: number | null | undefined, d = 1) => (v == null ? "—" : (v > 0 ? "+" : v < 0 ? MINUS : "") + nf(v, d) + "%");
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "up" : "down");
function Empty({ icon, title, text, to, cta }: { icon: string; title: string; text: string; to: string; cta: string }) {
  return <div className="dw-empty"><span className="dw-ei"><Icon name={icon} /></span><b>{title}</b><p>{text}</p><Link className="btn" to={to}>{cta}</Link></div>;
}

export function Movers({ items }: { items: Row[] }) {
  const top = [...items].filter((r) => r.change_pct != null).sort((a, b) => Math.abs(b.change_pct as number) - Math.abs(a.change_pct as number)).slice(0, 7);
  if (!items.length) return <Empty icon="wallet" title="No stocks yet" text="Add stocks to a watchlist to see how they moved today." to="/watchlist" cta="Open watchlist" />;
  const max = Math.max(...top.map((r) => Math.abs(r.change_pct as number)), 1);
  return (
    <ul className="dv">{top.map((r) => (
      <li key={r.symbol}><Link to={`/stocks/${r.symbol}`}><b title={codeNote(r)}>{titleOf(r)}</b>{subOf(r) && <small>{subOf(r)}</small>}</Link>
        <span className="dvbar" aria-hidden="true"><i className={tone(r.change_pct)} style={{ width: `${(Math.abs(r.change_pct as number) / max) * 50}%`, [(r.change_pct as number) >= 0 ? "left" : "right"]: "50%" }} /></span>
        <span className={"dvv " + tone(r.change_pct)}>{sgn(r.change_pct)}</span></li>))}</ul>
  );
}

function ResultCard({ symbol, name }: { symbol: string; name: string | null }) {
  const { data, isError } = useQuery({ queryKey: ["stock", symbol, "/financials"], queryFn: () => apiGet<Financials>(`/api/stocks/${symbol}/financials`), staleTime: 60_000, retry: false });
  const q = data?.quarterly.pl;
  if (isError || (data && (!q || q.periods.length < 2))) return null;
  if (!q) return <div className="rc"><div className="skeleton" style={{ height: 120 }} /></div>;
  const n = q.periods.length, last = n - 1, yoy = n >= 5 ? n - 5 : -1;
  const ch = (a?: number | null, b?: number | null) => (a == null || b == null || !b ? null : ((a - b) / Math.abs(b)) * 100);
  const rev = q.rows.revenue as (number | null)[], np = q.rows.net_profit as (number | null)[];
  const line = (label: string, v: (number | null)[]) => (
    <div className="rc-r"><span>{label}</span><b>{v[last] == null ? "—" : (v[last]! < 0 ? MINUS : "") + "₹" + cr(Math.abs(v[last] as number))} Cr</b>
      <span className={"qd " + tone(ch(v[last], yoy >= 0 ? v[yoy] : null))}>{sgn(ch(v[last], yoy >= 0 ? v[yoy] : null))} <small>YoY</small></span>
      <span className={"qd " + tone(ch(v[last], v[last - 1]))}>{sgn(ch(v[last], v[last - 1]))} <small>QoQ</small></span></div>
  );
  return (
    <Link className="rc" to={`/stocks/${symbol}#quarter`}>
      <div className="rc-h"><b>{symbol}</b><small>{name} · {q.periods[last]}</small></div>
      {line("Revenue", rev)}{line("Net profit", np)}
      <MiniBars labels={q.periods.slice(-6)} series={[{ key: "np", label: "Net profit", values: np.slice(-6), color: "var(--gold)" }]} fmt={(v) => cr(v)} height={86} w={260} highlight={5} />
    </Link>
  );
}
export function Results({ symbols, names }: { symbols: string[]; names: Map<string, string | null> }) {
  if (!symbols.length) return <><Empty icon="notes" title="Pick stocks to follow" text="Your watchlist's newest quarterly results appear here, compared with last quarter and last year." to="/watchlist" cta="Build a watchlist" /><p className="rcs-all"><Link to="/results/quarter">See all quarter results <Icon name="arrow" /></Link></p></>;
  return <><div className="rcs">{symbols.slice(0, 4).map((s) => <ResultCard key={s} symbol={s} name={names.get(s) ?? null} />)}</div><p className="rcs-all"><Link to="/results/quarter">See all quarter results <Icon name="arrow" /></Link></p></>;
}

export function SecondLook({ items, meta }: { items: Row[]; meta: Record<string, { target?: number }> }) {
  const flagged = items.map((r) => ({ r, s: signals(r, meta[r.symbol]?.target) })).filter((x) => x.s.length).slice(0, 5);
  if (!items.length) return <Empty icon="quality" title="Nothing to review yet" text="Add stocks to your watchlist and FinLit flags the ones that need a second look." to="/watchlist" cta="Open watchlist" />;
  if (!flagged.length) return <p className="muted dw-ok"><Icon name="check" /> Nothing in your watchlist needs attention right now.</p>;
  return <ul className="sl">{flagged.map(({ r, s }) => <li key={r.symbol}><Link to={`/stocks/${r.symbol}`}><b title={codeNote(r)}>{titleOf(r)}</b>{r.band && <span className={"band-dot " + r.band}>{BAND_LABEL[r.band]}</span>}</Link><span>{s[0]}</span></li>)}</ul>;
}
export function Buckets({ items }: { items: Row[] }) {
  const order = ["strong", "healthy", "mixed", "watch"] as const;
  const colour: Record<string, string> = { strong: "var(--v-strong)", healthy: "var(--v-healthy)", mixed: "var(--v-mixed)", watch: "var(--v-weak)" };
  const counts = order.map((b) => ({ b, n: items.filter((r) => r.band === b).length }));
  const total = counts.reduce((a, c) => a + c.n, 0);
  if (!total) return <Empty icon="layers" title="No scored stocks" text="Add stocks to a watchlist to see them grouped by FinLit band." to="/watchlist" cta="Open watchlist" />;
  return (
    <div><div className="breadth big" role="img" aria-label="Watchlist by band">{counts.filter((c) => c.n).map((c) => <i key={c.b} style={{ flex: c.n, background: colour[c.b] }} />)}</div>
      <ul className="bandk">{counts.map((c) => <li key={c.b}><i style={{ background: colour[c.b] }} /><span>{BAND_LABEL[c.b]}</span><b>{c.n}</b></li>)}</ul></div>
  );
}
export function Locked({ tier, label }: { tier: Plan; label: string }) {
  const { upgrade } = useUI();
  return <div className="dw-lock"><span className="dw-ei"><Icon name="lock" /></span><b>{label}</b><p>Part of the {TIER[tier].n} plan.</p><button className="btn" onClick={() => upgrade(tier, `${label} is part of ${TIER[tier].n}.`)}>Unlock with {TIER[tier].n}</button></div>;
}
export function CommoditiesW() {
  const q = useCommodities();
  const rows = (q.data?.items ?? []).filter((i) => ["gold", "silver", "crude"].includes(i.code) && i.mcx?.price);
  if (q.isError || (q.data && !rows.length)) return <Empty icon="activity" title="Gold and silver today" text="MCX gold, silver and crude oil with the day change, and the international price beside them." to="/commodities" cta="Open commodity prices" />;
  if (!q.data) return <div className="skeleton" style={{ height: 120 }} />;
  return <><ul className="sl">{rows.map((i) => { const m = i.mcx!; const d = direction(m.change?.pct);
    return <li key={i.code}><Link to="/commodities"><b>{i.name}</b>{m.change ? <span className={"chip " + (d === "up" ? "up" : d === "down" ? "down" : "gold")}>{signedPct(m.change.pct)}</span> : null}</Link>
      <span>{inr(m.price!.value)} {m.price!.unit.replace(/^₹\s*/, "")} · {m.contract}{m.asOf ? ` · ${m.state === "closed" ? "last trade" : "trade at"} ${istTime(m.asOf)} IST` : ""}</span></li>; })}</ul>
    <p className="rcs-all"><Link to="/commodities">Open commodity prices <Icon name="arrow" /></Link></p></>;
}

type SavedDcf = { name: string; symbol: string | null; updatedAt: string; inputs: DcfInputs };
export function DcfW() {
  const q = useQuery<{ scenarios: SavedDcf[] }, ApiError>({ queryKey: ["dcf-scenarios"], queryFn: () => apiGet("/api/dcf/scenarios"), retry: false, enabled: !DEMO });
  const list = (q.data?.scenarios ?? []).slice(0, 5);
  if (DEMO || q.isError || (q.data && !list.length)) return <Empty icon="rupee" title="Value a company" text="Work out the intrinsic value per share, the margin-of-safety price and what today's price implies." to="/dcf" cta="Open the DCF calculator" />;
  if (!q.data) return <div className="skeleton" style={{ height: 120 }} />;
  return <><ul className="sl">{list.map((s) => { const o = run(s.inputs), r = o.result;
    return <li key={s.name}><Link to={dcfLink(s)}><b>{s.name}</b>{r && r.equity > 0 ? <span className={"chip " + (r.status === "buy" ? "up" : r.status === "overvalued" ? "down" : "gold")}>{STATUS_TEXT[r.status].label}</span> : null}</Link>
      <span>{r && r.equity > 0 ? `Value ₹${nf(r.iv, 2)} · buy below ₹${nf(r.buyPrice, 2)} · price ₹${nf(s.inputs.price, 2)} when saved` : "Inputs need a fix"}</span></li>; })}</ul>
    <p className="rcs-all"><Link to="/dcf">Open the DCF calculator <Icon name="arrow" /></Link></p></>;
}
const dcfLink = (s: SavedDcf) => {
  const i = s.inputs, sp = new URLSearchParams({ fcf: String(i.fcf0), r: String(i.r), g1: String(i.g1), g2: String(i.g2), gt: String(i.gT), mc: String(i.marketCap), p: String(i.price), nd: String(i.netDebt), mos: String(i.mos) });
  if (i.shares != null) sp.set("sh", String(i.shares));
  if (i.midYear) sp.set("mid", "1");
  if (i.tvMethod === "exit") { sp.set("tv", "exit"); if (i.exitMultiple != null) sp.set("xm", String(i.exitMultiple)); }
  if (s.symbol) sp.set("sym", s.symbol);
  return "/dcf?" + sp.toString();
};
