import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { Icon } from "../lib/icons";
import { HScroll } from "../components/HScroll";
import { SectionHead } from "./Sections";
import { Plain } from "../components/Plain";
import {
  LABEL_WORD, monthYear, ordinal, pts, rankStory, relativeSentence, tone, useLeadership, useLeadershipHistory,
  type Direction, type LeadHistory, type LeadLabel, type LeadPeer, type LeadRun, type LeadershipOn, type Reliability,
} from "../lib/leadership";

/** Leader / In line / Laggard. Describes past relative price performance only; never a recommendation. */
export const LEAD_NOTE = "Describes past performance; not a recommendation.";
const EXPLAINER = "/leadership-label";

function useWidth<T extends HTMLElement>(): [(el: T | null) => void, number] {
  const [w, setW] = useState(640);
  const ro = useRef<ResizeObserver | null>(null);
  const ref = (el: T | null) => {
    ro.current?.disconnect();
    if (!el) return;
    setW(Math.max(260, Math.round(el.getBoundingClientRect().width) || 640));
    if (typeof ResizeObserver === "undefined") return;
    ro.current = new ResizeObserver(([e]) => setW(Math.max(260, Math.round(e.contentRect.width))));
    ro.current.observe(el);
  };
  useEffect(() => () => ro.current?.disconnect(), []);
  return [ref, w];
}

const dirWord = (d: Direction) => (d === "gaining" ? "gaining over 3 months" : d === "weakening" ? "weakening over 3 months" : "");

/* ------------------------------------------------------------------ chip + tooltip */
export function LeadChip({ label, onClick, title }: { label: LeadLabel; onClick?: () => void; title?: string }) {
  const body = <><i className="ld-dot" aria-hidden="true" />{LABEL_WORD[label]}</>;
  return onClick
    ? <button type="button" className={"ld-chip " + label} onClick={onClick} title={title} aria-label={`${LABEL_WORD[label]}. Show the peer ranking`}>{body}</button>
    : <span className={"ld-chip " + label}>{body}</span>;
}

function LeadTip({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", away); document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", away); document.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <span className="ld-tipw" ref={box} onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button type="button" className="info" aria-label="What does this label mean?" aria-expanded={open} onClick={() => setOpen((o) => !o)} onFocus={() => setOpen(true)}>i</button>
      {open && <span className="ld-tip" role="tooltip">{text} <Link to={EXPLAINER} onClick={() => setOpen(false)}>How this works</Link></span>}
    </span>
  );
}

/* ------------------------------------------------------------------ 1. the line under the company name */
export function LeadLine({ symbol, jump }: { symbol: string; jump: (id: string) => void }) {
  const q = useLeadership(symbol);
  const d = q.data;
  if (q.isLoading || !d) return <div className="ld-line ld-wait" aria-hidden="true" />;
  if (!d.available) return <div className="ld-line"><span className="ld-empty" role="note">{d.display.line}</span></div>;
  const parts = d.display.parts;
  return (
    <div className="ld-line">
      <div className="ld-row">
        <span className="ld-a">
          <LeadChip label={d.label} onClick={() => jump("peers")} />
          <span className="ld-rank">{parts?.rank || d.display.line}</span>
        </span>
        {parts && (
          <span className="ld-b">
            <button type="button" className="ld-fig" onClick={() => jump("leadership")}><b className={"pt " + tone(parts.sector.v)}>{parts.sector.pts} pts</b> vs {parts.sector.name}</button>
            {parts.market && <button type="button" className="ld-fig" onClick={() => jump("leadership")}><b className={"pt " + tone(parts.market.v)}>{parts.market.pts} pts</b> vs {parts.market.name}</button>}
            <span className="ld-win">(12 months)</span>
            {parts.direction && <span className={"ld-dir " + parts.direction}>{parts.direction === "gaining" ? "▲" : "▼"} {dirWord(parts.direction)}</span>}
          </span>
        )}
        <LeadTip text={d.display.tooltip || ""} />
      </div>
      {d.display.note && <div className="ld-caution" role="note"><Icon name="alert" /><span>{d.display.note}</span></div>}
      {d.stale && <div className="ld-stale" role="note">Last updated {monthYear(d.asOf)}; this week's refresh has not come through yet.</div>}
      {d.display.benchmarkNote && <div className="ld-stale" role="note">{d.display.benchmarkNote}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ 2. the peer ranking table (Peers section) */
type Row = { symbol: string; name: string; rank: number | null; label: LeadLabel | null; direction: Direction; rel52: number | null; rel13: number | null; rel52Market: number | null };
type SortKey = "rank" | "name" | "rel52" | "rel13" | "rel52Market";

export function PeerRanking({ lead, self, extras }: { lead: LeadershipOn; self: string; extras: { symbol: string; name: string | null }[] }) {
  const nav = useNavigate();
  const [key, setKey] = useState<SortKey>("rank");
  const [dir, setDir] = useState<1 | -1>(1);
  const [all, setAll] = useState(false);
  const rows = useMemo<Row[]>(() => {
    const ranked: Row[] = lead.peers.map((p) => ({ symbol: p.symbol, name: p.name || p.symbol, rank: p.rank, label: p.label, direction: p.direction, rel52: p.rel52, rel13: p.rel13, rel52Market: p.rel52Market }));
    const seen = new Set(ranked.map((r) => r.symbol));
    const rest: Row[] = extras.filter((e) => !seen.has(e.symbol) && e.symbol !== self).map((e) => ({ symbol: e.symbol, name: e.name || e.symbol, rank: null, label: null, direction: null, rel52: null, rel13: null, rel52Market: null }));
    const val = (r: Row): number | string => (key === "name" ? r.name.toLowerCase() : key === "rank" ? (r.rank ?? 1e9) : ((r[key] as number | null) ?? -1e9));
    const base = key === "rank" || key === "name" ? 1 : -1;   // the number columns open best-first
    ranked.sort((a, b) => { const x = val(a), y = val(b); return (x < y ? -1 : x > y ? 1 : a.symbol.localeCompare(b.symbol)) * dir * base; });
    return [...ranked, ...rest];   // stocks without a year of prices stay at the bottom whatever the sort
  }, [lead, extras, key, dir, self]);
  const sort = (k: SortKey) => { if (k === key) setDir((d) => (d === 1 ? -1 : 1)); else { setKey(k); setDir(1); } };
  const LIMIT = 12;
  const shown = all ? rows : rows.filter((r, i) => i < LIMIT || r.symbol === self);
  const th = (k: SortKey, text: string, cls = "") => (
    <th scope="col" className={cls} aria-sort={key === k ? (dir === 1 ? "ascending" : "descending") : "none"}>
      <button type="button" onClick={() => sort(k)}>{text}<span aria-hidden="true">{key === k ? (dir === 1 ? " ↑" : " ↓") : ""}</span></button>
    </th>
  );
  return (
    <div className="card acc ld-rank-card" style={{ "--ac": "var(--gold)", marginTop: 16 } as React.CSSProperties}>
      <div className="card-h"><h3><span className="ci"><Icon name="layers" /></span>How it ranks among {lead.peerGroup.ranked} {lead.peerGroup.short} peers</h3><span className="s">12-month return against {lead.benchmarks.sector.name}</span></div>
      <HScroll label="peer ranking">
        <table className="ld-tbl">
          <caption className="sr-only">Peers ranked by their 12-month return against {lead.benchmarks.sector.name}. Status is given in words.</caption>
          <thead><tr>{th("rank", "#", "n")}{th("name", "Company")}<th scope="col">Status</th>{th("rel52", "vs sector, 12M", "r")}{th("rel13", "vs sector, 3M", "r")}{th("rel52Market", "vs market, 12M", "r")}</tr></thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.symbol} className={(r.symbol === self ? "me " : "") + (r.label ? "" : "none")} onClick={() => r.symbol !== self && nav(`/stocks/${r.symbol}`)} aria-current={r.symbol === self ? "true" : undefined}>
                <td className="n">{r.rank ?? "—"}</td>
                <th scope="row" className="nm">{r.symbol === self ? <b>{r.name}<span className="you"> · this company</span></b> : <Link to={`/stocks/${r.symbol}`} onClick={(e) => e.stopPropagation()}>{r.name}</Link>}<span className="tk">{r.symbol}</span></th>
                <td>{r.label ? <><LeadChip label={r.label} />{r.direction && <span className={"ld-dir ld-dsm " + r.direction} title={dirWord(r.direction)}>{r.direction === "gaining" ? "▲" : "▼"}<span className="sr-only"> {dirWord(r.direction)}</span></span>}</> : <span className="ld-nh">Not enough history</span>}</td>
                <td className="r"><Pt v={r.rel52} /></td><td className="r"><Pt v={r.rel13} /></td><td className="r"><Pt v={r.rel52Market} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </HScroll>
      {rows.length > LIMIT && <button type="button" className="btn ld-more" onClick={() => setAll((a) => !a)}>{all ? "Show fewer" : `Show all ${rows.length} companies`}</button>}
      <p className="ld-foot">{LEAD_NOTE} <Link to={EXPLAINER}>How this works</Link></p>
    </div>
  );
}

function Pt({ v }: { v: number | null }) {
  return v == null ? <span className="ld-nh">—</span> : <span className={"pt " + tone(v)}>{pts(v)}<small> pts</small></span>;
}

/* ------------------------------------------------------------------ 3. the section at the bottom of the page */
const RANGES = [["1Y", 52, "1 year"], ["3Y", 156, "3 years"], ["5Y", 260, "5 years"]] as const;

export function LeadershipSection({ symbol, name }: { symbol: string; name: string }) {
  const [seen, setSeen] = useState(false);
  const host = useRef<HTMLElement>(null);
  const lead = useLeadership(symbol).data;
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") { setSeen(true); return; }
    const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { setSeen(true); io.disconnect(); } }, { rootMargin: "600px 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  const hist = useLeadershipHistory(symbol, seen && !!lead?.available);
  return (
    <section className="block ld-sec" ref={host} style={{ "--sc": "var(--gold-deep)" } as React.CSSProperties}>
      <SectionHead id="leadership" no="Leadership" icon="medal" tier="basic" title="Where this stock stands among its peers" sub="How the last 12 months compare with the industry and the market, and whether that has meant anything here." color="--gold-deep" />
      {!lead ? <div className="skeleton" style={{ height: 220 }} aria-hidden="true" /> : !lead.available ? (
        <div className="card ld-emptycard"><p className="ld-empty" role="note">{lead.display.line}</p><p className="ld-foot">{LEAD_NOTE} <Link to={EXPLAINER}>How this works</Link></p></div>
      ) : (
        <>
          <Plain>{lead.display.line}. {lead.display.note ? lead.display.note + ". " : ""}A label like this is a snapshot, so below is how the stock got here and whether being ahead has lasted in this part of the market.</Plain>
          <div className="ld-grid">
            <RelativeStrength name={name} lead={lead} hist={hist.data} loading={hist.isLoading || !seen} />
            <RankHistory name={name} lead={lead} hist={hist.data} loading={hist.isLoading || !seen} />
            <ReliabilityCard lead={lead} />
            <StripPlot self={symbol} lead={lead} />
          </div>
          <p className="ld-foot">{LEAD_NOTE} Based on weekly prices, refreshed after each Friday's close. <Link to={EXPLAINER}>How this works</Link></p>
        </>
      )}
    </section>
  );
}

/* ---- shared bits */
function ChartTable({ caption, head, rows }: { caption: string; head: string[]; rows: (string | number)[][] }) {
  return (
    <div className="ld-table"><table><caption>{caption}</caption><thead><tr>{head.map((h) => <th key={h} scope="col">{h}</th>)}</tr></thead>
      <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => (j === 0 ? <th scope="row" key={j}>{c}</th> : <td key={j}>{c}</td>))}</tr>)}</tbody></table></div>
  );
}
function ShowTable({ on, set }: { on: boolean; set: (b: boolean) => void }) {
  return <button type="button" className="ld-link" aria-expanded={on} onClick={() => set(!on)}>{on ? "Hide table" : "Show as table"}</button>;
}
const dShort = (iso: string) => new Date(iso + "T00:00:00Z").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const path = (xs: number[], ys: (number | null)[]) => { let d = "", pen = false; xs.forEach((x, i) => { const y = ys[i]; if (y == null) { pen = false; return; } d += (pen ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1); pen = true; }); return d; };

/* ---- A. relative strength */
function RelativeStrength({ name, lead, hist, loading }: { name: string; lead: LeadershipOn; hist?: LeadHistory; loading: boolean }) {
  const [range, setRange] = useState<(typeof RANGES)[number]>(RANGES[1]);
  const [mkt, setMkt] = useState(true);
  const [table, setTable] = useState(false);
  const [hover, setHover] = useState<number | null>(null);
  const [box, W] = useWidth<HTMLDivElement>();
  const s = hist?.series;
  const hasSector = !!s?.sector && lead.benchmarks.sector.kind === "index";
  const hasMarket = !!s?.market && !!lead.benchmarks.market;
  const calc = useMemo(() => {
    if (!s) return null;
    const n = Math.min(range[1], s.dates.length), from = s.dates.length - n;
    const rebase = (bench: (number | null)[] | null) => {
      if (!bench) return null;
      const raw = s.stock.slice(from).map((v, i) => { const b = bench[from + i]; return v == null || b == null ? null : v / b; });
      const base = raw.find((v) => v != null);
      return base ? raw.map((v) => (v == null ? null : (v / base) * 100)) : null;
    };
    return { dates: s.dates.slice(from), sec: hasSector ? rebase(s.sector) : null, mk: hasMarket ? rebase(s.market) : null, n };
  }, [s, range, hasSector, hasMarket]);
  const lines = calc ? ([["sector", calc.sec, lead.benchmarks.sector.name], ...(mkt ? [["market", calc.mk, lead.benchmarks.market?.name || ""]] : [])] as [string, (number | null)[] | null, string][]).filter((l) => l[1]) : [];
  const H = W < 480 ? 230 : 280, M = { t: 14, r: W < 480 ? 96 : 150, b: 26, l: 40 };
  const vals = lines.flatMap((l) => (l[1] as (number | null)[]).filter((v): v is number => v != null)).concat(100);
  const lo = vals.length ? Math.min(...vals) : 90, hi = vals.length ? Math.max(...vals) : 110, pad = Math.max(2, (hi - lo) * 0.08);
  const y0 = lo - pad, y1 = hi + pad;
  const iw = W - M.l - M.r, ih = H - M.t - M.b;
  const X = (i: number) => M.l + (calc && calc.dates.length > 1 ? (i / (calc.dates.length - 1)) * iw : 0);
  const Y = (v: number) => M.t + (1 - (v - y0) / (y1 - y0)) * ih;
  const xs = calc ? calc.dates.map((_, i) => X(i)) : [];
  const first = lines[0];
  const lastOf = (a: (number | null)[] | null) => { if (!a) return null; for (let i = a.length - 1; i >= 0; i--) if (a[i] != null) return a[i]; return null; };
  const concl = first ? relativeSentence(name, first[2], lastOf(first[1]), range[2]) : `${name} against its benchmarks: not enough price history for a chart.`;
  const ticks = useMemo(() => { const k = 4, out: number[] = []; for (let i = 0; i <= k; i++) out.push(y0 + ((y1 - y0) * i) / k); return out; }, [y0, y1]);
  const yearTicks = calc ? calc.dates.map((d, i) => [d, i] as const).filter(([d, i], j, a) => i === 0 || d.slice(0, 4) !== a[j - 1][0].slice(0, 4)).filter((_, j, a) => a.length < 7 || j % Math.ceil(a.length / 6) === 0) : [];
  const move = (e: React.PointerEvent<SVGSVGElement>) => {
    if (!calc || calc.dates.length < 2) return;
    const r = e.currentTarget.getBoundingClientRect(), x = ((e.clientX - r.left) / r.width) * W;
    setHover(Math.max(0, Math.min(calc.dates.length - 1, Math.round(((x - M.l) / iw) * (calc.dates.length - 1)))));
  };
  const sample = calc ? Array.from({ length: Math.min(12, calc.dates.length) }, (_, k) => Math.round((k * (calc.dates.length - 1)) / Math.max(1, Math.min(12, calc.dates.length) - 1))) : [];
  const f1 = (v: number | null | undefined) => (v == null ? "—" : v.toFixed(1));
  return (
    <div className="card acc ld-card ld-ca" style={{ "--ac": "var(--ld-blue)" } as React.CSSProperties}>
      <div className="card-h"><h3><span className="ci"><Icon name="line" /></span>Relative strength</h3>
        <div className="seg" role="group" aria-label="Range">{RANGES.map((r) => <button key={r[0]} type="button" className={r === range ? "on" : ""} aria-pressed={r === range} onClick={() => setRange(r)}>{r[0]}</button>)}</div></div>
      <p className="ld-cap">Price divided by the index, set to 100 at the start. Above 100 means ahead of the index.</p>
      {hasMarket && <label className="ld-sw"><input type="checkbox" checked={mkt} onChange={(e) => setMkt(e.target.checked)} /> Show {lead.benchmarks.market?.name}</label>}
      <div ref={box} className="ld-chart">
        {loading ? <div className="skeleton" style={{ height: H }} aria-hidden="true" /> : !calc || !lines.length ? <p className="ld-empty">{lead.benchmarks.sector.kind === "peer_average" ? "There is no sector index for this industry, so there is no line to draw against it." : "The index history is not available right now."}</p> : (
          <>
            <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={concl} onPointerMove={move} onPointerLeave={() => setHover(null)} style={{ touchAction: "pan-y" }}>
              <defs>
                <clipPath id="ldUp"><rect x={M.l} y={M.t} width={iw} height={Math.max(0, Y(100) - M.t)} /></clipPath>
                <clipPath id="ldDn"><rect x={M.l} y={Y(100)} width={iw} height={Math.max(0, M.t + ih - Y(100))} /></clipPath>
              </defs>
              {ticks.map((t, i) => <g key={i}><line x1={M.l} x2={M.l + iw} y1={Y(t)} y2={Y(t)} className="ld-grid-l" /><text x={M.l - 6} y={Y(t) + 4} textAnchor="end" className="ld-ax">{Math.round(t)}</text></g>)}
              {calc.sec && <>
                <path d={path(xs, calc.sec.map((v) => (v == null ? null : Y(v)))) + `L${xs[xs.length - 1]} ${Y(100)}L${xs[0]} ${Y(100)}Z`} className="ld-up" clipPath="url(#ldUp)" />
                <path d={path(xs, calc.sec.map((v) => (v == null ? null : Y(v)))) + `L${xs[xs.length - 1]} ${Y(100)}L${xs[0]} ${Y(100)}Z`} className="ld-dn" clipPath="url(#ldDn)" />
              </>}
              <line x1={M.l} x2={M.l + iw} y1={Y(100)} y2={Y(100)} className="ld-base" />
              <text x={M.l + 4} y={Y(100) - 5} className="ld-ax strong">Level with the index</text>
              {lines.map(([k, a]) => <path key={k} d={path(xs, (a as (number | null)[]).map((v) => (v == null ? null : Y(v))))} className={"ld-ln " + k} />)}
              {lines.map(([k, a, nm]) => { const v = lastOf(a), i = (a as (number | null)[]).length - 1; return v == null ? null : <g key={k}><circle cx={X(i)} cy={Y(v)} r="3.5" className={"ld-end " + k} /><text x={X(i) + 8} y={Y(v) + 4} className={"ld-lab " + k}>{W < 480 ? `${f1(v)}` : `vs ${nm} ${f1(v)}`}</text></g>; })}
              {yearTicks.map(([d, i]) => <text key={d} x={X(i)} y={H - 6} textAnchor="middle" className="ld-ax">{W < 480 ? d.slice(2, 4) : monthYear(d)}</text>)}
              {hover != null && <g><line x1={X(hover)} x2={X(hover)} y1={M.t} y2={M.t + ih} className="ld-cross" />{lines.map(([k, a]) => { const v = (a as (number | null)[])[hover]; return v == null ? null : <circle key={k} cx={X(hover)} cy={Y(v)} r="4.5" className={"ld-end " + k} />; })}</g>}
            </svg>
            {hover != null && (
              <div className="ld-hov" style={{ left: Math.min(Math.max(8, X(hover) - 70), W - 160) }} aria-hidden="true">
                <b>{dShort(calc.dates[hover])}</b>{lines.map(([k, a, nm]) => { const v = (a as (number | null)[])[hover]; return <span key={k} className={"l " + k}>vs {nm}: {v == null ? "—" : `${pts((v - 100) / 100)} pts`}</span>; })}
              </div>
            )}
          </>
        )}
      </div>
      {calc && lines.length > 0 && <div className="ld-foot2"><span className="ld-key"><i className="up" />Ahead of the index</span><span className="ld-key"><i className="dn" />Behind the index</span><ShowTable on={table} set={setTable} /></div>}
      {table && calc && <ChartTable caption={concl} head={["Date", ...lines.map((l) => `Against ${l[2]} (100 at start)`)]} rows={sample.map((i) => [dShort(calc.dates[i]), ...lines.map((l) => f1((l[1] as (number | null)[])[i]))])} />}
    </div>
  );
}

/* ---- B. rank history */
function RankHistory({ name, lead, hist, loading }: { name: string; lead: LeadershipOn; hist?: LeadHistory; loading: boolean }) {
  const rows = hist?.rows || [];
  const [table, setTable] = useState(false);
  const [hover, setHover] = useState<number | null>(null);
  const [box, W] = useWidth<HTMLDivElement>();
  const n = Math.max(lead.peerGroup.ranked, ...rows.map((r) => r.ranked), 2);
  const k = Math.ceil((3 * n) / 10);
  const H = W < 480 ? 240 : 280, M = { t: 26, r: 14, b: 26, l: 34 };
  const iw = W - M.l - M.r, ih = H - M.t - M.b;
  const t0 = rows.length ? Date.parse(rows[0].date) : 0, t1 = rows.length ? Date.parse(rows[rows.length - 1].date) : 1;
  const X = (d: string) => M.l + (t1 === t0 ? iw / 2 : ((Date.parse(d) - t0) / (t1 - t0)) * iw);
  const Y = (r: number) => M.t + ((r - 1) / Math.max(1, n - 1)) * ih;
  const count = (l: LeadLabel) => rows.filter((r) => r.label === l).length;
  const story = rankStory(name, rows);
  const concl = rows.length ? `${story}. Latest rank ${lead.rank} of ${lead.peerGroup.ranked}.` : `${name}: no rank history yet.`;
  const years = rows.map((r) => r.date).filter((d, i, a) => i === 0 || d.slice(0, 4) !== a[i - 1].slice(0, 4)).filter((d, i, a) => i === 0 || X(d) - X(a[i - 1]) >= 38);
  const move = (e: React.PointerEvent<SVGSVGElement>) => {
    if (!rows.length) return;
    const r = e.currentTarget.getBoundingClientRect(), x = ((e.clientX - r.left) / r.width) * W;
    let best = 0, bd = 1e9;
    rows.forEach((row, i) => { const d = Math.abs(X(row.date) - x); if (d < bd) { bd = d; best = i; } });
    setHover(best);
  };
  const h = hover != null ? rows[hover] : null;
  return (
    <div className="card acc ld-card ld-cb" style={{ "--ac": "var(--gold)" } as React.CSSProperties}>
      <div className="card-h"><h3><span className="ci"><Icon name="layers" /></span>Rank history</h3><span className="s">1 is the top of {lead.peerGroup.short} peers</span></div>
      {loading ? <div className="skeleton" style={{ height: H }} aria-hidden="true" /> : rows.length < 2 ? <p className="ld-empty">The rank history builds up week by week. It will appear here after a few weekly runs.</p> : (
        <>
          <p className="ld-story">{story}</p>
          <div ref={box} className="ld-chart">
            <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={concl} onPointerMove={move} onPointerLeave={() => setHover(null)} style={{ touchAction: "pan-y" }}>
              <rect x={M.l} y={M.t - 6} width={iw} height={Y(k) - M.t + 12} className="ld-zone leader" />
              <rect x={M.l} y={Y(n - k + 1) - 6} width={iw} height={Y(n) - Y(n - k + 1) + 12} className="ld-zone laggard" />
              <text x={M.l + 2} y={M.t - 12} className="ld-zt leader">Leader zone (top 30%)</text>
              <text x={M.l + iw - 2} y={M.t + ih + 1} textAnchor="end" className="ld-zt laggard">Laggard zone (bottom 30%)</text>
              {[1, Math.round((n + 1) / 2), n].map((r) => <g key={r}><line x1={M.l} x2={M.l + iw} y1={Y(r)} y2={Y(r)} className="ld-grid-l" /><text x={M.l - 6} y={Y(r) + 4} textAnchor="end" className="ld-ax">{r}</text></g>)}
              <path d={path(rows.map((r) => X(r.date)), rows.map((r) => Y(r.rank)))} className="ld-rl" />
              {rows.map((r, i) => <circle key={r.date} cx={X(r.date)} cy={Y(r.rank)} r={i === rows.length - 1 ? 5.5 : 3.6} className={"ld-pd " + r.label} />)}
              {years.map((d) => <text key={d} x={X(d)} y={H - 6} textAnchor="middle" className="ld-ax">{W < 480 ? d.slice(2, 4) : d.slice(0, 4)}</text>)}
              {h && <g><line x1={X(h.date)} x2={X(h.date)} y1={M.t} y2={M.t + ih} className="ld-cross" /><circle cx={X(h.date)} cy={Y(h.rank)} r="7" className={"ld-pd hot " + h.label} /></g>}
            </svg>
            {h && <div className="ld-hov" style={{ left: Math.min(Math.max(8, X(h.date) - 70), W - 190) }} aria-hidden="true"><b>{dShort(h.date)}</b><span>Rank {h.rank} of {h.ranked} · {LABEL_WORD[h.label]}</span><span>{pts(h.rel52)} pts vs {lead.benchmarks.sector.name}</span>{h.rel52Market != null && <span>{pts(h.rel52Market)} pts vs {lead.benchmarks.market?.name}</span>}</div>}
          </div>
          <div className="ld-counts" role="list">
            {(["leader", "in_line", "laggard"] as LeadLabel[]).map((l) => <span role="listitem" key={l} className={"ld-cnt " + l}><i aria-hidden="true" /><b>{count(l)}</b> {LABEL_WORD[l]}</span>)}
            <span className="ld-cnt-n">of {rows.length} checks</span><ShowTable on={table} set={setTable} />
          </div>
          {table && <ChartTable caption={concl} head={["Date", "Rank", "Status", "vs sector, 12M"]} rows={[...rows].reverse().slice(0, 24).map((r: LeadRun) => [dShort(r.date), `${r.rank} of ${r.ranked}`, LABEL_WORD[r.label], `${pts(r.rel52)} pts`])} />}
        </>
      )}
    </div>
  );
}

/* ---- C. has leadership held here? */
function ReliabilityCard({ lead }: { lead: LeadershipOn }) {
  const r: Reliability = lead.sectorReliability;
  const ok = r.tier !== "insufficient" && r.hitRate6m != null;
  const [table, setTable] = useState(false);
  const rate = Math.round((r.hitRate6m || 0) * 100);
  const word = r.tier === "consistent" ? "Consistent" : r.tier === "mixed" ? "Mixed" : r.tier === "not_reliable" ? "Not reliable" : "Not enough history";
  const concl = ok ? `${r.sentence}` : "Not enough history to judge whether leaders have stayed ahead in this group.";
  return (
    <div className="card acc ld-card ld-cc" style={{ "--ac": "var(--ld-grey)" } as React.CSSProperties}>
      <div className="card-h"><h3><span className="ci"><Icon name="check" /></span>Has leadership held here?</h3><span className={"ld-tier " + r.tier}>{word}</span></div>
      <p className="ld-sent">{r.sentence || concl}</p>
      {ok ? (
        <>
          <div className="ld-rel" role="img" aria-label={concl}>
            <div className="ld-rel-main"><span className="ld-rel-l">Leaders beat laggards over the next 6 months</span>
              <div className="ld-bar"><i style={{ width: `${rate}%` }} className={r.tier} /><u style={{ left: "50%" }} /><em style={{ left: "50%" }}>coin flip</em></div><b>{rate}%</b></div>
            <div className="ld-rel-per">{r.periods.map((p) => { const v = Math.round(p.hitRate6m * 100); return <div key={p.years} className="ld-pbar"><div className="ld-pcol"><i style={{ height: `${v}%` }} className={v >= 50 ? "ok" : "no"} /><u /></div><b>{v}%</b><span>{p.years}</span></div>; })}</div>
          </div>
          <div className="ld-foot2"><span className="ld-sm">{r.checks} checks, {r.from} to {r.to}. A share of past checks, not a forecast.</span><ShowTable on={table} set={setTable} /></div>
          {table && <ChartTable caption={concl} head={["Period", "Checks where leaders beat laggards"]} rows={[["Overall", `${rate}% of ${r.checks}`], ...r.periods.map((p) => [p.years, `${Math.round(p.hitRate6m * 100)}%`])]} />}
        </>
      ) : (
        <p className="ld-sm">Judging this needs about 10 years of weekly prices for the group. <Link to={EXPLAINER}>See how it held in four large sectors</Link>.</p>
      )}
    </div>
  );
}

/* ---- D. where it sits today */
function StripPlot({ self, lead }: { self: string; lead: LeadershipOn }) {
  const [box, W] = useWidth<HTMLDivElement>();
  const [table, setTable] = useState(false);
  const [hot, setHot] = useState<string | null>(null);
  const nav = useNavigate();
  const peers = lead.peers.filter((p) => p.rel52 != null);
  const me = peers.find((p) => p.symbol === self);
  const vals = peers.map((p) => p.rel52 as number);
  const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals), pad = Math.max(0.03, (hi - lo) * 0.06);
  const M = { l: 14, r: 14 }, H = 150, axisY = 96;
  const X = (v: number) => M.l + ((v - (lo - pad)) / (hi + pad - (lo - pad))) * (W - M.l - M.r);
  const placed = useMemo(() => {   // dots that would overlap are stacked upwards
    const rows: { p: LeadPeer; x: number; lvl: number }[] = [], lastAt: number[][] = [];
    [...peers].sort((a, b) => (a.rel52 as number) - (b.rel52 as number)).forEach((p) => {
      const x = X(p.rel52 as number); let lvl = 0;
      while ((lastAt[lvl] || []).some((px) => Math.abs(px - x) < 11)) lvl++;
      (lastAt[lvl] = lastAt[lvl] || []).push(x); rows.push({ p, x, lvl });
    });
    return rows;
  }, [peers, W]); // eslint-disable-line react-hooks/exhaustive-deps
  const idx = lead.peers.findIndex((p) => p.symbol === self);
  const near = idx < 0 ? lead.peers.slice(0, 11) : lead.peers.slice(Math.max(0, idx - 5), idx + 6);
  const concl = me ? `${me.name || self} is ${ordinal(me.rank)} of ${lead.peerGroup.ranked} peers at ${pts(me.rel52)} points against ${lead.benchmarks.sector.name} over 12 months.` : "Peers by 12-month return against the sector index.";
  const sh = hot ? peers.find((p) => p.symbol === hot) : null;
  return (
    <div className="card acc ld-card ld-cd" style={{ "--ac": "var(--gold)" } as React.CSSProperties}>
      <div className="card-h"><h3><span className="ci"><Icon name="bars" /></span>Where it sits today</h3><span className="s">12 months vs {lead.benchmarks.sector.name}</span></div>
      <div ref={box} className="ld-chart ld-strip">
        <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={concl}>
          <line x1={M.l} x2={W - M.r} y1={axisY} y2={axisY} className="ld-axis" />
          <line x1={X(0)} x2={X(0)} y1={axisY - 62} y2={axisY + 8} className="ld-zero" /><text x={X(0)} y={axisY + 22} textAnchor="middle" className="ld-ax strong">0 = level with the index</text>
          <text x={M.l} y={axisY + 22} className="ld-ax">{pts(lo - pad)}</text><text x={W - M.r} y={axisY + 22} textAnchor="end" className="ld-ax">{pts(hi + pad)}</text>
          {placed.map(({ p, x, lvl }) => p.symbol === self ? null : (
            <circle key={p.symbol} cx={x} cy={axisY - 9 - lvl * 12} r="5" className={"ld-sd " + p.label + (hot === p.symbol ? " hot" : "")} tabIndex={0} role="link" aria-label={`${p.name || p.symbol}, ${LABEL_WORD[p.label]}, ${pts(p.rel52)} points`}
              onPointerEnter={() => setHot(p.symbol)} onPointerLeave={() => setHot(null)} onFocus={() => setHot(p.symbol)} onBlur={() => setHot(null)} onClick={() => nav(`/stocks/${p.symbol}`)} onKeyDown={(e) => e.key === "Enter" && nav(`/stocks/${p.symbol}`)} />
          ))}
          {me && (() => { const pl = placed.find((q) => q.p.symbol === self); return pl ? <g><circle cx={pl.x} cy={axisY - 9 - pl.lvl * 12} r="9" className={"ld-sd me " + me.label} /><text x={Math.min(W - 40, Math.max(40, pl.x))} y={axisY - 28 - pl.lvl * 12} textAnchor="middle" className="ld-me-l">{self} · {pts(me.rel52)}</text></g> : null; })()}
        </svg>
        {sh && <div className="ld-hov" style={{ left: Math.min(Math.max(8, X(sh.rel52 as number) - 70), W - 190), top: 4 }} aria-hidden="true"><b>{sh.name || sh.symbol}</b><span>{ordinal(sh.rank)} · {LABEL_WORD[sh.label]} · {pts(sh.rel52)} pts</span></div>}
      </div>
      <ol className="ld-near" aria-label="This stock and its nearest peers">
        {near.map((p) => <li key={p.symbol} className={p.symbol === self ? "me" : ""}><span className="n">{p.rank}</span>{p.symbol === self ? <b>{p.name || p.symbol}</b> : <Link to={`/stocks/${p.symbol}`}>{p.name || p.symbol}</Link>}<LeadChip label={p.label} /><Pt v={p.rel52} /></li>)}
      </ol>
      <div className="ld-foot2"><span className="ld-sm">Each dot is one peer. Dots to the right are further ahead of {lead.benchmarks.sector.name}.</span><ShowTable on={table} set={setTable} /></div>
      {table && <ChartTable caption={concl} head={["Rank", "Company", "Status", "vs sector, 12M"]} rows={lead.peers.map((p) => [p.rank, p.name || p.symbol, LABEL_WORD[p.label], `${pts(p.rel52)} pts`])} />}
    </div>
  );
}
