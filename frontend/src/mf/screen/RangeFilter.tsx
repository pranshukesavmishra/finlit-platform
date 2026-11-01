// One numeric filter of the Mutual Fund Screener: a histogram of the funds that pass every OTHER filter, a two-handle slider under it, two typed boxes, preset chips,
// "N of M funds have this figure" and an off-by-default "Include funds with no data". The slider's scale is the histogram's: each bar is one equal step, so a skewed field
// (fund size, spread over four orders of magnitude) is still easy to set. Pure geometry is exported for tests.
import { useEffect, useId, useRef, useState } from "react";
import { nf } from "../../lib/format";
import type { Hist } from "../../lib/mfScreen";
import { cleanNum } from "../../lib/mfScreen";
import { unitText, type NumDef } from "../../lib/mfScreenDefs";

export const STEPS = 1000;

/** 0..1 position of value v on the piecewise-linear scale whose bins are the edges. */
export function toPos(edges: number[], v: number): number {
  const n = edges.length - 1;
  if (n < 1 || v <= edges[0]) return 0;
  if (v >= edges[n]) return 1;
  let i = 0;
  while (i < n - 1 && edges[i + 1] <= v) i++;
  return (i + (v - edges[i]) / (edges[i + 1] - edges[i])) / n;
}
/** The value at position p (0..1). */
export function fromPos(edges: number[], p: number): number {
  const n = edges.length - 1, t = Math.min(Math.max(p, 0), 1) * n, i = Math.min(Math.floor(t), n - 1);
  return edges[i] + (t - i) * (edges[i + 1] - edges[i]);
}
const roundTo = (v: number, dec: number) => { const k = 10 ** dec; return Math.round(v * k) / k; };
/** The text a slider position writes into a box: rounded to the field's decimals; an end position means "no bound" (empty). */
export function valueAt(edges: number[], pos: number, dec: number): string {
  if (pos <= 0 || pos >= STEPS) return "";
  const v = roundTo(fromPos(edges, pos / STEPS), dec);
  return String(v);
}
/** Which bars lie (even partly) inside [lo, hi]. */
export const barIn = (edges: number[], i: number, lo: number | null, hi: number | null) => (hi == null || edges[i] < hi) && (lo == null || edges[i + 1] > lo);

function Box({ label, value, ph, onCommit }: { label: string; value: number | null; ph: string; onCommit: (v: string) => void }) {
  const [t, setT] = useState(value == null ? "" : String(value));
  useEffect(() => setT(value == null ? "" : String(value)), [value]);
  const go = () => { const c = cleanNum(t); if (c !== (value == null ? "" : String(value))) onCommit(c); else setT(value == null ? "" : String(value)); };
  return <input className="mfs-box" type="text" inputMode="decimal" value={t} placeholder={ph} aria-label={label} onChange={(e) => setT(e.target.value)} onBlur={go} onKeyDown={(e) => { if (e.key === "Enter") go(); }} />;
}

type Props = {
  def: NumDef; hist?: Hist; lo: number | null; hi: number | null; nodata: boolean; onRange: (lo: string, hi: string) => void; onNodata: (on: boolean) => void;
  waiting?: boolean; builtRows?: number; hideHead?: boolean;
};
export function RangeFilter({ def, hist, lo, hi, nodata, onRange, onNodata, waiting, builtRows, hideHead }: Props) {
  const uid = useId();
  const edges = hist?.edges ?? [];
  const ok = edges.length >= 3;
  const setLo = lo == null ? 0 : Math.round(toPos(edges, lo) * STEPS), setHi = hi == null ? STEPS : Math.round(toPos(edges, hi) * STEPS);
  const [drag, setDrag] = useState<[number, number] | null>(null);
  const timer = useRef<number | null>(null);
  useEffect(() => { setDrag(null); }, [lo, hi]);
  useEffect(() => () => { if (timer.current) window.clearTimeout(timer.current); }, []);
  const [a, b] = drag ?? [setLo, setHi];
  const commit = (x: number, y: number) => { if (timer.current) window.clearTimeout(timer.current); timer.current = null; onRange(valueAt(edges, x, def.dec), valueAt(edges, y, def.dec)); };
  const move = (x: number, y: number) => { setDrag([x, y]); if (timer.current) window.clearTimeout(timer.current); timer.current = window.setTimeout(() => commit(x, y), 450); };
  const dispLo = drag ? (drag[0] <= 0 ? null : roundTo(fromPos(edges, drag[0] / STEPS), def.dec)) : lo;
  const dispHi = drag ? (drag[1] >= STEPS ? null : roundTo(fromPos(edges, drag[1] / STEPS), def.dec)) : hi;
  const max = Math.max(1, ...(hist?.bins ?? [0]));
  const n = hist?.n ?? 0, m = hist?.m ?? 0, missing = m - n, active = lo != null || hi != null;
  const lab = (v: number) => unitText(def, v);
  const same = (p: { lo?: number; hi?: number }) => (p.lo ?? null) === lo && (p.hi ?? null) === hi;
  const summary = hist ? `Histogram of ${n} funds. ${def.presets.length ? "" : ""}` : "Histogram loading";
  return (
    <div className={"mfs-rf" + (active ? " is-on" : "")} data-field={def.key}>
      {!hideHead && <div className="mfs-rfh"><b>{def.label}</b>{active && <button type="button" className="fgx-link" onClick={() => onRange("", "")}>Clear</button>}</div>}
      {def.hint && !hideHead && <p className="fgx-note">{def.hint}</p>}
      {ok ? (
        <>
          <div className="mfs-hist" role="img" aria-label={`${summary} Selected range: ${dispLo == null ? "any" : lab(dispLo)} to ${dispHi == null ? "any" : lab(dispHi)}.`}>
            {hist!.bins.map((c, i) => (
              <i key={i} className={barIn(edges, i, dispLo, dispHi) ? "in" : ""} style={{ height: c ? `${Math.max(5, (c / max) * 100)}%` : "0" }}
                title={`${lab(edges[i])} to ${lab(edges[i + 1])}: ${nf(c, 0)} fund${c === 1 ? "" : "s"}`} />))}
          </div>
          <div className={"mfs-sl" + (waiting ? " is-wait" : "")}>
            <input type="range" className="mfs-th lo" min={0} max={STEPS} step={1} value={a} aria-label={`Minimum ${def.label}`} aria-valuetext={dispLo == null ? "no minimum" : lab(dispLo)}
              onChange={(e) => move(Math.min(Number(e.target.value), b), b)} onPointerUp={() => drag && commit(drag[0], drag[1])} onBlur={() => drag && commit(drag[0], drag[1])} />
            <input type="range" className="mfs-th hi" min={0} max={STEPS} step={1} value={b} aria-label={`Maximum ${def.label}`} aria-valuetext={dispHi == null ? "no maximum" : lab(dispHi)}
              onChange={(e) => move(a, Math.max(Number(e.target.value), a))} onPointerUp={() => drag && commit(drag[0], drag[1])} onBlur={() => drag && commit(drag[0], drag[1])} />
            <span className="mfs-track" aria-hidden="true"><span style={{ left: `${a / 10}%`, right: `${100 - b / 10}%` }} /></span>
          </div>
          <div className="mfs-axis" aria-hidden="true"><span>{lab(edges[0])}</span><span>{lab(edges[Math.floor(edges.length / 2)])}</span><span>{lab(edges[edges.length - 1])}</span></div>
        </>
      ) : <div className="mfs-hist is-empty" role="status">{waiting ? "Loading the spread of funds…" : "The spread of funds is not available yet."}</div>}
      <div className="mfs-mm" role="group" aria-label={`${def.label}, exact range`}>
        <Box label={`${def.label}, minimum`} value={lo} ph="Min" onCommit={(v) => onRange(v, hi == null ? "" : String(hi))} />
        <span aria-hidden="true">to</span>
        <Box label={`${def.label}, maximum`} value={hi} ph="Max" onCommit={(v) => onRange(lo == null ? "" : String(lo), v)} />
        {def.unit && <span className="mfs-unit" aria-hidden="true">{def.unit === "₹ Cr" ? "₹ Cr" : def.unit === "years" ? "yr" : def.unit}</span>}
      </div>
      {def.presets.length > 0 && (
        <div className="fgx-chips mfs-pre" role="group" aria-label={`${def.label}, quick ranges`}>
          {def.presets.map((p) => { const on = same(p); return (
            <button key={p.label} type="button" className={"fgx-chip" + (on ? " is-on" : "")} aria-pressed={on} onClick={() => (on ? onRange("", "") : onRange(p.lo == null ? "" : String(p.lo), p.hi == null ? "" : String(p.hi)))}>{on && <i aria-hidden="true">&#10003;</i>}{p.label}</button>); })}
        </div>)}
      <p className="mfs-cover" id={`${uid}-c`} aria-live="polite">
        {hist ? (n === 0 && m > 0 ? <><b>No fund</b> among the {nf(m, 0)} here has this figure{builtRows === 0 ? " yet: the nightly job has not run" : ""}.</>
          : <><b>{nf(n, 0)}</b> of <b>{nf(m, 0)}</b> funds have this figure{missing > 0 && active && !nodata ? <span className="mfs-hid"> · {nf(missing, 0)} without it {missing === 1 ? "is" : "are"} left out</span> : null}</>) : "…"}
      </p>
      {missing > 0 && (
        <label className={"fgx-row mfs-nd" + (!active ? " is-off" : "")} title={active ? undefined : "Set a range first: with none set, funds with no figure are already shown."}>
          <input type="checkbox" checked={nodata && active} disabled={!active} onChange={(e) => onNodata(e.target.checked)} aria-describedby={`${uid}-c`} />
          <span className="fgx-lab">Include funds with no data</span><small className="fgx-n">{nf(missing, 0)}</small>
        </label>)}
    </div>
  );
}
