// The Mutual Fund Screener's two small graphics, both drawn only from numbers the server sends and both in the page's one accent colour (gold):
//   RiskReturn  each fund of the result as a dot: yearly 3-year return up, volatility along. A picture of where the result sits, never a ranking.
//   FlowBars    the last six months of AMFI's net flow for a category: gold bars up for inflow, grey bars down for outflow.
import { Link } from "react-router";
import { nf } from "../../lib/format";
import type { ScreenFacets } from "../../lib/mfScreen";

/** About `count` round tick values covering [lo, hi]. */
export function niceTicks(lo: number, hi: number, count = 4): number[] {
  if (!(hi > lo)) return [lo];
  const raw = (hi - lo) / count, mag = 10 ** Math.floor(Math.log10(raw)), k = raw / mag, step = (k < 1.5 ? 1 : k < 3.5 ? 2 : k < 7.5 ? 5 : 10) * mag;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(Math.round(v / step) * step);
  return out;
}

const W = 420, H = 230, L = 44, R = 12, T = 12, B = 38;
export function RiskReturn({ data }: { data?: ScreenFacets["scatter"] }) {
  const pts = data?.points ?? [];
  if (pts.length < 3) return <p className="muted mfs-gl-none">{data ? "Fewer than three funds in this result have both a 3-year return and a volatility, so no picture is drawn." : "Loading…"}</p>;
  const xs = pts.map((p) => p[3]), ys = pts.map((p) => p[2]);
  const x0 = 0, x1 = Math.max(...xs) * 1.05 || 1, y0 = Math.min(0, ...ys) * 1.05, y1 = Math.max(...ys) * 1.05 || 1;
  const X = (v: number) => L + ((v - x0) / (x1 - x0)) * (W - L - R), Y = (v: number) => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
  const xt = niceTicks(x0, x1, 4), yt = niceTicks(y0, y1, 4);
  return (
    <figure className="mfs-fig">
      <svg viewBox={`0 0 ${W} ${H}`} role="group" aria-label={`Volatility and 3-year return of ${pts.length} funds in the result`} className="mfs-sc">
        {yt.map((v) => <g key={"y" + v}><line x1={L} x2={W - R} y1={Y(v)} y2={Y(v)} className={v === 0 ? "ax0" : "gr"} /><text x={L - 6} y={Y(v) + 3.5} textAnchor="end">{nf(v, 0)}%</text></g>)}
        {xt.map((v) => <g key={"x" + v}><line x1={X(v)} x2={X(v)} y1={T} y2={H - B} className="gr" /><text x={X(v)} y={H - B + 14} textAnchor="middle">{nf(v, 0)}%</text></g>)}
        <text x={(L + W - R) / 2} y={H - 6} textAnchor="middle" className="ttl">Volatility, 3 years (a year's ups and downs, %)</text>
        <text transform={`translate(11 ${(T + H - B) / 2}) rotate(-90)`} textAnchor="middle" className="ttl">Return, 3 years per year</text>
        {pts.map(([code, name, ret, vol]) => (
          <Link key={code} to={`/funds/${code}`} aria-label={`${name}: return ${nf(ret, 1)}%, volatility ${nf(vol, 1)}%`}>
            <circle cx={X(vol)} cy={Y(ret)} r={3.6} className="dot"><title>{`${name}\n3-year return ${nf(ret, 1)}% a year, volatility ${nf(vol, 1)}%`}</title></circle>
          </Link>))}
      </svg>
      <figcaption className="faint">Each dot is a fund{data && data.eligible > data.shown ? `: the ${nf(data.shown, 0)} largest of the ${nf(data.eligible, 0)} that have both figures` : ` (${nf(pts.length, 0)} funds with both figures)`}. Past figures from month-end NAVs; the picture describes the result, it does not rank it.</figcaption>
    </figure>
  );
}

const FW = 150, FH = 46;
export function FlowBars({ flows }: { flows?: ScreenFacets["flows"] }) {
  if (!flows) return <p className="muted mfs-gl-none">Loading…</p>;
  if (!flows.length) return <p className="muted mfs-gl-none">AMFI's monthly category report has no rows for the categories in this result yet.</p>;
  return (
    <ul className="mfs-flows" aria-label="Net flow by category, last months">
      {flows.slice(0, 6).map((f) => {
        const vals = f.net.map((v) => v ?? 0), top = Math.max(1, ...vals.map(Math.abs)), bw = FW / vals.length;
        const last = f.net[f.net.length - 1];
        return (
          <li key={f.key}>
            <span className="mfs-fl-n">{f.label}</span>
            <svg viewBox={`0 0 ${FW} ${FH}`} role="img" aria-label={`${f.label}: net flow by month ${f.months.map((m, i) => `${m} ${f.net[i] == null ? "no figure" : nf(f.net[i]!, 0) + " crore"}`).join(", ")}`} className="mfs-fl">
              <line x1="0" x2={FW} y1={FH / 2} y2={FH / 2} className="ax0" />
              {vals.map((v, i) => { const h = Math.max(1.5, (Math.abs(v) / top) * (FH / 2 - 2)); return <rect key={i} x={i * bw + 3} width={bw - 6} y={v >= 0 ? FH / 2 - h : FH / 2} height={h} className={v >= 0 ? "up" : "down"}><title>{`${f.months[i]}: ${f.net[i] == null ? "no figure" : "₹" + nf(f.net[i]!, 0) + " Cr"}`}</title></rect>; })}
            </svg>
            <span className="mfs-fl-v">{last == null ? "—" : (last >= 0 ? "+" : "−") + "₹" + nf(Math.abs(last), 0) + " Cr"}<small>{f.months[f.months.length - 1]}</small></span>
          </li>);
      })}
    </ul>
  );
}
