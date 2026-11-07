// The rotation map: x = 6-month strength against the average industry, y = last month's change, 8 (or 4) weekly points per group as a line ending in today's dot. A hollow dot means this
// week's reading is in another corner. Every dot is a button (name, corner, numbers in its label); labels are all on at desktop width and the top 6 by rank on phones.
import { useEffect, useRef, useState } from "react";
import { CORNER_WORD, longDate, shortName, mapGeometry, placeLabels, pts, rankMove, type RotationRow } from "../../lib/rotation";
import { Glyph } from "./Parts";
import { ChartZoom } from "../../components/ChartZoom";

function useWidth(): [React.RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement | null>(null);
  const [w, setW] = useState(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const read = () => setW(Math.round(el.getBoundingClientRect().width));
    read();
    if (typeof ResizeObserver === "undefined") { window.addEventListener("resize", read); return () => window.removeEventListener("resize", read); }
    const ro = new ResizeObserver(read);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

export function RotationMapChart({ rows, date, onOpen, filterCorner }: { rows: RotationRow[]; date: string; onOpen: (slug: string) => void; filterCorner?: string }) {
  const [wrap, width] = useWidth();
  const [weeks, setWeeks] = useState<4 | 8>(8);
  const [pick, setPick] = useState<string | null>(null);
  const phone = width > 0 && width < 640;
  const w = Math.max(280, width || 960), h = phone ? 420 : 560;
  const geo = mapGeometry(rows, w, h, weeks, phone ? 6 : null, phone ? { left: 34, right: 10, top: 12, bottom: 30 } : undefined);
  const lab = placeLabels(geo.dots, phone ? 6.2 : 6.6, 14, w);
  const picked = geo.dots.find((d) => d.slug === pick) ?? null;
  const quad = (cls: string, x1: number, y1: number, x2: number, y2: number) => <rect className={`rt-q ${cls}`} x={Math.min(x1, x2)} y={Math.min(y1, y2)} width={Math.abs(x2 - x1)} height={Math.abs(y2 - y1)} />;
  return (
    <ChartZoom label={"Sector rotation map"} className="cz-r">
    <div className="rt-map">
      <div className="rt-mapbar">
        <p className="rt-note" style={{ margin: 0 }}>Across: 6-month return against the average industry. Up: last month against the average. Tails show the last {weeks} weekly closes.</p>
        <div className="rt-seg" role="group" aria-label="Weeks of tail">
          {([4, 8] as const).map((n) => <button key={n} type="button" aria-pressed={weeks === n} onClick={() => setWeeks(n)}>{n} weeks</button>)}
        </div>
      </div>
      <div ref={wrap} className="rt-mapbox">
        <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} role="group" aria-label={`Rotation map of ${rows.length} industry groups as of ${longDate(date)}`}>
          {quad("bg", geo.left, geo.top, geo.x0, geo.y0)}{quad("ag", geo.x0, geo.top, geo.right, geo.y0)}{quad("bs", geo.left, geo.y0, geo.x0, geo.bottom)}{quad("as", geo.x0, geo.y0, geo.right, geo.bottom)}
          <line className="rt-axis" x1={geo.left} x2={geo.right} y1={geo.y0} y2={geo.y0} /><line className="rt-axis" y1={geo.top} y2={geo.bottom} x1={geo.x0} x2={geo.x0} />
          {geo.xTicks.map((t) => <text key={"x" + t} className="rt-tick" x={geo.x(t)} y={h - 12} textAnchor="middle">{t > 0 ? "+" : ""}{String(t).replace("-", "−")}</text>)}
          {geo.yTicks.map((t) => <text key={"y" + t} className="rt-tick" x={geo.left - 6} y={geo.y(t) + 4} textAnchor="end">{t > 0 ? "+" : ""}{String(t).replace("-", "−")}</text>)}
          <text className="rt-qlab bg" x={geo.left + 8} y={geo.top + 16}>Behind but gaining</text>
          <text className="rt-qlab ag" x={geo.right - 8} y={geo.top + 16} textAnchor="end">Ahead and gaining</text>
          <text className="rt-qlab bs" x={geo.left + 8} y={geo.bottom - 8}>Behind and slipping</text>
          <text className="rt-qlab as" x={geo.right - 8} y={geo.bottom - 8} textAnchor="end">Ahead but slowing</text>
          {geo.dots.map((d) => <path key={"p" + d.slug} className={`rt-tail c-${d.row.corner}${filterCorner && filterCorner !== d.row.corner ? " dim" : ""}`} d={d.path} fill="none" />)}
          {geo.dots.map((d) => {
            const dim = filterCorner && filterCorner !== d.row.corner;
            const l = lab[d.slug];
            return (
              <g key={d.slug} className={`rt-dotg c-${d.row.corner}${dim ? " dim" : ""}${pick === d.slug ? " sel" : ""}`}>
                <circle className="rt-hit" cx={d.x} cy={d.y} r={phone ? 22 : 11} onClick={() => setPick(d.slug)} tabIndex={0} role="button" aria-label={`${d.name}: ${d.row.corner_name}${d.hollow ? `, this week reads ${d.row.this_week_reading_name}` : ""}, rank ${d.row.rank}, ${pts(d.row.strength_pts)} points over 6 months, ${pts(d.row.change_pts)} last month`}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setPick(d.slug); } }}><title>{d.name}</title></circle>
                <circle className={"rt-dot" + (d.hollow ? " hollow" : "")} cx={d.x} cy={d.y} r={d.hollow ? 5 : 4.5} />
                {l && <text className="rt-dlab" x={l.x} y={l.y} textAnchor={l.anchor}>{shortName(d.name)}</text>}
              </g>
            );
          })}
        </svg>
      </div>
      <div className="rt-legend"><span><i className="dot" />Filled dot: today's corner</span><span><i className="dot hollow" />Hollow dot: this week's reading is in another corner; one more weekly close there would move it</span></div>
      <p className="rt-note">Points are percentage points against the average industry. {phone ? "Tap a dot for its name and numbers; the labels show the top 6 by rank." : "Select a dot for its numbers."}</p>
      {picked && (
        <div className="rt-pick" role="status" aria-live="polite">
          <div><b>{picked.name}</b> <span className={`rt-corner c-${picked.row.corner}`}><Glyph corner={picked.row.corner} /><span>{picked.row.corner_name}</span></span></div>
          <div className="rt-note" style={{ margin: "4px 0 0" }}>Rank {picked.row.rank} of {picked.row.ranked} ({rankMove(picked.row.rank_change_1w).label} on the week) · {pts(picked.row.strength_pts)} pts over 6 months · {pts(picked.row.change_pts)} pts last month{picked.hollow ? ` · this week reads ${picked.row.this_week_reading_name}` : ""} · {CORNER_WORD[picked.row.corner]} for {picked.row.weeks_in_corner} {picked.row.weeks_in_corner === 1 ? "week" : "weeks"}</div>
          <button type="button" className="btn" onClick={() => onOpen(picked.slug)} style={{ minHeight: 44 }}>Open {picked.name}</button>
        </div>
      )}
    </div>
    </ChartZoom>
  );
}
