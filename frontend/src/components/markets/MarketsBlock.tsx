// The dashboard's markets block, top to bottom: Market today (index levels and the daily Nifty 50 / Sensex chart), Market snapshot (breadth, movers,
// every sector as a heat-map), FII/DII flows, the index heat-map (stocks of an index, sized by market cap and coloured by today's move) and sectoral
// activity (pick a sector group, see its index and its gainers and losers). Information only.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { Logo } from "../search/parts";
import { FlowsPanel } from "../FlowsPanel";
import { useIndices, type IndexRow } from "../../lib/indices";
import { useSearchQuotes } from "../../lib/api";
import { quoteMap } from "../../lib/globalSearch";
import { MINUS, dateIN, nf } from "../../lib/format";
import { niceTicks } from "../../lib/etf";
import { useGold } from "../../lib/premium";
import type { Row } from "../../lib/screener";
import { CATEGORIES, FLAT_TILE, MAX_MOVE, RANGES, gainers, indexFor, largest, lastN, losers, moveColour, sectorBoard, stocksFor, treemap, useLevels, useMembers, weightedMove, type Pill } from "../../lib/markets";
import "../../styles/markets.css";

/** A listed company's ticker, or its name when the ticker is only a numeric exchange code. */
const shortName = (r: { symbol: string; name?: string | null }) => (/^\d+$/.test(r.symbol) && r.name ? r.name : r.symbol);
const sgn = (v: number | null | undefined, d = 2) => (v == null ? MINUS : (v > 0 ? "+" : v < 0 ? MINUS : "") + nf(Math.abs(v), d) + "%");
const tone = (v: number | null | undefined) => (v == null || Math.abs(v) < 0.005 ? "" : v > 0 ? "up" : "down");
const reduced = () => typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** Width of an element that may mount later than the component does (a chart behind a loading state): a callback ref, so the observer attaches whenever the element appears. */
function useWidth<T extends HTMLElement>(): [(el: T | null) => void, number] {
  const [w, setW] = useState(900);
  const ro = useRef<ResizeObserver | null>(null);
  const ref = useCallback((el: T | null) => {
    ro.current?.disconnect(); ro.current = null;
    if (!el) return;
    setW(Math.max(280, Math.round(el.getBoundingClientRect().width)));
    if (typeof ResizeObserver === "undefined") return;
    ro.current = new ResizeObserver(([e]) => setW(Math.max(280, Math.round(e.contentRect.width))));
    ro.current.observe(el);
  }, []);
  useEffect(() => () => ro.current?.disconnect(), []);
  return [ref, w];
}

// ---------------------------------------------------------------------------------------------------------------- market today
const CHART_INDEX = [["NIF50", "Nifty 50"], ["SNSXSENSEX", "Sensex"]] as const;

function DailyChart({ idx }: { idx: IndexRow[] }) {
  const [code, setCode] = useState<string>("NIF50"), [range, setRange] = useState<(typeof RANGES)[number][0]>("6M");
  const years = range === "5Y" ? 5 : 1;
  const q = useLevels(code, years);
  const [box, W] = useWidth<HTMLDivElement>();
  const [hv, setHv] = useState<number | null>(null);
  const n = RANGES.find((r) => r[0] === range)![1];
  const rows = useMemo(() => lastN(q.data?.rows || [], n), [q.data, n]);
  const live = idx.find((r) => r.code === code);
  const H = W < 560 ? 230 : 290, L = 56, R = 14, T = 16, B = 26;
  const controls = (
    <div className="mk-chart-h">
      <div className="mk-pills" role="radiogroup" aria-label="Index">{CHART_INDEX.map(([c, l]) => <button key={c} type="button" role="radio" aria-checked={code === c} className={code === c ? "on" : ""} onClick={() => { setCode(c); setHv(null); }}>{l}</button>)}</div>
      <div className="mk-seg" role="radiogroup" aria-label="Range">{RANGES.map(([k]) => <button key={k} type="button" role="radio" aria-checked={range === k} className={range === k ? "on" : ""} onClick={() => { setRange(k); setHv(null); }}>{k}</button>)}</div>
    </div>
  );
  if (q.isError) return <div className="mk-chart">{controls}<p className="mk-note">Daily closes for this index are not available right now.{(q.error as { status?: number })?.status === 404 ? " The preview build holds the Nifty 50 only." : ""}</p></div>;
  if (!rows.length) return <div className="mk-chart">{controls}<div className="skeleton" style={{ height: H }} aria-busy="true" /></div>;
  const v = rows.map((r) => r.c), up = v[v.length - 1] >= v[0];
  const ticks = niceTicks(Math.min(...v), Math.max(...v), 5), lo = ticks[0], hi = ticks[ticks.length - 1];
  const X = (i: number) => L + (i / Math.max(1, rows.length - 1)) * (W - L - R), Y = (c: number) => T + (1 - (c - lo) / (hi - lo || 1)) * (H - T - B);
  const path = rows.map((r, i) => `${i ? "L" : "M"}${X(i).toFixed(1)} ${Y(r.c).toFixed(1)}`).join("");
  const color = up ? "var(--gain)" : "var(--loss)", cur = hv == null ? null : rows[hv], prev = hv != null && hv > 0 ? rows[hv - 1] : null;
  const first = new Date(rows[0].d), last = new Date(rows[rows.length - 1].d), span = (+last - +first) / 864e5;
  const label = (d: string) => dateIN(d, span > 400 ? { month: "short", year: "2-digit" } : { day: "numeric", month: "short" });
  const xs = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(f * (rows.length - 1)));
  const move = (e: React.PointerEvent<SVGSVGElement>) => { const r = e.currentTarget.getBoundingClientRect(); setHv(Math.max(0, Math.min(rows.length - 1, Math.round(((((e.clientX - r.left) / r.width) * W) - L) / (W - L - R) * (rows.length - 1))))); };
  const key = (e: React.KeyboardEvent) => { if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); setHv((h) => Math.max(0, Math.min(rows.length - 1, (h ?? rows.length - 1) + (e.key === "ArrowRight" ? 1 : -1)))); } else if (e.key === "Escape") setHv(null); };
  const chg = (a: number, b: number) => ((a / b - 1) * 100);
  return (
    <div className="mk-chart" ref={box}>
      {controls}
      <div className="mk-chart-s"><b>{nf(live?.close ?? v[v.length - 1])}</b><span className={tone(live?.changePct ?? chg(v[v.length - 1], v[v.length - 2] ?? v[0]))}>{sgn(live?.changePct ?? chg(v[v.length - 1], v[v.length - 2] ?? v[0]))} today</span>
        <em>{range} {sgn(chg(v[v.length - 1], v[0]))} · daily closes, {label(rows[0].d)} to {label(rows[rows.length - 1].d)}</em></div>
      <div className="mk-chart-b">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" tabIndex={0} aria-label={`${CHART_INDEX.find((c) => c[0] === code)![1]} daily closing level, ${range}. Use the left and right arrow keys to read each day.`} onPointerMove={move} onPointerLeave={() => setHv(null)} onKeyDown={key}>
          <defs><linearGradient id="mkfill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor={color} stopOpacity=".28" /><stop offset="1" stopColor={color} stopOpacity="0" /></linearGradient></defs>
          {ticks.map((t) => <g key={t} className="mk-grid"><line x1={L} x2={W - R} y1={Y(t)} y2={Y(t)} /><text x={L - 8} y={Y(t) + 4} textAnchor="end">{nf(t, 0)}</text></g>)}
          {xs.map((i) => <text key={i} className="mk-xt" x={X(i)} y={H - 6} textAnchor={i === 0 ? "start" : i === rows.length - 1 ? "end" : "middle"}>{label(rows[i].d)}</text>)}
          <path d={`${path}L${X(rows.length - 1)} ${H - B}L${X(0)} ${H - B}Z`} fill="url(#mkfill)" /><path d={path} fill="none" stroke={color} strokeWidth="2.2" strokeLinejoin="round" className={reduced() ? "" : "mk-draw"} />
          {cur && hv != null && <g className="mk-hv"><line x1={X(hv)} x2={X(hv)} y1={T} y2={H - B} /><circle cx={X(hv)} cy={Y(cur.c)} r="5" fill={color} /></g>}
        </svg>
        {cur && hv != null && <div className="mk-tip" style={{ left: `${Math.min(86, Math.max(14, (X(hv) / W) * 100))}%` }} role="status"><b>{dateIN(cur.d, { weekday: "short", day: "numeric", month: "short", year: "numeric" })}</b><span>Close <em>{nf(cur.c)}</em></span>
          {prev && <span>Day <em className={tone(chg(cur.c, prev.c))}>{sgn(chg(cur.c, prev.c))}</em></span>}</div>}
      </div>
    </div>
  );
}

function MarketToday() {
  const { data, isError } = useIndices();
  const gold = useGold();
  if (isError) return null;
  if (!data) return <section className="mk-card" aria-busy="true"><div className="skeleton" style={{ height: 260 }} /></section>;
  const key = data.key.map((c) => data.items.find((r) => r.code === c)).filter((r): r is IndexRow => !!r && r.close != null);
  return (
    <section className="mk-card" aria-labelledby="mkToday">
      <div className="mk-h"><div><h2 id="mkToday">Market today</h2><p><span className={"pm-live" + (data.marketOpen ? " on" : "")} />{data.marketOpen ? "Market open · live" : "Market closed · last close"}{data.asOf ? ` · ${dateIN(data.asOf)}` : ""}</p></div></div>
      <div className="mk-tiles" aria-label="Index levels">{key.map((r) => { const c = r.changePct, good = r.code === "INDVIX" ? (c ?? 0) <= 0 : (c ?? 0) >= 0;
        return <div key={r.code} className={"mk-tile " + (c == null || c === 0 ? "" : good ? "up" : "down")}><small>{r.name}</small><b>{nf(r.close as number)}</b>
          <span>{c == null ? MINUS : (c > 0 ? "▲ " : c < 0 ? "▼ " : "") + sgn(c)}{r.points != null ? ` (${r.points > 0 ? "+" : r.points < 0 ? MINUS : ""}${nf(Math.abs(r.points))})` : ""}</span>{r.pe != null && <em>P/E {nf(r.pe, 1)}</em>}</div>; })}</div>
      <DailyChart idx={data.items} />
      <p className="mk-foot">{gold ? <>All {data.items.length} indices and 5-year valuation history: <Link to="/premium/markets#indices">Market events &amp; index dashboard</Link>.</> : "NSE and BSE index levels, refreshed every minute while the market is open."}</p>
    </section>
  );
}

// ---------------------------------------------------------------------------------------------------------------- heat-maps
type Cell = { key: string; label: string; sub: string; move: number | null; weight: number; href?: string; logo?: string | null; name: string };

function HeatMap({ cells, height, empty, minLabel = 64, logos = true }: { cells: Cell[]; height: number; empty: string; minLabel?: number; logos?: boolean }) {
  const [box, W] = useWidth<HTMLDivElement>();
  const tiles = useMemo(() => treemap(cells, (c) => c.weight, W, height), [cells, W, height]);
  if (!cells.length) return <p className="mk-note">{empty}</p>;
  return (
    <div className="mk-heat" ref={box} style={{ height }} role="list" aria-label="Heat map, tile size is market capitalisation, colour is today's move">
      {tiles.map(({ x, y, w, h, item: c }) => {
        const big = w >= minLabel && h >= 44, logoOk = logos && w >= 84 && h >= 84;
        const common = { className: "mk-tile2 " + tone(c.move), style: { left: x, top: y, width: w, height: h, background: moveColour(c.move) } as React.CSSProperties, title: `${c.name}: ${sgn(c.move)}` };
        const inner = big && <span className="mk-t-in">{logoOk && <Logo src={c.logo} name={c.name} kind="stock" size={Math.min(40, Math.round(Math.min(w, h) / 3))} />}<b>{c.label}</b><em>{sgn(c.move)}</em></span>;
        return c.href ? <Link key={c.key} to={c.href} role="listitem" {...common}>{inner}</Link> : <div key={c.key} role="listitem" {...common}>{inner}</div>;
      })}
    </div>
  );
}

function Legend() { return <span className="mk-legend" aria-hidden="true"><i style={{ background: moveColour(-2) }} /><i style={{ background: moveColour(-0.7) }} /><i style={{ background: FLAT_TILE }} /><i style={{ background: moveColour(0.7) }} /><i style={{ background: moveColour(2) }} />−2% … +2%</span>; }

function Snapshot({ rows }: { rows: Row[] }) {
  const m = useMemo(() => {
    const live = rows.filter((r) => r.change_pct != null && (r.price ?? 0) > 0);          // suspended or delisted companies carry no price and a −100% "change"
    const adv = live.filter((r) => (r.change_pct as number) > 0).length, dec = live.filter((r) => (r.change_pct as number) < 0).length;
    const big = live.filter((r) => (r.market_cap ?? 0) >= 100 && Math.abs(r.change_pct as number) <= MAX_MOVE);
    return { n: live.length, adv, dec, flat: live.length - adv - dec, up: gainers(big, 5), down: losers(big, 5), sectors: sectorBoard(rows), all: weightedMove(big) };
  }, [rows]);
  const cells = useMemo<Cell[]>(() => m.sectors.map((s) => ({ key: s.sector, label: s.sector, sub: `${s.n} companies`, move: s.move, weight: s.cap, name: s.sector })), [m.sectors]);
  if (!m.n) return <section className="mk-card"><div className="mk-h"><h2>Market snapshot</h2></div><p className="mk-note">Market data is on its way.</p></section>;
  return (
    <section className="mk-card" aria-labelledby="mkSnap">
      <div className="mk-h"><div><h2 id="mkSnap">Market snapshot</h2><p>{m.n.toLocaleString("en-IN")} companies{m.all != null ? <> · cap-weighted move <b className={tone(m.all)}>{sgn(m.all)}</b></> : null}</p></div></div>
      <div className="mk-snap">
        <div>
          <div className="mk-label">Market breadth</div>
          <div className="mk-breadth" role="img" aria-label={`${m.adv} rising, ${m.dec} falling, ${m.flat} unchanged`}><i className="up" style={{ flex: m.adv || 0.01 }} /><i style={{ flex: Math.max(m.flat, 0.01) }} /><i className="down" style={{ flex: m.dec || 0.01 }} /></div>
          <div className="mk-bk"><span className="up">▲ {m.adv.toLocaleString("en-IN")} rising</span><span>{m.flat.toLocaleString("en-IN")} unchanged</span><span className="down">▼ {m.dec.toLocaleString("en-IN")} falling</span></div>
          <div className="mk-movers">
            <div><div className="mk-label">Top gainers</div>{m.up.map((r) => <Link key={r.symbol} to={`/stocks/${r.symbol}`}><b>{shortName(r)}</b><span className="up">{sgn(r.change_pct)}</span></Link>)}</div>
            <div><div className="mk-label">Top decliners</div>{m.down.map((r) => <Link key={r.symbol} to={`/stocks/${r.symbol}`}><b>{shortName(r)}</b><span className="down">{sgn(r.change_pct)}</span></Link>)}</div>
          </div>
        </div>
        <div>
          <div className="mk-label">Sectors today <Legend /></div>
          <HeatMap cells={cells} height={300} empty="Sector data is on its way." minLabel={70} logos={false} />
          <p className="mk-foot">Every sector, sized by total market value and coloured by its cap-weighted move today. Sectors are grouped from the exchange industry list; companies below ₹100 crore are left out.</p>
        </div>
      </div>
    </section>
  );
}

const BROAD = { id: "n50", label: "Nifty 50" } as const;

function IndexHeatmap({ rows }: { rows: Row[] }) {
  const members = useMembers().data?.indices;
  const logos = useSearchQuotes(true).data;
  const lm = useMemo(() => quoteMap(logos), [logos]);
  const pills = useMemo(() => [BROAD as { id: string; label: string }, ...CATEGORIES.flatMap((c) => c.pills.filter((p) => p.id !== "oilgas" && p.id !== "commodities" && p.id !== "mfg"))], []);
  const [sel, setSel] = useState<string>(BROAD.id);
  const res = useMemo(() => {
    if (sel === BROAD.id) {
      const list = members?.NIFTY50;
      if (list && list.length >= 20) { const by = new Map(rows.map((r) => [r.symbol, r])); return { stocks: list.map((s) => by.get(s)).filter((r): r is Row => !!r && (r.price ?? 0) > 0 && r.change_pct != null), basis: "exchange list" as const }; }
      return { stocks: largest(rows, 50), basis: "market cap" as const };
    }
    const p = CATEGORIES.flatMap((c) => c.pills).find((x) => x.id === sel) as Pill;
    return stocksFor(p, rows, members);
  }, [sel, rows, members]);
  const cells = useMemo<Cell[]>(() => res.stocks.slice(0, 60).map((r) => ({ key: r.symbol, label: r.symbol, sub: "", move: r.change_pct, weight: r.market_cap as number, href: `/stocks/${r.symbol}`, logo: lm.get(r.symbol)?.logo, name: r.name || r.symbol })), [res, lm]);
  const mv = weightedMove(res.stocks);
  return (
    <section className="mk-card" aria-labelledby="mkHeat">
      <div className="mk-h"><div><h2 id="mkHeat">Heatmap</h2><p>Stocks of an index, sized by market cap, coloured by today's move</p></div><Legend /></div>
      <div className="mk-pills scroll" role="radiogroup" aria-label="Index">{pills.map((p) => <button key={p.id} type="button" role="radio" aria-checked={sel === p.id} className={sel === p.id ? "on" : ""} onClick={() => setSel(p.id)}>{p.label}</button>)}</div>
      <HeatMap cells={cells} height={420} empty="No traded stocks for this group yet." />
      <p className="mk-foot">{res.basis === "exchange list" ? "Constituents from the exchange's published index list." : res.basis === "market cap" ? "The exchange's constituent list is not loaded yet, so this shows the 50 largest listed companies by market cap (not the official index)." : "The exchange's constituent list is not loaded yet, so companies are grouped by FinLit's sector classification (not the official index)."}
        {cells.length ? ` ${cells.length} stocks${mv != null ? ` · cap-weighted move ${sgn(mv)}` : ""}.` : ""} Tile area is market capitalisation.</p>
    </section>
  );
}

// ---------------------------------------------------------------------------------------------------------------- sectoral activity
function Sectoral({ rows }: { rows: Row[] }) {
  const members = useMembers().data?.indices;
  const idx = useIndices().data?.items;
  const logos = useSearchQuotes(true).data, lm = useMemo(() => quoteMap(logos), [logos]);
  const [cat, setCat] = useState(CATEGORIES[0].id), [pillId, setPillId] = useState(CATEGORIES[0].pills[0].id), [tab, setTab] = useState<"g" | "l">("g"), [openMenu, setOpenMenu] = useState(false);
  const c = CATEGORIES.find((x) => x.id === cat)!, pill = c.pills.find((p) => p.id === pillId) || c.pills[0];
  const row = indexFor(idx, pill), { stocks, basis } = useMemo(() => stocksFor(pill, rows, members), [pill, rows, members]);
  const list = tab === "g" ? gainers(stocks, 8) : losers(stocks, 8), mv = row?.changePct ?? weightedMove(stocks);
  const menu = useRef<HTMLDivElement>(null);
  useEffect(() => { if (!openMenu) return; const f = (e: MouseEvent) => { if (!menu.current?.contains(e.target as Node)) setOpenMenu(false); }; const k = (e: KeyboardEvent) => { if (e.key === "Escape") setOpenMenu(false); }; document.addEventListener("mousedown", f); document.addEventListener("keydown", k); return () => { document.removeEventListener("mousedown", f); document.removeEventListener("keydown", k); }; }, [openMenu]);
  return (
    <section className="mk-card" aria-labelledby="mkSect">
      <div className="mk-h"><div><h2 id="mkSect">Sectoral activity</h2><p>Pick a sector group; see its index and the stocks moving it</p></div>
        <div className="mk-dd" ref={menu}><button type="button" aria-haspopup="listbox" aria-expanded={openMenu} onClick={() => setOpenMenu((v) => !v)}>{c.label}<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 6l5 5 5-5" /></svg></button>
          {openMenu && <div className="mk-dd-m" role="listbox" aria-label="Sector categories"><div className="mk-dd-t">Sector categories</div>{CATEGORIES.map((x) => <button key={x.id} type="button" role="option" aria-selected={x.id === cat} className={x.id === cat ? "on" : ""} onClick={() => { setCat(x.id); setPillId(x.pills[0].id); setOpenMenu(false); }}>{x.label}</button>)}</div>}</div></div>
      <div className="mk-pills scroll" role="radiogroup" aria-label="Index in this group">{c.pills.map((p) => <button key={p.id} type="button" role="radio" aria-checked={pill.id === p.id} className={pill.id === p.id ? "on" : ""} onClick={() => setPillId(p.id)}>{p.label}</button>)}</div>
      <div className="mk-ix">
        <div><small>{row?.name ?? pill.label}</small><b>{row?.close != null ? nf(row.close) : MINUS}</b></div>
        <div className={"mk-ix-c " + tone(mv)}>{row?.points != null && <span>{row.points > 0 ? "+" : row.points < 0 ? MINUS : ""}{nf(Math.abs(row.points))}</span>}<span>{mv != null ? (mv > 0 ? "▲ " : mv < 0 ? "▼ " : "") + sgn(mv) : MINUS}</span></div>
        <em>{row?.date ? `${dateIN(row.date)} close` : row ? "" : "Index level not in the feed; the move shown is the cap-weighted move of its stocks."}</em>
      </div>
      <div className="mk-tabs" role="tablist"><button type="button" role="tab" aria-selected={tab === "g"} className={tab === "g" ? "on" : ""} onClick={() => setTab("g")}>Gainers</button><button type="button" role="tab" aria-selected={tab === "l"} className={tab === "l" ? "on" : ""} onClick={() => setTab("l")}>Losers</button></div>
      {list.length ? <div className="mk-cards" role="tabpanel">{list.map((r) => <Link key={r.symbol} to={`/stocks/${r.symbol}`} className="mk-sc"><Logo src={lm.get(r.symbol)?.logo} name={r.name || r.symbol} kind="stock" size={34} /><b>{r.symbol}</b><span>₹{nf(r.price as number)}</span><em className={tone(r.change_pct)}>{sgn(r.change_pct)} </em></Link>)}</div>
        : <p className="mk-note">{stocks.length ? `No ${tab === "g" ? "gainers" : "losers"} in this group today.` : "No traded stocks for this group yet."}</p>}
      <p className="mk-foot">{basis === "exchange list" ? "Stocks from the exchange's published index list." : "The exchange's constituent list is not loaded yet; stocks are grouped by FinLit's sector classification (not the official index). The index level and move above are the exchange's own."} <Link to="/screener">Open the screener</Link></p>
    </section>
  );
}

export function MarketsBlock({ rows }: { rows: Row[] }) {
  return (
    <div className="mk-block" aria-label="Markets">
      <MarketToday />
      <Snapshot rows={rows} />
      <FlowsPanel />
      <IndexHeatmap rows={rows} />
      <Sectoral rows={rows} />
    </div>
  );
}
