import { useContext, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ChartHelp } from "../components/ChartHelp";
import { Gate, OpenAccess, TierChip } from "../components/Gate";
import { Icon } from "../lib/icons";
import { useSection, type Financials } from "../lib/api";
import { MINUS } from "../lib/format";
import { useUI } from "../lib/ui";
import { basisNote, fmtCr, fmtPct, isLenderLike, revenueCash, type Basis, type RevenueCash as Model, type Severity, type Status, type Warning, type Year } from "../lib/revenueCash";
import "../styles/revenue-cash.css";
import { ChartZoom } from "../components/ChartZoom";

export const DISCLAIMER = "Describes cash conversion from the company's filings; not a recommendation. Information only, not investment advice.";
const SEV_MARK: Record<Severity, string> = { Critical: "■", High: "◆", Moderate: "◇", Positive: "●" };
const STATUS_MARK: Record<Status, string> = { "Needs attention": "✕", Watch: "!", Healthy: "✓", Improving: "↗" };
const arrow = (v: number | null) => (v == null || Math.round(v * 10) === 0 ? "" : v > 0 ? "▲ " : "▼ ");

/** The revenue-to-cash model for a company, or null while locked (Gold) or still loading. */
export function useRevenueCashModel(symbol: string, lender: boolean, labels?: (string | null | undefined)[]) {
  const { has } = useUI();
  const open = useContext(OpenAccess);
  const locked = !open && !has("gold");
  const f = useSection<Financials>(symbol, "financials", !!symbol && !locked);
  const key = (labels ?? []).join("|");
  const m = useMemo(() => (locked ? null : revenueCash(f.data?.yearly.pl, f.data?.yearly.bs, f.data?.yearly.cf, { lender: isLenderLike(lender, ...(labels ?? [])), labels })), [locked, f.data, lender, key]); // eslint-disable-line react-hooks/exhaustive-deps
  return { locked, loaded: !!f.data, m };
}

/** Revenue-to-Cash Intelligence on the stock page (Gold): operating cash flow against revenue, five years, with rule-based warnings. Annual statements only. */
export function RevenueCash({ symbol, lender, labels }: { symbol: string; lender: boolean; labels?: (string | null | undefined)[] }) {
  const { has } = useUI();
  const open = useContext(OpenAccess);
  const locked = !open && !has("gold");
  const f = useSection<Financials>(symbol, "financials", !!symbol && !locked);
  const key = (labels ?? []).join("|");
  const m = useMemo(() => (locked ? null : revenueCash(f.data?.yearly.pl, f.data?.yearly.bs, f.data?.yearly.cf, { lender: isLenderLike(lender, ...(labels ?? [])), labels })), [locked, f.data, lender, key]); // eslint-disable-line react-hooks/exhaustive-deps
  const head = (
    <div className="rcx-h">
      <div>
        <h3><span className="ci"><Icon name="coins" /></span>Revenue turning into cash<ChartHelp id="revenue-cash" /></h3>
        <p className="rcx-sub">Understand how efficiently sales convert into cash.</p>
      </div>
      <TierChip tier="gold" />
    </div>
  );
  if (locked) {
    // Nothing worked out is drawn here: the locked state holds an empty outline, not figures behind a blur.
    return (
      <div className="card rcx" id="revenue-cash" aria-label="Revenue turning into cash">{head}
        <Gate tier="gold" title="Revenue-to-cash analysis" points={["Operating cash flow against revenue, five years", "Receivables and inventory against sales", "Plain-language warnings built from the filings"]}>
          <div className="rcx-skel" aria-hidden="true"><i /><i /><i /><i /></div>
        </Gate>
      </div>
    );
  }
  if (!f.data) return <div className="card rcx" id="revenue-cash" aria-label="Revenue turning into cash">{head}<div className="skeleton" style={{ height: 220 }} /></div>;
  if (!m || m.state === "nodata") return <div className="card rcx" id="revenue-cash" aria-label="Revenue turning into cash">{head}<p className="rcx-note">Revenue and cash flow are not reported for enough years to show this.</p></div>;
  if (m.state === "lender") {
    return (
      <div className="card rcx" id="revenue-cash" aria-label="Revenue turning into cash">{head}
        <div className="rcx-lender" role="status"><b>Not comparable for lenders</b><p>{m.notes[0]}</p></div>
        <p className="rcx-disc">{DISCLAIMER}</p>
      </div>
    );
  }
  return <Body m={m} head={head} />;
}

function Body({ m, head }: { m: Model; head: React.ReactNode }) {
  const L = m.latest as Year;
  return (
    <div className="card rcx" id="revenue-cash" aria-label="Revenue turning into cash">
      {head}
      <section className="rcx-sec" aria-labelledby="rcx-health">
        <h4 id="rcx-health" className="rcx-k">Cash conversion health</h4>
        <div className="rcx-health">
          <div>
            <div className={"rcx-big" + (L.ocfMargin != null && L.ocfMargin < 0 ? " neg" : "")}>{L.ocfMargin == null ? "n/a" : fmtPct(L.ocfMargin)}</div>
            <div className="rcx-cap">Operating cash flow / Revenue · {L.period}</div>
          </div>
          {m.status && <span className={"rcx-pill s-" + m.status.replace(/\s/g, "").toLowerCase()}><span aria-hidden="true">{STATUS_MARK[m.status]}</span>{m.status}</span>}
        </div>
        <p className="rcx-line">{m.statusLine} <span className="rcx-faint">{m.benchmark}.</span></p>
      </section>

      <section className="rcx-sec" aria-labelledby="rcx-trend">
        <h4 id="rcx-trend" className="rcx-k">Revenue growth and OCF margin, last five financial years</h4>
        <Trend years={m.years} />
      </section>

      <section className="rcx-sec" aria-labelledby="rcx-ind">
        <h4 id="rcx-ind" className="rcx-k">Key indicators <span className="rcx-faint">· {L.period}</span></h4>
        <div className="rcx-ind">
          <Tile label="Revenue growth" v={L.revenueGrowth} tone={L.revenueGrowth == null ? "" : L.revenueGrowth < 0 ? "bad" : "good"} sub={`${L.period} against the year before`} tip="Revenue from the annual profit and loss, this year against last year." />
          <Tile label="OCF margin" v={L.ocfMargin} tone={L.ocfMargin == null ? "" : L.ocfMargin < 0 ? "bad" : "good"} sub={L.ocf == null ? "Operating cash flow not reported" : `Operating cash flow ${fmtCr(L.ocf)}`} tip="Operating cash flow divided by revenue, from the annual cash flow statement and profit and loss." plain />
          <Tile label="Receivables growth" v={L.receivablesGrowth} tone={L.receivablesGap != null && L.receivablesGap > 0 ? "warn" : ""} sub={gapLine(L.receivablesGap)} tip={basisNote(L.receivablesBasis)} basis={L.receivablesBasis} />
          <Tile label="Inventory growth" v={L.inventoryGrowth} tone={L.inventoryGap != null && L.inventoryGap > 0 ? "warn" : ""} sub={gapLine(L.inventoryGap)} tip={basisNote(L.inventoryBasis)} basis={L.inventoryBasis} />
        </div>
      </section>

      <section className="rcx-sec" aria-labelledby="rcx-warn">
        <h4 id="rcx-warn" className="rcx-k">Automated warnings</h4>
        {m.warnings.length ? <ul className="rcx-list">{m.warnings.map((w) => <WarningRow key={w.id} w={w} />)}</ul> : <p className="rcx-note">None of the rules used here was triggered for {L.period}.</p>}
        {m.notEvaluated.length > 0 && <p className="rcx-note">{m.notEvaluated.join(" ")}</p>}
      </section>

      <section className="rcx-sec rcx-read" aria-labelledby="rcx-reading">
        <h4 id="rcx-reading" className="rcx-k">Reading the numbers</h4>
        <p>{m.reading}</p>
        <h4 className="rcx-k">What to investigate next</h4>
        <p>{m.next}</p>
      </section>
      {m.caveat && <p className="rcx-caveat"><b>{m.group === "standard" ? "" : "Industry adjustment. "}</b>{m.caveat}</p>}
      <p className="rcx-disc">{DISCLAIMER}</p>
    </div>
  );
}

export const gapLine = (gap: number | null) => (gap == null ? "No comparison with revenue growth" : `${gap > 0 ? "+" : gap < 0 ? MINUS : ""}${Math.abs(gap).toFixed(1)} points against revenue growth`);

export function Tile({ label, v, tone, sub, tip, basis, plain }: { label: string; v: number | null; tone: string; sub: string; tip: string; basis?: Basis | null; plain?: boolean }) {
  const id = "rcx-t" + useId().replace(/[^a-zA-Z0-9_-]/g, "");
  return (
    <div className={"rcx-tile " + tone}>
      <div className="rcx-tl"><span>{label}</span>
        <button type="button" className="rcx-i" aria-label={`About ${label}`} aria-describedby={id}>i</button>
        <span role="tooltip" id={id} className="rcx-tt">{tip}</span>
      </div>
      <b className="rcx-tv"><span aria-hidden="true">{arrow(v)}</span>{fmtPct(v, 1, !plain)}</b>
      <small>{sub}{basis ? ` · ${basis} balances` : ""}</small>
    </div>
  );
}

export function WarningRow({ w }: { w: Warning }) {
  return (
    <li className={"rcx-w sev-" + w.severity.toLowerCase()}>
      <div className="rcx-wh"><span className="rcx-sev"><span aria-hidden="true">{SEV_MARK[w.severity]}</span>{w.severity}</span><b>{w.text}</b><span className="rcx-pat">{w.pattern}</span></div>
      <p>{w.why}</p>
      {w.investigate && <p className="rcx-inv"><b>Investigate:</b> {w.investigate}</p>}
      {w.note && <p className="rcx-faint">{w.note}</p>}
    </li>
  );
}

/* ---------------- chart ---------------- */
function useWidth(): [React.RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(560);
  useLayoutEffect(() => {
    const el = ref.current; if (!el) return;
    const upd = () => { const x = el.clientWidth; if (x > 0) setW(x); };
    upd();
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(upd) : null; ro?.observe(el);
    return () => ro?.disconnect();
  }, []);
  return [ref, w];
}
/** Round axis ticks that always include zero. */
export function niceTicks(lo: number, hi: number, target = 5): number[] {
  const min = Math.min(0, lo), max = Math.max(0, hi), span = max - min || 1;
  const raw = span / target, mag = 10 ** Math.floor(Math.log10(raw)), step = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((s) => s >= raw) as number;
  const out: number[] = [];
  for (let t = Math.floor(min / step) * step; t <= Math.ceil(max / step) * step + step / 1e6; t += step) out.push(Math.round(t / step) * step);
  return out;
}

export function Trend({ years }: { years: Year[] }) {
  const [ref, W] = useWidth();
  const [on, setOn] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const tid = "rcx-tb" + useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const narrow = W < 480, H = narrow ? 230 : 250, ml = 46, mr = narrow ? 74 : 122, mt = 14, mb = 28;
  const rev = years.map((y) => y.revenueGrowth), ocf = years.map((y) => y.ocfMargin);
  const vals = [...rev, ...ocf].filter((v): v is number => v != null);
  const ticks = niceTicks(vals.length ? Math.min(...vals) : 0, vals.length ? Math.max(...vals) : 1);
  const lo = ticks[0], hi = ticks[ticks.length - 1];
  const pw = Math.max(40, W - ml - mr), ph = H - mt - mb;
  const x = (i: number) => ml + (years.length === 1 ? pw / 2 : (pw * i) / (years.length - 1));
  const y = (v: number) => mt + ph * (1 - (v - lo) / (hi - lo || 1));
  const segs = (s: (number | null)[]) => {
    const out: { i: number; v: number }[][] = []; let cur: { i: number; v: number }[] = [];
    s.forEach((v, i) => { if (v == null) { if (cur.length) out.push(cur); cur = []; } else cur.push({ i, v }); });
    if (cur.length) out.push(cur); return out;
  };
  const path = (seg: { i: number; v: number }[]) => seg.map((p, k) => `${k ? "L" : "M"}${x(p.i).toFixed(1)} ${y(p.v).toFixed(1)}`).join(" ");
  const lastOf = (s: (number | null)[]) => { for (let i = s.length - 1; i >= 0; i--) if (s[i] != null) return i; return -1; };
  const lab = (name: string, s: (number | null)[]) => { const i = lastOf(s); return i < 0 ? null : { name, v: s[i] as number, ty: y(s[i] as number) }; };
  const labels = [lab("Revenue growth", rev), lab("OCF margin", ocf)].filter((l): l is NonNullable<ReturnType<typeof lab>> => !!l);
  if (labels.length === 2 && Math.abs(labels[0].ty - labels[1].ty) < 40) {   // two direct labels never sit on top of each other
    const mid = (labels[0].ty + labels[1].ty) / 2, up = labels[0].ty <= labels[1].ty ? 0 : 1;
    labels[up].ty = mid - 20; labels[1 - up].ty = mid + 20;
  }
  const act = on != null ? years[on] : null;
  const aria = "Revenue growth and operating cash flow margin by financial year: " + years.map((yr) => `${yr.period} revenue growth ${fmtPct(yr.revenueGrowth, 1, true)}, OCF margin ${fmtPct(yr.ocfMargin)}`).join("; ") + ".";
  return (
    <ChartZoom label={"Revenue growth and operating cash flow margin"}>
    <div className="rcx-chart" ref={ref}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="group" aria-label={aria}>
        {ticks.map((t) => <g key={t}><line className={t === 0 ? "rcx-zero" : "rcx-gl"} x1={ml} x2={ml + pw} y1={y(t)} y2={y(t)} /><text className="rcx-ax" x={ml - 8} y={y(t) + 4} textAnchor="end">{t === 0 ? "0%" : fmtPct(t, Math.abs(t) < 10 && t % 1 !== 0 ? 1 : 0)}</text></g>)}
        {years.map((yr, i) => <text key={yr.period} className="rcx-ax" x={x(i)} y={H - 8} textAnchor="middle">{yr.period}</text>)}
        {on != null && <line className="rcx-guide" x1={x(on)} x2={x(on)} y1={mt} y2={mt + ph} />}
        {segs(rev).map((s, k) => <path key={"r" + k} className="rcx-l-rev" d={path(s)} fill="none" />)}
        {segs(ocf).map((s, k) => <path key={"o" + k} className="rcx-l-ocf" d={path(s)} fill="none" />)}
        {rev.map((v, i) => v == null ? null : <circle key={"rv" + i} className="rcx-d-rev" cx={x(i)} cy={y(v)} r={on === i ? 5 : 3.5} />)}
        {ocf.map((v, i) => v == null ? null : <rect key={"ov" + i} className="rcx-d-ocf" x={x(i) - (on === i ? 5 : 3.5)} y={y(v) - (on === i ? 5 : 3.5)} width={on === i ? 10 : 7} height={on === i ? 10 : 7} />)}
        {labels.map((l) => {
          const words = l.name.split(" "), two = narrow ? words : [l.name];
          return (
            <text key={l.name} className={"rcx-dl " + (l.name === "OCF margin" ? "ocf" : "rev")} x={ml + pw + 10} y={l.ty - (two.length * 12) / 2 + 8}>
              {two.map((w, k) => <tspan key={k} x={ml + pw + 10} dy={k ? 12 : 0}>{w}</tspan>)}
              <tspan x={ml + pw + 10} dy={12} className="rcx-dv">{fmtPct(l.v, 1, l.name === "Revenue growth")}</tspan>
            </text>
          );
        })}
        {years.map((yr, i) => {
          const step = years.length > 1 ? pw / (years.length - 1) : pw, w = Math.max(24, step);
          return <rect key={"h" + yr.period} className="rcx-hit" x={x(i) - w / 2} y={mt} width={w} height={ph + mb} tabIndex={0}
            aria-label={`${yr.period}: revenue growth ${fmtPct(yr.revenueGrowth, 1, true)}, OCF margin ${fmtPct(yr.ocfMargin)}`}
            onMouseEnter={() => setOn(i)} onMouseLeave={() => setOn((c) => (c === i ? null : c))} onFocus={() => setOn(i)} onBlur={() => setOn((c) => (c === i ? null : c))}
            onKeyDown={(e) => { if (e.key === "Escape") (e.target as SVGElement).blur(); if (e.key === "ArrowRight") { e.preventDefault(); (e.currentTarget.nextElementSibling as SVGElement | null)?.focus(); } if (e.key === "ArrowLeft") { e.preventDefault(); (e.currentTarget.previousElementSibling as SVGElement | null)?.focus(); } }} />;
        })}
      </svg>
      {act && on != null && (
        <div className="rcx-tip" role="status" style={{ left: Math.min(Math.max(x(on), 80), W - 80), top: 6 }}>
          <b>{act.period}</b>
          <span><i className="k-rev" />Revenue growth <em>{fmtPct(act.revenueGrowth, 1, true)}</em></span>
          <span><i className="k-ocf" />OCF margin <em>{fmtPct(act.ocfMargin)}</em></span>
        </div>
      )}
      <div className="rcx-legend"><span><i className="k-rev" />Revenue growth</span><span><i className="k-ocf" />OCF margin</span><span className="rcx-faint">Missing years leave a gap.</span>
        <button type="button" className="rcx-link" aria-expanded={table} aria-controls={tid} onClick={() => setTable((t) => !t)}>{table ? "Hide table" : "Show as table"}</button></div>
      {table && (
        <div id={tid} className="rcx-tblw"><table className="rcx-tbl"><thead><tr><th scope="col">Financial year</th><th scope="col">Revenue growth</th><th scope="col">OCF margin</th><th scope="col">Revenue</th><th scope="col">Operating cash flow</th></tr></thead>
          <tbody>{years.map((yr) => <tr key={yr.period}><th scope="row">{yr.period}</th><td>{fmtPct(yr.revenueGrowth, 1, true)}</td><td>{fmtPct(yr.ocfMargin)}</td><td>{fmtCr(yr.revenue)}</td><td>{fmtCr(yr.ocf)}</td></tr>)}</tbody></table></div>
      )}
    </div>
    </ChartZoom>
  );
}
