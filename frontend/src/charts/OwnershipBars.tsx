import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { Ownership } from "../lib/api";
import { labelEvery } from "../lib/chartAxis";
import { Icon } from "../lib/icons";
import { OWN_COLOR } from "../stock/derive";
import { RANGES, MIX_HIDDEN_NOTE, barsSummary, buildBars, changeScale, fmtPct, fmtPp, ownCategories, ownershipCsv, toggleHidden, diffPp, type BarView, type Gran, type RangeKey } from "../lib/ownershipBars";

const H = 300, PT = 14, PB = 34, AX = 46, PLOT = H - PT - PB;
const reduced = () => typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
const clamp = (x: number, a: number, b: number) => Math.max(a, Math.min(b, x));

function Seg<T extends string>({ label, value, set, items }: { label: string; value: T; set: (v: T) => void; items: { v: T; t: string }[] }) {
  return <div className="seg ob-seg" role="group" aria-label={label}>{items.map((i) => <button key={i.v} type="button" aria-pressed={value === i.v} onClick={() => set(i.v)}>{i.t}</button>)}</div>;
}

/** Interactive bar chart of the shareholding pattern: 100% stacked bars (Mix) or diverging bars of the change in percentage points (Change).
 *  Clicking a bar selects that filing for the rest of the section. Plain React SVG, no chart library. */
export function OwnershipBars({ o, selected, onSelect }: { o: Ownership; selected: number; onSelect: (periodIndex: number) => void }) {
  const uid = useId().replace(/:/g, "");
  const [gran, setGran] = useState<Gran>("quarterly"), [range, setRange] = useState<RangeKey>("3Y"), [view, setView] = useState<BarView>("mix");
  const [hidden, setHidden] = useState<string[]>([]), [hl, setHl] = useState<string | null>(null);
  const [hover, setHover] = useState<number | null>(null), [focus, setFocus] = useState<number | null>(null), [focused, setFocused] = useState(false);
  const [box, setBox] = useState({ w: 640, left: 0 });
  const scroller = useRef<HTMLDivElement>(null), wrap = useRef<HTMLDivElement>(null);

  const cats = useMemo(() => ownCategories(o), [o]);
  const bars = useMemo(() => buildBars(o, gran, range), [o, gran, range]);
  const keys = cats.map((c) => c.key), visible = cats.filter((c) => !hidden.includes(c.key)), vk = visible.map((c) => c.key);
  const n = bars.length, k = Math.max(visible.length, 1);
  const selPos = bars.findIndex((b) => b.index === selected);

  useEffect(() => {
    const el = scroller.current; if (!el) return;
    const m = () => setBox((b) => ({ ...b, w: el.clientWidth || b.w }));
    m();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(m); ro.observe(el); return () => ro.disconnect();
  }, []);

  const minPitch = view === "mix" ? 26 : k * 9 + 16;
  const pitch = Math.max(minPitch, box.w / Math.max(n, 1)), W = Math.max(n * pitch, box.w);
  const x0 = (i: number) => i * pitch;

  // Keep the selected bar in view when the controls or the selection change.
  useEffect(() => {
    const el = scroller.current; if (!el || n === 0) return;
    const pos = selPos >= 0 ? selPos : n - 1, c = pos * pitch + pitch / 2;
    if (c < el.scrollLeft + 20 || c > el.scrollLeft + el.clientWidth - 20 || selPos < 0)
      el.scrollTo({ left: Math.max(0, c - el.clientWidth / 2), behavior: reduced() ? "auto" : "smooth" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selPos, gran, range, view, n, pitch]);

  const ms = view === "change" ? changeScale(bars, vk) : { max: 100, step: 25 };
  const Y = (v: number) => PT + (1 - (v + (view === "change" ? ms.max : 0)) / (view === "change" ? 2 * ms.max : 100)) * PLOT;
  const ticks: number[] = []; for (let t = view === "change" ? -ms.max : 0; t <= ms.max + 1e-9; t += ms.step) ticks.push(Math.round(t * 100) / 100);
  const every = labelEvery(n, W, 8, 6.2, 12);
  const col = (key: string) => `var(${OWN_COLOR[key] || "--faint"})`;
  const act = hover ?? (focused ? focus : null), shown = act != null ? bars[act] : selPos >= 0 ? bars[selPos] : null;

  const move = (to: number) => { const t = clamp(to, 0, n - 1); setFocus(t); setHover(null); const el = scroller.current; if (el) { const c = t * pitch + pitch / 2; if (c < el.scrollLeft + 24 || c > el.scrollLeft + el.clientWidth - 24) el.scrollTo({ left: Math.max(0, c - el.clientWidth / 2), behavior: reduced() ? "auto" : "smooth" }); } };
  const onKey = (e: React.KeyboardEvent) => {
    const cur = focus ?? (selPos >= 0 ? selPos : n - 1);
    if (e.key === "ArrowRight") { e.preventDefault(); move(cur + 1); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); move(cur - 1); }
    else if (e.key === "Home") { e.preventDefault(); move(0); }
    else if (e.key === "End") { e.preventDefault(); move(n - 1); }
    else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); if (bars[cur]?.filed) onSelect(bars[cur].index); }
  };

  const download = () => {
    const csv = ownershipCsv(bars, visible, view);
    const a = document.createElement("a"), url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    a.href = url; a.download = `shareholding-${view === "mix" ? "mix" : "change"}-${gran}.csv`; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
  };

  if (n < 2 || !cats.length) return (
    <div id="own-history" className="card acc own-hist" style={{ "--ac": "var(--p-balance)" } as React.CSSProperties}>
      <div className="card-h"><h3><span className="ci"><Icon name="bars" /></span>How the shareholding pattern changed</h3></div>
      <p className="faint ob-empty">Not enough filings to show a trend. {o.periods.length ? `Only ${o.periods.length} filing${o.periods.length === 1 ? "" : "s"} on record so far.` : ""} Information only, not advice.</p>
    </div>
  );

  const prevOf = (i: number) => (i > 0 ? bars[i - 1] : null);
  const tipLeft = act != null ? clamp(AX + x0(act) + pitch / 2 - box.left, 104, Math.max(104, box.w + AX - 104)) : 0;
  const ab = act != null ? bars[act] : null, pb = act != null ? prevOf(act) : null;
  const span = `${bars[0].period} to ${bars[n - 1].period}`;
  const avail = range !== "All" && gran === "quarterly" && n < 4 * +range[0];
  const live = shown ? `${act != null ? "Focused" : "Selected"} ${shown.period}. ${visible.map((c) => `${c.label} ${view === "mix" ? fmtPct(shown.values[c.key]) : fmtPp(shown.changes[c.key])}`).join(", ")}.` : "";

  return (
    <div id="own-history" className="card acc own-hist ob" style={{ "--ac": "var(--p-balance)" } as React.CSSProperties}>
      <div className="card-h"><h3><span className="ci"><Icon name="bars" /></span>How the shareholding pattern changed</h3><span className="s">{view === "mix" ? "Share of all shares held, each filing" : "Change in percentage points against a year earlier"}</span></div>
      <div className="ob-ctl">
        <Seg label="Filings" value={gran} set={setGran} items={[{ v: "quarterly", t: "Quarterly" }, { v: "yearly", t: "Yearly" }]} />
        <Seg label="Range" value={range} set={setRange} items={RANGES.map((r) => ({ v: r, t: r }))} />
        <Seg label="View" value={view} set={setView} items={[{ v: "mix", t: "Mix" }, { v: "change", t: "Change" }]} />
        <button type="button" className="btn ob-dl" onClick={download}><Icon name="download" />Download CSV</button>
      </div>
      <div className="clg ob-lg" role="group" aria-label="Show or hide holders">{cats.map((c) => (
        <button key={c.key} type="button" className={"ob-li" + (hidden.includes(c.key) ? " off" : "")} aria-pressed={!hidden.includes(c.key)} onClick={() => setHidden((h) => toggleHidden(h, c.key, keys))} onMouseEnter={() => setHl(c.key)} onMouseLeave={() => setHl(null)} onFocus={() => setHl(c.key)} onBlur={() => setHl(null)}><i style={{ background: col(c.key) }} />{c.label}</button>
      ))}</div>
      {view === "mix" && hidden.length > 0 && <p className="ob-warn" role="status">{MIX_HIDDEN_NOTE}.</p>}
      <div className="ob-wrap" ref={wrap}>
        <svg className="ob-ax" width={AX} height={H} aria-hidden="true">{ticks.map((t) => <text key={t} x={AX - 6} y={Y(t) + 4} textAnchor="end" fontSize="10.5" fill="var(--faint)" fontFamily="IBM Plex Mono, monospace">{view === "mix" ? `${t}%` : (t > 0 ? "+" : t < 0 ? "−" : "") + Math.abs(t)}</text>)}</svg>
        <div className="ob-scroll" ref={scroller} onScroll={(e) => { const left = e.currentTarget.scrollLeft; setBox((b) => ({ ...b, left })); }}>
          <div className="ob-plot" tabIndex={0} role="group" aria-label={`Shareholding bars, ${n} filings. Use the left and right arrow keys to move between bars, Enter to select one, Home and End to jump.`} aria-describedby={`${uid}-sum`} onKeyDown={onKey} onFocus={() => { setFocused(true); setFocus((f) => f ?? (selPos >= 0 ? selPos : n - 1)); }} onBlur={() => setFocused(false)} style={{ width: W }}>
            <svg width={W} height={H} role="img" aria-label={barsSummary(bars, visible, view)}>
              {ticks.map((t) => <line key={t} x1={0} x2={W} y1={Y(t)} y2={Y(t)} stroke={view === "change" && t === 0 ? "var(--text)" : "var(--border)"} strokeOpacity={view === "change" && t === 0 ? 0.55 : 1} strokeDasharray={view === "change" && t === 0 ? "" : "3 5"} />)}
              {bars.map((b, i) => {
                const on = i === act, sel = i === selPos, cx = x0(i) + pitch / 2;
                return (
                  <g key={b.index} className="ob-col">
                    {(on || sel) && <rect x={x0(i) + 1} y={PT - 4} width={pitch - 2} height={PLOT + 8} rx="6" fill={on ? "var(--s2)" : "none"} stroke={sel ? "var(--gold)" : "none"} strokeWidth="2" />}
                    {!b.filed && <g><rect x={cx - 8} y={PT + 6} width="16" height={PLOT - 12} rx="4" fill="none" stroke="var(--border-strong)" strokeDasharray="3 3" /><text transform={`translate(${cx + 4},${PT + PLOT / 2}) rotate(-90)`} textAnchor="middle" fontSize="10.5" fill="var(--faint)">not filed</text></g>}
                    {b.filed && view === "mix" && (() => {
                      const bw = clamp(pitch * 0.62, 14, 72); let cum = 0;
                      return visible.map((c) => {
                        const v = b.values[c.key]; if (v == null) return null;
                        const y1 = Y(Math.min(100, cum + v)), y0 = Y(Math.min(100, cum)); cum += v;
                        return <rect key={c.key} className="ob-r" x={cx - bw / 2} y={y1} width={bw} height={Math.max(0, y0 - y1)} fill={col(c.key)} opacity={hl && hl !== c.key ? 0.25 : 1} stroke="var(--s1)" strokeWidth="0.75" />;
                      });
                    })()}
                    {b.filed && view === "change" && (() => {
                      const sw = clamp((pitch * 0.78) / k, 6, 16), gx = cx - (sw * k) / 2;
                      return visible.map((c, j) => {
                        const d = b.changes[c.key], x = gx + j * sw, op = hl && hl !== c.key ? 0.25 : 1;
                        if (d == null) return <circle key={c.key} cx={x + sw / 2} cy={Y(0)} r="2.4" fill="none" stroke="var(--faint)" strokeWidth="1.2" opacity={op}><title>{`${c.label}: ${fmtPp(null)}`}</title></circle>;
                        const yy = Y(d), h = Math.max(Math.abs(yy - Y(0)), d === 0 ? 1 : 1.5);
                        return <rect key={c.key} className="ob-r" x={x + 0.5} y={d >= 0 ? Y(0) - h : Y(0)} width={Math.max(sw - 1, 2)} height={h} rx="1.5" fill={col(c.key)} opacity={op} />;
                      });
                    })()}
                    {(n - 1 - i) % every === 0 && <text x={cx} y={H - 12} textAnchor="middle" fontSize="10.5" fill={sel ? "var(--gold)" : "var(--faint)"} fontWeight={sel ? 700 : 400}>{b.period}</text>}
                    <rect x={x0(i)} y={0} width={pitch} height={H} fill="transparent" style={{ cursor: b.filed ? "pointer" : "default" }} onPointerEnter={() => setHover(i)} onPointerLeave={() => setHover(null)} onClick={() => { if (b.filed) { onSelect(b.index); setFocus(i); } }} />
                  </g>
                );
              })}
            </svg>
          </div>
        </div>
        {ab && <div className="ob-tip" style={{ left: tipLeft }} role="presentation">
          <b>{ab.period}{ab.index === selected ? " · selected" : ""}</b>
          {!ab.filed && <span className="ob-nf">Not filed in this period</span>}
          {ab.filed && visible.map((c) => {
            const v = ab.values[c.key], d = ab.changes[c.key];
            const vs = view === "mix" ? (pb ? diffPp(v, pb.values[c.key]) : null) : (pb ? diffPp(d, pb.changes[c.key]) : null);
            return <span key={c.key}><i style={{ background: col(c.key) }} />{c.label}<em>{view === "mix" ? fmtPct(v) : fmtPp(d)}</em><small>{pb ? `vs previous bar ${fmtPp(vs)}` : "first bar shown"}</small></span>;
          })}
          {ab.filed && view === "change" && <small className="ob-cmp">{ab.comparedWith ? `Compared with ${ab.comparedWith}` : "No earlier filing to compare with"}</small>}
          {ab.filed && view === "mix" && hidden.length > 0 && <small className="ob-cmp">Hidden holders not included</small>}
          <small className="ob-hint">Click to show this period above</small>
        </div>}
      </div>
      <p id={`${uid}-sum`} className="ob-cap faint">{view === "mix" ? `Each bar is one ${gran === "yearly" ? "year's latest filing" : "quarterly filing"}, ${span}.` : `Each group is the change in percentage points against ${gran === "yearly" ? "the previous year's latest filing" : "the same quarter a year earlier"}; above the line means holding more, below means less.`}{avail ? ` Only ${n} filings are on record, so that is what is shown.` : ""} Gaps and “not filed” marks are filings with no figure; they are never drawn as zero. Click a bar to show that period in the year selector, the owners and the bought and sold bars. Information only, not advice.</p>
      <p className="sr-only" aria-live="polite">{live}</p>
      <table className="sr-only"><caption>Shareholding pattern by filing, {view === "mix" ? "percent of shares" : "change in percentage points against a year earlier"}</caption>
        <thead><tr><th scope="col">Period</th>{visible.map((c) => <th scope="col" key={c.key}>{c.label}</th>)}</tr></thead>
        <tbody>{bars.map((b) => <tr key={b.index}><th scope="row">{b.period}</th>{visible.map((c) => <td key={c.key}>{view === "mix" ? fmtPct(b.values[c.key]) : fmtPp(b.changes[c.key])}</td>)}</tr>)}</tbody></table>
    </div>
  );
}
