import { useState } from "react";
import { MINUS, heatStep, readingRule, readingsFor, restSentence, short2, two } from "./derive";
import { GROUP_NOTE, GROUP_NOTE_LONG, LEGEND } from "./words";
import type { Meta, Mode, PageObject, Seg } from "./types";
import { ChartZoom } from "../components/ChartZoom";

type Props = { page: PageObject; meta: Record<string, Meta>; mode: Mode; colors: Record<string, string> };
type Pick = "all" | "same" | "cross";
const sectorOf = (meta: Record<string, Meta>, s: string) => meta[s]?.sector || `${s} (not classified)`;
const secName = (s: string) => s.replace(/ \(not classified\)$/, "");

function SegCard({ title, seg, bins, on, onPick }: { title: string; seg: Seg; bins: [number, number][]; on: boolean; onPick: () => void }) {
  const max = Math.max(1, ...seg.hist);
  return (
    <button type="button" className={"pfx-seg" + (on ? " on" : "")} aria-pressed={on} onClick={onPick}>
      <span className="pfx-seg-h"><b>{title}</b><span>{seg.pairs} pairs</span></span>
      <span className="pfx-seg-v"><span className="pfx-serif">{seg.avg == null ? MINUS : two(seg.avg)}</span> average correlation</span>
      <span className="pfx-hist" aria-hidden="true">{seg.hist.map((c, i) => <i key={i} className={"h" + heatStep(Math.max(bins[i][0] + 0.05, 0.06))} style={{ height: c ? `${Math.max(4, Math.round((c / max) * 100))}%` : 0 }} title={`${c} pairs from ${bins[i][0].toFixed(1)} to ${bins[i][1].toFixed(1)}`} />)}</span>
      <span className="pfx-hist-x" aria-hidden="true"><span>−0.2</span><span>0</span><span>0.5</span><span>1</span></span>
      <span className="pfx-seg-f">{seg.pairs ? `${seg.at_least_05} of ${seg.pairs} pairs at 0.5 or more (${Math.round(seg.share_at_least_05 ?? 0)}%)` : "No pairs in this group: it needs two shares in one sector, or two sectors."}</span>
      {seg.top.length > 0 && <span className="pfx-seg-f">Closest: {seg.top[0].a} and {seg.top[0].b} ({two(seg.top[0].corr)})</span>}
    </button>
  );
}

export function GroupCard({ g, meta, colors }: { g: PageObject["groups"][number]; meta: Record<string, Meta>; colors: Record<string, string> }) {
  const secs = [...new Set(g.members.map((m) => sectorOf(meta, m)))];
  return (
    <div className="pfx-group"><div className="pfx-group-h"><span className="pfx-letter">{g.letter}</span><b>{g.members.length} shares · {two(g.avg_corr)} on average</b>{secs.length > 1 && <em className="pfx-cross">Crosses sectors</em>}</div>
      <div className="pfx-gchips">{g.members.map((m) => <span className="pfx-pill2" key={m}><i className="pfx-dot" style={{ background: colors[sectorOf(meta, m)] }} aria-hidden="true" />{m}</span>)}</div>
      <p>{secs.map(secName).join(" + ")}</p></div>
  );
}

/** The correlation grid: group blocks first, every pair a square (numbers inside on short lists, on hover on long ones). */
function Grid({ page, meta, colors, pick, focus, setFocus }: Props & { pick: Pick; focus: string | null; setFocus: (s: string | null) => void }) {
  const order = page.order, n = order.length, long = page.layout === "long";
  const pos = new Map(order.map((s, i) => [s, i]));
  const same = (a: string, b: string) => sectorOf(meta, a) === sectorOf(meta, b) && !/\(not classified\)$/.test(sectorOf(meta, a));
  const cell = long ? (n > 60 ? 8 : n > 30 ? 15 : 18) : 29;
  const style = { "--n": n, "--cell": cell + "px" } as React.CSSProperties;
  return (
    <ChartZoom label="How each pair of shares moved together"><div className="pfx-gridwrap" data-chart><div className={"pfx-grid" + (long ? " small" : "")} style={style} role="table" aria-label="How each pair of shares moved together">
      {order.map((s, i) => <span key={"c" + s} className="pfx-gcol" style={{ gridColumn: 4 + i, gridRow: 1 }} role="columnheader">{s}</span>)}
      {order.map((a, i) => (
        <div key={a} style={{ display: "contents" }} role="row">
          <button type="button" className={"pfx-grow-l" + (focus === a ? " on" : "")} style={{ gridRow: 2 + i, gridColumn: 1 }} aria-pressed={focus === a} onClick={() => long && setFocus(focus === a ? null : a)} tabIndex={long ? 0 : -1}>{a}</button>
          <i className="pfx-sw" style={{ gridRow: 2 + i, gridColumn: 2, background: colors[sectorOf(meta, a)] }} aria-hidden="true" />
          {order.map((b, j) => {
            const v = page.corr[i][j], diag = i === j, sm = same(a, b);
            const lit = diag || ((pick === "all" || (pick === "same") === sm) && (!focus || a === focus || b === focus));
            return <span key={b} role="cell" className={"pfx-gc" + (diag ? " d" : " h" + heatStep(v)) + (lit ? "" : " dim")} style={{ gridRow: 2 + i, gridColumn: 4 + j }}
              title={diag ? a : `${a} with ${b}: ${two(v)} · ${sm ? "same sector" : "different sectors"}`}>{!long && !diag ? short2(v) : ""}</span>; })}
        </div>))}
      {page.groups.map((g) => { const lo = pos.get(g.members[0]) ?? 0, k = g.members.length; return (
        <div key={g.letter} style={{ display: "contents" }}>
          <span className="pfx-gl" style={{ gridColumn: 3, gridRow: `${2 + lo} / span ${k}` }} aria-label={`Group ${g.letter}`}>{g.letter}</span>
          <span className="pfx-gbox" style={{ gridColumn: `${4 + lo} / span ${k}`, gridRow: `${2 + lo} / span ${k}` }} aria-hidden="true" />
        </div>); })}
    </div></div></ChartZoom>
  );
}

export function Together({ page, meta, mode, colors, open, onToggle, children }: Props & { open: boolean; onToggle: () => void; children?: React.ReactNode }) {
  const [pick, setPick] = useState<Pick>("all");
  const [focus, setFocus] = useState<string | null>(null);
  const long = page.layout === "long", seg = page.segments;
  const m2 = readingRule(page, "M2", mode);
  const notes = readingsFor(page, mode, "together", 5, ["M1", "M2"]);
  const total = seg.same.pairs + seg.cross.pairs, nG = page.groups.length;
  const crossG = page.groups.filter((g) => new Set(g.members.map((m) => sectorOf(meta, m))).size > 1).length;
  const line = `${page.order.length} shares move like ${page.score.effective_stocks.toFixed(1)} independent ones · ${nG} ${nG === 1 ? "group" : "groups"}`
    + (seg.same.avg != null && seg.cross.avg != null ? ` · same-sector pairs ${two(seg.same.avg)}, different-sector pairs ${two(seg.cross.avg)}` : "");
  const set = (p: Pick) => setPick((c) => (c === p ? "all" : p));
  return (
    <section className="pfx-card pfx-wide" id="pf-together" aria-labelledby="pfx-tg">
      <div className="pfx-h"><div><h2 id="pfx-tg">What moves together</h2><p className="pfx-line pfx-tight">{line}</p></div>
        <button type="button" className="pfx-btn" aria-expanded={open} aria-controls="pfx-tg-body" onClick={onToggle}>{open ? "Hide" : "Show"}<svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" style={{ transform: open ? "rotate(180deg)" : undefined }}><path d="M2 4l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.6" /></svg></button></div>
      {open && <div id="pfx-tg-body" className="pfx-tg-body">
        <div><h3>Same sector or different sectors</h3><p className="pfx-line">Every pair of shares is either in the same NSE sector or in two different ones. Click a card to show only those pairs on the grid.</p>
          <div className="pfx-segs"><SegCard title="Same sector" seg={seg.same} bins={seg.bins} on={pick === "same"} onPick={() => set("same")} /><SegCard title="Different sectors" seg={seg.cross} bins={seg.bins} on={pick === "cross"} onPick={() => set("cross")} /></div>
          {m2 && <p className="pfx-line">{m2.text}</p>}</div>
        <div className="pfx-gsplit">
          <div><div className="pfx-pickrow"><span>Show on the grid</span>
            {([["all", `All pairs · ${total}`], ["same", `Same sector · ${seg.same.pairs}`], ["cross", `Different sectors · ${seg.cross.pairs}`]] as const).map(([id, l]) => <button key={id} type="button" className={"pfx-pillbtn" + (pick === id ? " on" : "")} aria-pressed={pick === id} onClick={() => setPick(id)}>{l}</button>)}</div>
            <Grid page={page} meta={meta} mode={mode} colors={colors} pick={pick} focus={focus} setFocus={setFocus} />
            <div className="pfx-legend">{LEGEND.map((l, i) => <span key={l}><i className={i === 0 ? "h0 hollow" : "h" + i} />{l}</span>)}<span><i className="pfx-sw" style={{ background: "var(--k1)" }} />Bar beside a name = its sector colour</span></div></div>
          <div className="pfx-gside">
            {!long && <><h3>Groups that move together</h3><div className="pfx-groups2">{page.groups.map((g) => <GroupCard key={g.letter} g={g} meta={meta} colors={colors} />)}</div>
              <p className="pfx-fine">{GROUP_NOTE}</p></>}
            {long && <div className="pfx-pickbox">{focus ? <><h3>{focus}</h3><p>Average with the other shares: {two(page.avg_with_rest[focus] ?? 0)}. {page.order.length - 1} pairs are lit on the grid. Click the name again to clear.</p></>
              : <><h3>Pick a share</h3><p>Click a name on the left to light up its row and see which of your other shares it moves with most and least.</p></>}</div>}
            <div className="pfx-grid-says"><h3>What the grid shows</h3><ul>{notes.map((x) => <li key={x.rule + x.text}>{x.text}</li>)}{!notes.length && <li>No pair or group stands out for this list.</li>}</ul></div>
          </div>
        </div>
        {long && <div><h3>Groups that move together</h3><p className="pfx-line">{GROUP_NOTE_LONG}{crossG ? ` ${crossG} of the ${nG} groups cross sectors.` : ""}</p>
          <div className="pfx-groups4">{page.groups.map((g) => <GroupCard key={g.letter} g={g} meta={meta} colors={colors} />)}</div></div>}
        {long && <Rest page={page} />}
        {children}
      </div>}
    </section>
  );
}

/** Long lists: each share's average correlation with the others, lowest to highest. */
function Rest({ page }: { page: PageObject }) {
  const xs = Object.entries(page.avg_with_rest).sort((a, b) => a[1] - b[1]);
  const max = Math.max(0.01, ...xs.map((x) => x[1]));
  return (
    <div className="pfx-rest"><div className="pfx-h"><h3 className="pfx-serif">How much each share moves with the rest</h3><p className="pfx-note">Average correlation with the other {Math.max(0, xs.length - 1)}</p></div>
      <ChartZoom label="How much each share moves with the rest">
      <p className="pfx-legend"><span><i className="rest-lo" />Under 0.2, mostly moves on its own</span><span><i className="rest-mid" />0.2–0.3</span><span><i className="rest-hi" />0.3+, moves a lot with the rest</span></p>
      <div className="pfx-restbars" role="img" aria-label="Average correlation of each share with the rest of the list">{xs.map(([s, v]) => <span key={s} title={`${s}: ${two(v)}`} className={v < 0.2 ? "lo" : v < 0.3 ? "mid" : "hi"}><i style={{ height: `${Math.max(3, (v / max) * 100)}%` }} /><em>{s}</em></span>)}</div>
      </ChartZoom>
      <p className="pfx-line">{restSentence(page.avg_with_rest)}</p></div>
  );
}
