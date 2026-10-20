import { HScroll } from "../components/HScroll";
import { PageArt } from "../components/PageArt";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getPortfolio, type PortfolioReport } from "../lib/siteApi";
import { Reveal } from "../components/Reveal";
import { useChart } from "../charts/useChart";
import { css, drawIn, el, niceTicks, vgrad } from "../lib/svg";
import { dateIN, MINUS, nf, signed } from "../lib/format";
import { useDocTitle } from "../lib/title";
import { Link } from "react-router";
import { ChartHelp } from "../components/ChartHelp";

const inr = (n: number) => (n < 0 ? MINUS : "") + "₹" + nf(Math.abs(n), 0);

function CumulativeLine({ data }: { data: PortfolioReport["charts"]["cumulativeRealizedPnl"] }) {
  const { wrap, svg } = useChart((s, W, first) => {
    const H = W < 520 ? 240 : 320, pl = 4, pr = 60, pt = 14, pb = 26, n = data.length;
    if (n < 2) return;
    s.setAttribute("viewBox", `0 0 ${W} ${H}`); s.style.height = H + "px";
    const v = data.map((d) => d.realizedPnl), lo = Math.min(0, ...v), hi = Math.max(...v) * 1.05;
    const x = (i: number) => pl + (i / (n - 1)) * (W - pl - pr), y = (p: number) => pt + (1 - (p - lo) / (hi - lo || 1)) * (H - pt - pb);
    niceTicks(lo, hi, 4).forEach((t) => { if (t < lo || t > hi) return; el("line", { x1: pl, x2: W - pr, y1: y(t), y2: y(t), stroke: css("--border"), "stroke-dasharray": "3 5" }, s); el("text", { x: W - pr + 8, y: y(t) + 4, fill: css("--faint"), "font-size": 11, "font-family": "IBM Plex Mono, monospace" }, s).textContent = nf(t / 1000, 0) + "k"; });
    const line = v.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p).toFixed(1)}`).join("");
    el("path", { d: `${line}L${x(n - 1)},${y(0)}L${x(0)},${y(0)}Z`, fill: vgrad(s, css("--gain"), 0.3, 0) }, s);
    drawIn(el("path", { d: line, fill: "none", stroke: css("--gain"), "stroke-width": 2.4, "stroke-linejoin": "round" }, s), first);
    [0, Math.floor(n / 2), n - 1].forEach((i, k) => el("text", { x: x(i), y: H - 6, fill: css("--faint"), "font-size": 11, "text-anchor": k === 0 ? "start" : k === 2 ? "end" : "middle", "font-family": "IBM Plex Mono, monospace" }, s).textContent = dateIN(data[i].date, { day: "numeric", month: "short" }));
    el("circle", { cx: x(n - 1), cy: y(v[n - 1]), r: 5, fill: css("--gold"), stroke: css("--s1"), "stroke-width": 2 }, s);
  }, [data]);
  return <div className="chart-box" ref={wrap}><svg ref={svg} role="img" aria-label="Cumulative realised profit over the period" /></div>;
}

function HBars({ rows, color }: { rows: { label: string; value: number }[]; color?: boolean }) {
  const max = Math.max(...rows.map((r) => Math.abs(r.value)), 1);
  return <div>{rows.map((r) => <div className="hbar" key={r.label} style={{ "--bc": r.value >= 0 ? "var(--gain)" : "var(--loss)" } as React.CSSProperties}><span>{r.label}</span><span className="tr"><b style={{ width: `${(Math.abs(r.value) / max) * 100}%`, background: color ? undefined : "var(--bc)" }} /></span><span className="num">{color === false ? r.value : inr(r.value)}</span></div>)}</div>;
}

export function Portfolio() {
  useDocTitle("Portfolio report", "FinLit's realised portfolio performance: P&L, ROI, win rate, charges and every trade, from the broker statement.");
  const { data, isLoading, isError } = useQuery<PortfolioReport>({ queryKey: ["portfolio"], queryFn: getPortfolio, retry: 1, staleTime: 300_000 });
  const [page, setPage] = useState(0);
  const [q, setQ] = useState("");
  const rows = useMemo(() => (data?.tradeLedger || []).filter((t) => !q || t.security.toLowerCase().includes(q.toLowerCase()) || t.symbol?.toLowerCase().includes(q.toLowerCase())), [data, q]);
  if (isLoading) return <div className="wrap state"><h1 className="sr-only">Portfolio</h1><div className="skeleton" style={{ height: 200 }} /></div>;
  if (isError || !data) return <div className="wrap state"><h1 style={{ font: "300 32px var(--serif)" }}>The portfolio report is not available yet</h1><p>Please check back soon.</p></div>;
  const c = data.charts, per = 15, pages = Math.ceil(rows.length / per);
  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><PageArt kind="portfolio" /><div className="eyebrow">Portfolio report</div><h1>Realised results, in the open.</h1><p>{data.profile.reportPeriod} · {data.profile.financialYear} · Capital deployed {data.profile.deployedCapital}. Realised profit and loss from the broker's statement, after all charges.</p></div></section>
      <section className="sec" style={{ paddingTop: 16 }}><div className="wrap"><p className="faint" role="note" style={{ margin: "0 0 14px", maxWidth: "80ch", fontSize: 13.5 }}><b>Please read:</b> this is one personal account of the founder, unaudited, shown only to explain how we think. It is not a track record of any FinLit service or product, it does not predict future returns, and it is not investment advice. FinLit Ventures is not registered with SEBI or AMFI.</p>
        <Reveal><div className="kpis-p">{[["Gross P&L", data.headline.grossPnl], ["Net P&L", data.headline.netPnl], ["Gross ROI", data.headline.grossRoi], ["Net ROI", data.headline.netRoi]].map(([k, v]) => <div className="kp" key={k}><div className="k">{k}</div><div className="v">{v}</div></div>)}</div></Reveal>
        <Reveal delay={60}><div className="kpis-p" style={{ marginTop: 14 }}>{[["Trades", String(data.summary.tradeCount)], ["Win rate", ((data.summary.winningTrades / data.summary.tradeCount) * 100).toFixed(1) + "%"], ["Winners / losers", `${data.summary.winningTrades} / ${data.summary.losingTrades}`], ["Charges", data.charges.totalFormatted]].map(([k, v]) => <div className="kp" key={k}><div className="k">{k}</div><div className="v">{v}</div></div>)}</div></Reveal>
        <Reveal><div className="card acc" style={{ marginTop: 16 }}><div className="card-h"><h3>Cumulative realised P&L<ChartHelp id="pf-cumulative" /></h3><span className="s">Gross, ₹</span></div><CumulativeLine data={c.cumulativeRealizedPnl} /></div></Reveal>
        <div className="grid g2" style={{ marginTop: 16 }}>
          <Reveal><div className="card acc"><div className="card-h"><h3>Monthly realised P&L<ChartHelp id="pf-monthly" /></h3></div><HBars rows={c.monthlyRealizedPnl.map((m) => ({ label: m.month, value: m.realizedPnl }))} /></div></Reveal>
          <Reveal delay={60}><div className="card acc"><div className="card-h"><h3>Top contributors<ChartHelp id="pf-contrib" /></h3><span className="s">By stock</span></div><HBars rows={c.pnlAttribution.map((m) => ({ label: m.stock, value: m.realizedPnl }))} /></div></Reveal>
          <Reveal><div className="card acc"><div className="card-h"><h3>Trade outcomes<ChartHelp id="pf-outcomes" /></h3></div><HBars color={false} rows={c.outcomes.map((o) => ({ label: o.outcome, value: o.trades }))} /></div></Reveal>
          <Reveal delay={60}><div className="card acc"><div className="card-h"><h3>Holding period<ChartHelp id="pf-holding" /></h3><span className="s">Trades</span></div><HBars color={false} rows={c.holdingPeriodDistribution.map((o) => ({ label: o.bucket, value: o.trades }))} /></div></Reveal>
        </div>
        <Reveal><div className="card acc" style={{ marginTop: 16 }}><div className="card-h"><h3>Charges breakdown<ChartHelp id="pf-charges" /></h3><span className="s">Total {data.charges.totalFormatted}</span></div>
          <div className="kpis-p">{Object.entries(data.charges.breakdown).map(([k, v]) => <div className="kp" key={k}><div className="k">{k.replace(/([A-Z])/g, " $1").trim()}</div><div className="v" style={{ fontSize: 22 }}>₹{nf(v)}</div></div>)}</div></div></Reveal>
        <Reveal><div className="card" style={{ marginTop: 16 }}>
          <div className="card-h"><h3>Every trade</h3><input className="sbox" placeholder="Search a stock" value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} aria-label="Search trades" /></div>
          <HScroll className="" label="table"><table className="tbl"><thead><tr><th>Security</th><th>Qty</th><th>Bought</th><th>Sold</th><th>Days</th><th>Realised P&L</th></tr></thead>
            <tbody>{rows.slice(page * per, page * per + per).map((t, i) => <tr key={i}><td>{t.security}</td><td>{t.quantity}</td><td>{dateIN(t.buyDate, { day: "numeric", month: "short" })}</td><td>{dateIN(t.sellDate, { day: "numeric", month: "short" })}</td><td>{t.holdingDays}</td><td className={t.realizedPnl >= 0 ? "pos" : "neg"}>{signed(t.realizedPnl, 2, "").replace("▲ ", "").replace("▼ ", "")}</td></tr>)}</tbody></table></HScroll>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 12 }}><span className="faint">{rows.length} trades · page {page + 1} of {Math.max(1, pages)}</span><div className="seg"><button disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Prev</button><button disabled={page + 1 >= pages} onClick={() => setPage((p) => p + 1)}>Next</button></div></div>
        </div></Reveal>
        <p className="faint" style={{ fontSize: 12.5, marginTop: 18 }}>Source: broker realised P&L statement ({data.sourceFileName}), generated {dateIN(data.generatedAt)}. Past performance does not indicate future results. <Link to="/legal/disclosures">Research disclosures</Link>.</p>
      </div></section>
    </>
  );
}
