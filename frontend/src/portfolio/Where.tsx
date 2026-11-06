import { useMemo } from "react";
import { bandInk, bandVar, scoreBand } from "../lib/scoreBands";
import { type Model, type OverviewHolding, scoreOf } from "../lib/portfolioOverview";
import { MINUS, cellShare, pct, plural, readingsFor, sectorOrder, squarify, type Rect } from "./derive";
import { SIZES_NOTE } from "./words";
import type { Meta, Mode, PageObject, SizeCode } from "./types";

type Common = { page: PageObject; meta: Record<string, Meta>; symbols: string[]; mode: Mode; colors: Record<string, string>; model: Model; ov: Map<string, OverviewHolding> };
const SIZES: SizeCode[] = ["L", "M", "S"];
const SIZE_HEAD: Record<SizeCode, string> = { L: "Large cap", M: "Mid cap", S: "Small cap", U: "Size not known" };
const shade = (p: number) => (p <= 0 ? undefined : { background: `color-mix(in srgb, var(--gold) ${Math.round(14 + 40 * Math.min(p, 50) / 50)}%, var(--s1))` });
const sectorName = (s: string) => s.replace(/ \(not classified\)$/, "");
const sectorNote = (s: string) => (/\(not classified\)$/.test(s) ? " (no NSE sector yet)" : "");

function Dot({ v, size = 8 }: { v: number | null; size?: number }) {
  return <i className="pfx-dot" style={{ width: size, height: size, background: bandVar(scoreBand(v)) }} aria-hidden="true" />;
}

/** Sector by size table for short lists: every share is a chip coloured by its score; darker cells hold more of the list. */
export function HeatTable({ page, meta, symbols, mode, colors, model, ov }: Common) {
  const secs = useMemo(() => sectorOrder(page, mode), [page, mode]);
  const cols: SizeCode[] = page.size_count.U ? [...SIZES, "U"] : SIZES;
  const by = (sec: string, sz: SizeCode) => symbols.filter((s) => (meta[s]?.sector || `${s} (not classified)`) === sec && meta[s]?.size === sz);
  const val = (s: string) => scoreOf(ov.get(s), model).value;
  return (
    <div className="pfx-heat" role="table" aria-label="Where your list sits: sector and size">
      <div className="pfx-heat-r pfx-heat-h" role="row" style={{ "--cols": cols.length } as React.CSSProperties}>
        <span role="columnheader">Sector</span>{cols.map((c) => <span role="columnheader" key={c}><span className="pfx-long">{SIZE_HEAD[c]}</span><span className="pfx-compact">{c}</span></span>)}<span role="columnheader"><span className="pfx-long">Of the list</span><span className="pfx-compact">List</span></span>
      </div>
      {secs.map((sec) => { const total = page.sector_weight[mode][sec] ?? 0; return (
        <div className="pfx-heat-r" role="row" key={sec} style={{ "--cols": cols.length } as React.CSSProperties}>
          <span className="pfx-sec" role="rowheader"><i className="pfx-dot" style={{ background: colors[sec] }} aria-hidden="true" /><span title={sectorName(sec) + sectorNote(sec)}>{sectorName(sec)}</span></span>
          {cols.map((sz) => { const list = by(sec, sz), p = cellShare(page, mode, list); return (
            <span className="pfx-cell" role="cell" key={sz} style={shade(p)}>
              <span className="pfx-chips">{list.map((s) => <span className="pfx-chip" key={s} title={`${meta[s]?.name ?? s}: ${val(s) == null ? "no score yet" : Math.round(val(s)!)}`}><Dot v={val(s)} /><span className="t">{s}</span></span>)}</span>
              {list.length > 0 && <small>{pct(p)}</small>}
            </span>); })}
          <span className="pfx-share" role="cell"><b>{pct(total)}</b><span className="pfx-bar"><i style={{ width: `${Math.min(100, total * 2)}%` }} /></span></span>
        </div>); })}
      <div className="pfx-heat-r pfx-heat-t" role="row" style={{ "--cols": cols.length } as React.CSSProperties}>
        <span role="rowheader">All sectors</span>
        {cols.map((sz) => { const n = page.size_count[sz] || 0; return <span role="cell" key={sz}><span><b>{plural(n, "share")}</b> · {pct(page.size_weight[mode][sz] ?? 0)}</span></span>; })}
        <span role="cell"><b>100%</b></span>
      </div>
    </div>
  );
}

/** The Prism (or FinLit IQ) colour mix and the average of each part: the two side cards of the short layout. */
export function MixCards({ lines, model, parts }: { lines: { v: number | null }[]; model: Model; parts: { label: string; value: number | null }[] }) {
  const mix = { hi: 0, mid: 0, lo: 0 };
  lines.forEach((l) => { if (l.v != null) mix[scoreBand(l.v) as "hi" | "mid" | "lo"]++; });
  const max = Math.max(1, mix.hi, mix.mid, mix.lo), name = model === "prism" ? "Prism" : "FinLit IQ";
  return (
    <div className="pfx-stack">
      <section className="pfx-card" aria-labelledby="pfx-mix"><h2 id="pfx-mix">{name} score mix</h2>
        {([["hi", "Green, 70+"], ["mid", "Orange, 50–69"], ["lo", "Red, under 50"]] as const).map(([b, l]) => (
          <div className="pfx-mixrow" key={b}><span>{l}</span><span className="pfx-bar"><i style={{ width: `${(mix[b] / max) * 100}%`, background: bandVar(b) }} /></span><b>{mix[b]}</b></div>))}</section>
      <section className="pfx-card" aria-labelledby="pfx-avg"><h2 id="pfx-avg">Average by {name} {model === "prism" ? "part" : "pillar"}</h2>
        {parts.map((p) => (<div className="pfx-mixrow" key={p.label}><span>{p.label}</span><span className="pfx-bar"><i style={{ width: `${p.value ?? 0}%`, background: bandVar(scoreBand(p.value)) }} /></span><b>{p.value == null ? MINUS : Math.round(p.value)}</b></div>))}
        <p className="pfx-fine">Each share counts once.{model === "prism" ? " A high Risk score means lower risk. Scores use FinLit Prism." : " Scores use the FinLit IQ."}</p></section>
    </div>
  );
}

/** Long lists: one block per sector, one tile per share, area = share of the list, colour = score band. */
export function Treemap({ page, meta, symbols, mode, colors, model, ov }: Common) {
  const W = 100, H = 62;
  const blocks = useMemo(() => {
    const w = page.share_weight[mode];
    const secs = sectorOrder(page, mode);
    const items = secs.map((sec) => ({ value: page.sector_weight[mode][sec] ?? 0, data: sec }));
    return squarify(items, { x: 0, y: 0, w: W, h: H }).map((b) => {
      const mem = symbols.filter((s) => (meta[s]?.sector || `${s} (not classified)`) === b.data).sort((x, y) => (w[y] ?? 0) - (w[x] ?? 0));
      const inner: Rect = { x: 0, y: 0, w: b.w, h: Math.max(1, b.h - 3.2) };
      return { ...b, tiles: squarify(mem.map((s) => ({ value: w[s] ?? 0, data: s })), inner) };
    });
  }, [page, meta, symbols, mode]);
  const w = page.share_weight[mode];
  return (
    <div className="pfx-tree" role="group" aria-label="Where your list sits: each block is a sector, each tile a share" style={{ aspectRatio: `${W} / ${H}` }}>
      {blocks.map((b) => (
        <div className="pfx-tb" key={b.data} style={{ left: `${(b.x / W) * 100}%`, top: `${(b.y / H) * 100}%`, width: `${(b.w / W) * 100}%`, height: `${(b.h / H) * 100}%` }}>
          <div className="pfx-tb-in">
            <div className="pfx-tb-h" title={`${sectorName(b.data)}${sectorNote(b.data)}: ${pct(page.sector_weight[mode][b.data] ?? 0)}`}><i className="pfx-dot" style={{ background: colors[b.data] }} aria-hidden="true" /><b>{sectorName(b.data)}</b><span>{pct(page.sector_weight[mode][b.data] ?? 0)}</span></div>
            <div className="pfx-tb-t">{b.tiles.map((t) => { const v = scoreOf(ov.get(t.data), model).value, band = scoreBand(v), big = t.w * t.h > 40; return (
              <span key={t.data} className={"pfx-tile b-" + band} title={`${meta[t.data]?.name ?? t.data} · ${pct(w[t.data] ?? 0)} of the list · ${v == null ? "no score yet" : Math.round(v)}`}
                style={{ left: `${(t.x / b.w) * 100}%`, top: `${(t.y / Math.max(1, b.h - 3.2)) * 100}%`, width: `${(t.w / b.w) * 100}%`, height: `${(t.h / Math.max(1, b.h - 3.2)) * 100}%`, color: bandInk(band) }}>
                <span className="pfx-tile-in"><b>{big || t.w > 7 ? t.data : ""}</b>{big && <em>{v == null ? MINUS : Math.round(v)}</em>}</span></span>); })}</div>
          </div>
        </div>))}
    </div>
  );
}

/** Long lists: how many shares sit in each sector and size band (a count table with the share of the list in the foot). */
export function CountTable({ page, meta, symbols, mode, colors }: Pick<Common, "page" | "meta" | "symbols" | "mode" | "colors">) {
  const secs = sectorOrder(page, mode);
  const cols: SizeCode[] = page.size_count.U ? [...SIZES, "U"] : SIZES;
  const maxN = Math.max(1, ...secs.flatMap((sec) => cols.map((sz) => symbols.filter((s) => (meta[s]?.sector || `${s} (not classified)`) === sec && meta[s]?.size === sz).length)));
  return (
    <aside className="pfx-card pfx-side" aria-labelledby="pfx-ct">
      <h2 id="pfx-ct">Sector and size</h2><p className="pfx-note">Number of shares in each cell. Darker cells contain more of the list.</p>
      <table className="pfx-ct"><thead><tr><th>Sector</th>{cols.map((c) => <th key={c}>{c === "U" ? "?" : SIZE_HEAD[c].replace(" cap", "")}</th>)}</tr></thead>
        <tbody>{secs.map((sec) => <tr key={sec}><th scope="row"><i className="pfx-dot" style={{ background: colors[sec] }} aria-hidden="true" /><span title={sectorName(sec)}>{sectorName(sec)}</span></th>
          {cols.map((sz) => { const n = symbols.filter((s) => (meta[s]?.sector || `${s} (not classified)`) === sec && meta[s]?.size === sz).length; return <td key={sz} style={n ? shade((n / maxN) * 50) : undefined}>{n || ""}</td>; })}</tr>)}</tbody>
        <tfoot><tr><th scope="row">All · share of list</th>{cols.map((sz) => <td key={sz}><b>{page.size_count[sz] || 0}</b><small>{pct(page.size_weight[mode][sz] ?? 0)}</small></td>)}</tr></tfoot></table>
      <p className="pfx-fine">{SIZES_NOTE}</p>
    </aside>
  );
}

export function WhereReadings({ page, mode }: { page: PageObject; mode: Mode }) {
  const r = readingsFor(page, mode, "where");
  const text = r.map((x) => x.text).slice(0, 2).join(" ");
  return <p className="pfx-line">{text || "No sector or share stands out by size."}</p>;
}
