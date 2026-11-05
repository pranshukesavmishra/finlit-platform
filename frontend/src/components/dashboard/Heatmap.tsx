// Block 7, Index heatmap (the old Heatmap and Sectoral activity merged): a Map or a List of an index's stocks. Tile size is market value, colour is today's move (white text at 4.5:1);
// a tile too small for its ticker at 11px shows no label, and hover, focus or tap gives the details.
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { MINUS, nf } from "../../lib/format";
import { CATEGORIES, largest, stocksFor, treemap, useMembers, weightedMove, type Pill } from "../../lib/markets";
import { tileColour, tileLabel, TILE_COLOURS } from "../../lib/dashboard";
import type { Row } from "../../lib/screener";
import { Card, Seg, tone, useIsPhone, useWidth } from "./parts";

type Cell = { symbol: string; name: string; move: number | null; cap: number; price: number | null };
const sgn = (v: number | null | undefined, d = 2) => (v == null ? MINUS : (v > 0 ? "+" : v < 0 ? MINUS : "") + nf(Math.abs(v), d) + "%");
const BROAD = { id: "n50", label: "Nifty 50" };
const MAIN = ["bank", "it", "auto", "pharma", "fmcg", "metal"];
const ALL_PILLS: Pill[] = CATEGORIES.flatMap((c) => c.pills);

function HeatTiles({ cells, h }: { cells: Cell[]; h: number }) {
  const [box, W] = useWidth<HTMLDivElement>();
  const tiles = useMemo(() => treemap(cells, (c) => Math.max(c.cap, 1), W, h), [cells, W, h]);
  const [tip, setTip] = useState<{ c: Cell; x: number; y: number; pinned: boolean } | null>(null);
  const show = (c: Cell, el: HTMLElement, pinned: boolean, e?: React.PointerEvent) => {
    const r = (el.closest(".dsh-map") as HTMLElement).getBoundingClientRect(), t = el.getBoundingClientRect();
    setTip({ c, x: e ? e.clientX - r.left : t.left - r.left + t.width / 2, y: e ? e.clientY - r.top : t.top - r.top, pinned });
  };
  return (
    <div className="dsh-map" ref={box} style={{ height: h }} role="list" aria-label="Heat map: tile size is market value, colour is today's move" onPointerLeave={() => setTip((t) => (t?.pinned ? t : null))}>
      {tiles.map(({ x, y, w, h: th, item: c }) => {
        const lab = tileLabel(c.symbol, w, th);
        const style = { left: x, top: y, width: w, height: th, background: tileColour(c.move) } as React.CSSProperties;
        const aria = `${c.name}: ${sgn(c.move)} today`;
        const hover = { onPointerEnter: (e: React.PointerEvent<HTMLElement>) => e.pointerType === "mouse" && show(c, e.currentTarget, false, e), onFocus: (e: React.FocusEvent<HTMLElement>) => show(c, e.currentTarget, false) };
        if (!lab) return <button key={c.symbol} type="button" role="listitem" className="t" style={style} aria-label={aria} {...hover} onClick={(e) => show(c, e.currentTarget, true)} />;
        return <Link key={c.symbol} to={`/stocks/${c.symbol}`} role="listitem" className="t" style={style} aria-label={aria} {...hover}><b style={{ fontSize: lab.size }}>{c.symbol}</b>{lab.pct && <em>{sgn(c.move)}</em>}</Link>;
      })}
      {tip && <div className="dsh-htip" role="status" style={{ left: Math.max(8, Math.min(W - 196, tip.x + 12)), top: Math.max(4, Math.min(h - 96, tip.y + 12)) }}>
        <b>{tip.c.symbol}</b><small>{tip.c.name}</small><span>{tip.c.price != null ? "₹" + nf(tip.c.price) : "No price"} · <i className={tone(tip.c.move)}>{sgn(tip.c.move)}</i></span>
        {tip.c.cap > 0 && <small>Market value ₹{Math.round(tip.c.cap).toLocaleString("en-IN")} Cr</small>}
        {tip.pinned && <Link to={`/stocks/${tip.c.symbol}`}>Open {tip.c.symbol} →</Link>}</div>}
    </div>
  );
}

type Key = "symbol" | "price" | "move";
function List({ cells }: { cells: Cell[] }) {
  const [by, setBy] = useState<Key>("move"), [dir, setDir] = useState<1 | -1>(-1);
  const rows = useMemo(() => [...cells].sort((a, b) => (by === "symbol" ? a.symbol.localeCompare(b.symbol) : ((a[by === "price" ? "price" : "move"] ?? -Infinity) as number) - ((b[by === "price" ? "price" : "move"] ?? -Infinity) as number)) * dir), [cells, by, dir]);
  const head = (k: Key, l: string, cls = "") => <button type="button" className={cls + (by === k ? " on" : "")} aria-label={`Sort by ${l}`} onClick={() => (k === by ? setDir((d) => (d === 1 ? -1 : 1)) : (setBy(k), setDir(k === "symbol" ? 1 : -1)))}>{l}{by === k ? (dir === 1 ? " ↑" : " ↓") : ""}</button>;
  return (
    <div className="dsh-hl" role="table" aria-label="Stocks of the index">
      <div className="h" role="row"><span role="columnheader">{head("symbol", "Ticker")}</span><span role="columnheader" className="r">{head("price", "Price", "r")}</span><span role="columnheader" className="r">{head("move", "Today", "r")}</span></div>
      {rows.map((c) => <Link key={c.symbol} to={`/stocks/${c.symbol}`} className="row" role="row"><span role="cell"><b>{c.symbol}</b><small>{c.name !== c.symbol ? c.name : ""}</small></span><span role="cell" className="r">{c.price != null ? "₹" + nf(c.price) : "—"}</span><span role="cell" className={"r " + tone(c.move)}>{sgn(c.move)}</span></Link>)}
    </div>
  );
}

export function IndexHeatmap({ rows, loading }: { rows: Row[]; loading: boolean }) {
  const members = useMembers().data?.indices, phone = useIsPhone();
  const [sel, setSel] = useState(BROAD.id), [view, setView] = useState<"map" | "list">("map"), [more, setMore] = useState(false);
  const res = useMemo(() => {
    if (sel === BROAD.id) {
      const list = members?.NIFTY50;
      if (list && list.length >= 20) { const by = new globalThis.Map(rows.map((r) => [r.symbol, r])); return { stocks: list.map((s) => by.get(s)).filter((r): r is Row => !!r && (r.price ?? 0) > 0 && r.change_pct != null), basis: "list" as const }; }
      return { stocks: largest(rows, 50), basis: "cap" as const };
    }
    return stocksFor(ALL_PILLS.find((p) => p.id === sel)!, rows, members);
  }, [sel, rows, members]);
  const cells = useMemo<Cell[]>(() => res.stocks.slice(0, 60).map((r) => ({ symbol: r.symbol, name: r.name || r.symbol, move: r.change_pct, cap: r.market_cap ?? 0, price: r.price })), [res]);
  const mv = weightedMove(res.stocks);
  const main = [BROAD, ...MAIN.map((id) => ALL_PILLS.find((p) => p.id === id)!).filter(Boolean)], rest = ALL_PILLS.filter((p) => !MAIN.includes(p.id));
  const basis = res.basis === "list" ? "Constituents from the exchange's published index list." : res.basis === "cap" ? "The exchange's constituent list is not loaded yet, so this shows the 50 largest listed companies by market value (not the official index)." : "The exchange's constituent list is not loaded yet, so companies are grouped by FinLit's sector classification (not the official index).";
  return (
    <Card id="heatmap" title="Index heatmap" sub="Tile size is market value, colour is today's move" right={<Seg label="View" value={view} options={[["map", "Map"], ["list", "List"]] as const} onChange={setView} />}>
      <div className="dsh-chips" role="group" aria-label="Index">
        {main.map((p) => <button key={p.id} type="button" aria-pressed={sel === p.id} onClick={() => setSel(p.id)}>{p.label}</button>)}
        <span className="dsh-menu"><button type="button" aria-haspopup="listbox" aria-expanded={more} aria-pressed={rest.some((p) => p.id === sel)} onClick={() => setMore(!more)}>{rest.find((p) => p.id === sel)?.label ?? "More indices"} ▾</button>
          {more && <div className="pop" role="listbox" aria-label="More indices">{rest.map((p) => <button key={p.id} type="button" role="option" aria-selected={sel === p.id} onClick={() => { setSel(p.id); setMore(false); }}>{p.label}</button>)}</div>}</span>
      </div>
      {loading ? <div className="skeleton" style={{ height: phone ? 300 : 420, borderRadius: 12 }} aria-busy="true" /> : !cells.length ? <p className="dsh-note">No traded stocks for this group today. {basis}</p> : view === "map" ? <HeatTiles cells={cells} h={phone ? 320 : 420} /> : <List cells={cells} />}
      <div className="dsh-hfoot"><span>{cells.length ? `${cells.length} stocks${mv != null ? ` · cap-weighted move ${sgn(mv)}` : ""} · hover or tap a tile for price and detail. ` : ""}{basis}</span>
        <span className="dsh-legend" aria-hidden="true">−2% {TILE_COLOURS.map((c) => <i key={c} style={{ background: c }} />)} +2%</span></div>
    </Card>
  );
}
