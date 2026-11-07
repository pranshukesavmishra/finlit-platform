// Block 2, Market today: seven index cards, the daily Nifty 50 / Sensex chart, and the prices-and-rates strip (Brent, USD/INR, repo, CPI, WPI, 10-year G-sec).
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { useIndices } from "../../lib/indices";
import { useMacro } from "../../lib/macro";
import { rateTiles } from "../../lib/dashMacro";
import { dayMonth, monthYear, pickIndices } from "../../lib/dashboard";
import { MINUS, dateIN, nf } from "../../lib/format";
import { niceTicks } from "../../lib/etf";
import { RANGES, lastN, useLevels } from "../../lib/markets";
import { useGold } from "../../lib/premium";
import { Card, Seg, tone, useWidth } from "./parts";
import { ChartZoom } from "../../components/ChartZoom";

const sgn = (v: number | null | undefined, d = 2) => (v == null ? MINUS : (v > 0 ? "+" : v < 0 ? MINUS : "") + nf(Math.abs(v), d) + "%");
const pts = (v: number | null | undefined) => (v == null ? "" : ` (${v > 0 ? "+" : v < 0 ? MINUS : ""}${nf(Math.abs(v))})`);
const CHARTS = [["NIF50", "Nifty 50"], ["SNSXSENSEX", "Sensex"]] as const;

function IndexChart({ items }: { items: { code: string; close: number | null; changePct: number | null }[] }) {
  const [code, setCode] = useState<string>("NIF50"), [range, setRange] = useState<(typeof RANGES)[number][0]>("6M");
  const q = useLevels(code, range === "5Y" ? 5 : 1);
  const [box, W] = useWidth<HTMLDivElement>();
  const [hv, setHv] = useState<number | null>(null);
  const n = RANGES.find((r) => r[0] === range)![1], live = items.find((r) => r.code === code);
  const rows = useMemo(() => lastN(q.data?.rows || [], n), [q.data, n]);
  const H = 240, L = 56, R = 12, T = 14, B = 28;
  const controls = (
    <div className="dsh-chart-c">
      <Seg label="Index" value={code} options={CHARTS} onChange={(c) => { setCode(c); setHv(null); }} />
      <Seg label="Range" value={range} options={RANGES.map(([k]) => [k, k] as const)} onChange={(k) => { setRange(k); setHv(null); }} />
    </div>
  );
  if (q.isError) return <div className="dsh-chart">{controls}<p className="dsh-note">Daily closes for this index are not available right now.</p></div>;
  if (!rows.length) return <div className="dsh-chart">{controls}<div className="skeleton" style={{ height: H, marginTop: 12 }} aria-busy="true" /></div>;
  const v = rows.map((r) => r.c), last = v[v.length - 1], up = last >= v[0];
  const ticks = niceTicks(Math.min(...v), Math.max(...v), 4), lo = ticks[0], hi = ticks[ticks.length - 1];
  const X = (i: number) => L + (i / Math.max(1, rows.length - 1)) * (W - L - R), Y = (c: number) => T + (1 - (c - lo) / (hi - lo || 1)) * (H - T - B);
  const path = rows.map((r, i) => `${i ? "L" : "M"}${X(i).toFixed(1)} ${Y(r.c).toFixed(1)}`).join("");
  const color = up ? "var(--d-up)" : "var(--d-down)", cur = hv == null ? null : rows[hv], prev = hv != null && hv > 0 ? rows[hv - 1] : null;
  const span = (+new Date(rows[rows.length - 1].d) - +new Date(rows[0].d)) / 864e5;
  const label = (d: string) => (span > 400 ? monthYear(d).replace(/ 20(\d\d)$/, " $1") : dayMonth(d));
  const xs = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(f * (rows.length - 1)));
  const chg = (a: number, b: number) => (a / b - 1) * 100;
  const day = live?.changePct ?? chg(last, v[v.length - 2] ?? v[0]);
  const move = (e: React.PointerEvent<SVGSVGElement>) => { const r = e.currentTarget.getBoundingClientRect(); setHv(Math.max(0, Math.min(rows.length - 1, Math.round((((e.clientX - r.left) / r.width) * W - L) / (W - L - R) * (rows.length - 1))))); };
  const key = (e: React.KeyboardEvent) => { if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); setHv((h) => Math.max(0, Math.min(rows.length - 1, (h ?? rows.length - 1) + (e.key === "ArrowRight" ? 1 : -1)))); } else if (e.key === "Escape") setHv(null); };
  return (
    <div className="dsh-chart" ref={box}>
      <ChartZoom label={"Index closing levels"} className="cz-r">
      {controls}
      <div className="dsh-chart-s"><b>{nf(live?.close ?? last)}</b><span className={tone(day)}>{sgn(day)} today</span><em>{range} {sgn(chg(last, v[0]))} · daily closes, {label(rows[0].d)} to {label(rows[rows.length - 1].d)}</em></div>
      <div className="dsh-chart-b">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" tabIndex={0} aria-label={`${CHARTS.find((c) => c[0] === code)![1]} daily closing level, ${range}. Use the left and right arrow keys to read each day.`} onPointerMove={move} onPointerLeave={() => setHv(null)} onKeyDown={key}>
          <defs><linearGradient id="dshfill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor={color} stopOpacity=".18" /><stop offset="1" stopColor={color} stopOpacity="0" /></linearGradient></defs>
          {ticks.map((t) => <g key={t} className="grid"><line x1={L} x2={W - R} y1={Y(t)} y2={Y(t)} /><text x={L - 8} y={Y(t) + 4} textAnchor="end">{nf(t, 0)}</text></g>)}
          {xs.map((i) => <text key={i} className="xt" x={X(i)} y={H - 8} textAnchor={i === 0 ? "start" : i === rows.length - 1 ? "end" : "middle"}>{label(rows[i].d)}</text>)}
          <path d={`${path}L${X(rows.length - 1)} ${H - B}L${X(0)} ${H - B}Z`} fill="url(#dshfill)" /><path d={path} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" />
          {cur && hv != null && <g className="hv"><line x1={X(hv)} x2={X(hv)} y1={T} y2={H - B} /><circle cx={X(hv)} cy={Y(cur.c)} r="5" fill={color} /></g>}
        </svg>
        {cur && hv != null && <div className="dsh-tip" style={{ left: `${Math.min(86, Math.max(14, (X(hv) / W) * 100))}%` }} role="status"><b>{`${dayMonth(cur.d, true)}`}</b><span>Close {nf(cur.c)}</span>{prev && <span className={tone(chg(cur.c, prev.c))}>Day {sgn(chg(cur.c, prev.c))}</span>}</div>}
      </div>
      </ChartZoom>
    </div>
  );
}

export function MarketToday() {
  const idx = useIndices(), macro = useMacro(), gold = useGold();
  const d = idx.data, cards = useMemo(() => pickIndices(d?.items ?? []), [d]);
  const tiles = useMemo(() => rateTiles(macro.data), [macro.data]);
  const status = d ? <><span className={"dsh-dot" + (d.marketOpen ? " on" : "")} />{d.marketOpen ? "Open" : "Closed"} · {d.marketOpen ? "live" : "last close"}{d.asOf ? ` · ${dateIN(d.asOf)}` : ""}</> : undefined;
  const vix = cards[6], main = cards.slice(0, 6);
  const tile = (c: (typeof cards)[number]) => {
    const r = c.row; if (!r) return <div key={c.label} className="dsh-ix na"><div className="n">{c.label}</div><div className="v">—</div><div className="c" title="This index is not in today's feed">Not in today's feed</div></div>;
    const ch = r.changePct;
    return <Link key={c.label} to={gold ? "/premium/markets#indices" : "/markets"} className="dsh-ix"><div className="n">{c.label}</div><div className="v">{nf(r.close as number)}</div>
      <div className={"c " + tone(ch)}>{ch == null ? MINUS : (ch > 0 ? "▲ " : ch < 0 ? "▼ " : "") + sgn(ch)}<span className="p">{pts(r.points)}</span></div><div className="pe">{r.pe != null ? `P/E ${nf(r.pe, 1)}` : "P/E —"}</div></Link>;
  };
  return (
    <Card id="market" title="Market today" sub={status} right={gold && d ? <Link className="dsh-link" to="/premium/markets#indices">All {d.items.length} indices →</Link> : undefined}>
      {!d ? <div className="dsh-ixs">{Array.from({ length: 7 }, (_, i) => <div key={i} className="skeleton" style={{ height: 92, borderRadius: 12 }} />)}</div> : idx.isError ? <p className="dsh-note">Index levels are not available right now.</p> : <>
        <div className="dsh-ixs" aria-label="Index levels">{main.map(tile)}
          {vix.row ? <div className="dsh-ix vix"><div className="n">India VIX</div><div className="v">{nf(vix.row.close as number)}</div><div className={"c " + tone(vix.row.changePct)}>{vix.row.changePct == null ? MINUS : (vix.row.changePct > 0 ? "▲ " : "▼ ") + sgn(vix.row.changePct)}<span className="p">{pts(vix.row.points)}</span></div><div className="pe">Volatility</div></div> : tile(vix)}</div>
        <div className="dsh-hide-phone"><IndexChart items={d.items} /></div>
      </>}
      <div className="dsh-rates"><div className="dsh-rates-h">Prices and rates that move company profits</div>
        {macro.isLoading ? <div className="dsh-rates-g">{Array.from({ length: 6 }, (_, i) => <div key={i} className="skeleton" style={{ height: 68, borderRadius: 12 }} />)}</div> :
          <div className="dsh-rates-g">{tiles.map((t) => <div key={t.key} className="dsh-rate"><div className="n">{t.name}</div><div className="v">{t.value ?? "—"}</div><div className={"nt " + (t.tone ?? "")}>{t.note}</div></div>)}</div>}
        <p className="dsh-foot">Sources: U.S. EIA (Brent), FBIL (USD/INR), RBI (repo), MoSPI (CPI, WPI). Brent is compared with its average over the last four finished quarters, the period behind companies' latest results.</p></div>
    </Card>
  );
}
