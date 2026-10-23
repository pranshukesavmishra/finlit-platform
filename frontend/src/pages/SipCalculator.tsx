// SIP calculator (free): the FinLit formula sheet, worked out month by month, with the extras an investor actually asks about: a yearly
// step-up, a one-time amount, start- or end-of-month instalments, inflation, a goal planner, what waiting costs, a range of outcomes,
// an equity capital-gains estimate, a fund's real past return as the assumption, and a link that reopens the same plan.
// All arithmetic lives in lib/sip.ts (pure and tested); this page only collects inputs and draws. Information only, not advice.
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useDocTitle } from "../lib/title";
import { useUI } from "../lib/ui";
import { csvText, dateIN, nf } from "../lib/format";
import { niceTicks } from "../lib/etf";
import { mfGet, type FundList, type FundRow } from "../lib/mf";
import {
  EQUITY_TAX_2024, LIMITS, delayCost, duration, equityTax, fromQuery, gainsOvertake, milestones, monthsToTarget, project, realValue,
  requiredMonthly, rupees, short, toInput, toQuery, type SipState, type TaxRules,
} from "../lib/sip";
import "../styles/sip.css";

const reduced = () => typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

/** A number that glides to its new value (instant when the visitor prefers less motion). */
function useGlide(target: number, ms = 450): number {
  const [v, setV] = useState(target);
  const from = useRef(target);
  useEffect(() => {
    if (reduced() || !Number.isFinite(target)) { setV(target); from.current = target; return; }
    const a = from.current, t0 = performance.now();
    let raf = 0;
    const step = (t: number) => {
      const k = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - k, 3);
      const x = a + (target - a) * e;
      setV(x); from.current = x;
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);
  return v;
}

// ------------------------------------------------------------------------------------------------------------- inputs
/** Slider positions mapped to values on a scale that is fine where people choose (small SIPs) and coarse at the top. */
type Scale = { at: number; step: number }[];
const MONTHLY_SCALE: Scale = [{ at: 100, step: 100 }, { at: 10_000, step: 500 }, { at: 100_000, step: 5_000 }, { at: 1_000_000, step: 0 }];
function scaleSteps(sc: Scale): number[] {
  const out: number[] = [];
  for (let k = 0; k < sc.length - 1; k++) for (let v = sc[k].at; v < sc[k + 1].at; v += sc[k].step) out.push(v);
  out.push(sc[sc.length - 1].at);
  return out;
}
const MONTHLY_STOPS = scaleSteps(MONTHLY_SCALE);
const nearestStop = (stops: number[], v: number) => { let best = 0; for (let k = 1; k < stops.length; k++) if (Math.abs(stops[k] - v) < Math.abs(stops[best] - v)) best = k; return best; };

function Field({ label, value, onChange, min, max, step, prefix, suffix, stops, hint, marks, digits = 0 }: {
  label: string; value: number; onChange: (v: number) => void; min: number; max: number; step?: number; prefix?: string; suffix?: string;
  stops?: number[]; hint?: string; marks?: string[]; digits?: number;
}) {
  const id = useId();
  const [text, setText] = useState(nf(value, digits));
  const [editing, setEditing] = useState(false);
  useEffect(() => { if (!editing) setText(value.toLocaleString("en-IN", { maximumFractionDigits: digits })); }, [value, editing, digits]);
  const pos = stops ? nearestStop(stops, value) : value;
  const lo = stops ? 0 : min, hi = stops ? stops.length - 1 : max;
  const fill = hi > lo ? ((Math.min(Math.max(pos, lo), hi) - lo) / (hi - lo)) * 100 : 0;
  const commit = (s: string) => {
    const v = Number(s.replace(/[,\s₹%]/g, ""));
    if (Number.isFinite(v)) onChange(Math.min(max, Math.max(min, Math.round(v * 10 ** digits) / 10 ** digits)));
    setEditing(false);
  };
  return (
    <div className="sip-f">
      <div className="sip-f-h">
        <label htmlFor={id}>{label}</label>
        <span className="sip-box">
          {prefix && <i>{prefix}</i>}
          <input id={id} inputMode="decimal" value={text} aria-describedby={hint ? id + "h" : undefined}
            onFocus={(e) => { setEditing(true); e.currentTarget.select(); }} onChange={(e) => setText(e.target.value)} onBlur={(e) => commit(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") commit((e.target as HTMLInputElement).value); }} />
          {suffix && <i>{suffix}</i>}
        </span>
      </div>
      <input type="range" className="sip-range" aria-label={label} min={lo} max={hi} step={stops ? 1 : step ?? 1} value={Math.min(Math.max(pos, lo), hi)}
        style={{ "--fill": `${fill}%` } as React.CSSProperties}
        aria-valuetext={`${prefix || ""}${value.toLocaleString("en-IN")}${suffix ? " " + suffix : ""}`}
        onChange={(e) => onChange(stops ? stops[Number(e.target.value)] : Number(e.target.value))} />
      {marks && <div className="sip-marks" aria-hidden="true">{marks.map((m) => <span key={m}>{m}</span>)}</div>}
      {hint && <p className="sip-hint" id={id + "h"}>{hint}</p>}
    </div>
  );
}

function Seg<T extends string>({ value, options, onChange, label }: { value: T; options: [T, string][]; onChange: (v: T) => void; label: string }) {
  return (
    <div className="sip-seg" role="radiogroup" aria-label={label}>
      {options.map(([k, l]) => <button key={k} type="button" role="radio" aria-checked={value === k} className={value === k ? "on" : ""} onClick={() => onChange(k)}>{l}</button>)}
    </div>
  );
}

// ------------------------------------------------------------------------------------------------------------- donut
function Donut({ invested, gain, value }: { invested: number; gain: number; value: number }) {
  const r = 70, c = 2 * Math.PI * r, total = Math.max(1, invested + Math.max(0, gain));
  const inv = (invested / total) * c;
  const shown = useGlide(value);
  return (
    <div className="sip-donut">
      <svg viewBox="0 0 180 180" role="img" aria-label={`Invested ${rupees(invested)}, gained ${rupees(gain)}`}>
        <defs><linearGradient id="sipGain" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="var(--gold-2)" /><stop offset="1" stopColor="var(--gold-deep)" /></linearGradient></defs>
        <circle cx="90" cy="90" r={r} className="sip-d-bg" />
        <circle cx="90" cy="90" r={r} className="sip-d-gain" strokeDasharray={`${c} ${c}`} />
        <circle cx="90" cy="90" r={r} className="sip-d-inv" strokeDasharray={`${inv} ${c}`} />
      </svg>
      <div className="sip-d-c"><span>Expected amount</span><b>{short(shown)}</b><small>{(invested ? value / invested : 0).toFixed(2)}× what you put in</small></div>
    </div>
  );
}

// ------------------------------------------------------------------------------------------------------------- growth chart
type Band = { lo: number[]; hi: number[]; loRate: number; hiRate: number } | null;
function GrowthChart({ s, band }: { s: SipState; band: Band }) {
  const r = useMemo(() => project(toInput(s)), [s]);
  const [hover, setHover] = useState<number | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(880);
  useEffect(() => {
    const el = box.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(300, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  // drawn at the size it is shown, so labels stay readable on a phone instead of shrinking with the picture
  const W = width, H = width < 600 ? 250 : 320, L = width < 600 ? 50 : 64, R = 14, T = 24, B = 30;
  const n = r.n || 1;
  const top = Math.max(r.value, band ? band.hi[band.hi.length - 1] : 0, 1);
  const ticks = niceTicks(0, top, 5);
  const ymax = Math.max(top, ticks[ticks.length - 1] || top);
  const X = (m: number) => L + (m / n) * (W - L - R), Y = (v: number) => T + (1 - v / ymax) * (H - T - B);
  const pts = r.monthly;
  const path = (get: (k: number) => number) => pts.map((p, k) => `${k ? "L" : "M"}${X(p.m).toFixed(1)} ${Y(get(k)).toFixed(1)}`).join("");
  const valueLine = path((k) => pts[k].value), invLine = path((k) => pts[k].invested);
  const area = (line: string) => `${line}L${X(n)} ${Y(0)}L${X(0)} ${Y(0)}Z`;
  const yearsTotal = n / 12, slots = Math.max(4, Math.floor(W / 70));
  const everyY = [1, 2, 5, 10, 25].find((k) => yearsTotal / k <= slots) ?? 25;
  const xt: number[] = []; for (let y = 0; y <= yearsTotal; y += everyY) xt.push(y * 12);
  const ms = milestones(r).filter((x) => x.m < n).slice(-4);
  const over = gainsOvertake(r);
  const hv = hover == null ? null : pts[Math.round(hover)];
  const move = (e: React.PointerEvent) => {
    const box = svg.current!.getBoundingClientRect();
    const x = ((e.clientX - box.left) / box.width) * W;
    setHover(Math.max(0, Math.min(n, ((x - L) / (W - L - R)) * n)));
  };
  const key = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") { e.preventDefault(); setHover((h) => Math.max(0, Math.min(n, Math.round((h ?? n) + (e.key === "ArrowRight" ? 12 : -12))))); }
    if (e.key === "Escape") setHover(null);
  };
  return (
    <div className="sip-chart" ref={box}>
      <svg ref={svg} viewBox={`0 0 ${W} ${H}`} role="img" tabIndex={0} aria-label={`Value grows to ${rupees(r.value)} over ${duration(n)} against ${rupees(r.invested)} put in. Use the left and right arrow keys to read each year.`}
        onPointerMove={move} onPointerLeave={() => setHover(null)} onKeyDown={key}>
        <defs>
          <linearGradient id="sipV" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="var(--gold)" stopOpacity=".42" /><stop offset="1" stopColor="var(--gold)" stopOpacity=".02" /></linearGradient>
          <linearGradient id="sipI" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="var(--k1)" stopOpacity=".38" /><stop offset="1" stopColor="var(--k1)" stopOpacity=".06" /></linearGradient>
        </defs>
        {ticks.map((t) => <g key={t} className="sip-grid"><line x1={L} x2={W - R} y1={Y(t)} y2={Y(t)} /><text x={L - 10} y={Y(t) + 4} textAnchor="end">{short(t)}</text></g>)}
        {xt.map((m) => <text key={m} className="sip-xt" x={X(m)} y={H - 10} textAnchor="middle">{m === 0 ? "Now" : `${m / 12}y`}</text>)}
        {band && <path className="sip-band" d={band.hi.map((v, k) => `${k ? "L" : "M"}${X(k).toFixed(1)} ${Y(v).toFixed(1)}`).join("") + band.lo.map((_, k) => `L${X(band.lo.length - 1 - k).toFixed(1)} ${Y(band.lo[band.lo.length - 1 - k]).toFixed(1)}`).join("") + "Z"} />}
        <path d={area(valueLine)} fill="url(#sipV)" className="sip-a" />
        <path d={area(invLine)} fill="url(#sipI)" />
        <path d={invLine} className="sip-l-inv" />
        <path d={valueLine} className="sip-l-val" />
        {over != null && over < n && W >= 520 && <g className="sip-over"><line x1={X(over)} x2={X(over)} y1={T} y2={H - B} /><text x={X(over) + (over > n * 0.6 ? -6 : 6)} y={T + 12} textAnchor={over > n * 0.6 ? "end" : "start"}>Gains pass what you put in · {duration(over)}</text></g>}
        {ms.map((x) => <g key={x.amount} className="sip-ms"><circle cx={X(x.m)} cy={Y(pts[x.m].value)} r="4.5" /><text x={X(x.m)} y={Y(pts[x.m].value) - 10} textAnchor="middle">{short(x.amount)}</text></g>)}
        {hv && (
          <g className="sip-hover">
            <line x1={X(hv.m)} x2={X(hv.m)} y1={T} y2={H - B} />
            <circle cx={X(hv.m)} cy={Y(hv.value)} r="5.5" className="v" /><circle cx={X(hv.m)} cy={Y(hv.invested)} r="4.5" className="i" />
          </g>
        )}
      </svg>
      {hv && (
        <div className="sip-tip" style={{ left: `${(X(hv.m) / W) * 100}%` }} role="status">
          <b>{hv.m === 0 ? "Start" : duration(hv.m)}</b>
          <span><i className="v" />Value <em>{rupees(hv.value)}</em></span>
          <span><i className="i" />Put in <em>{rupees(hv.invested)}</em></span>
          <span><i className="g" />Gained <em>{rupees(hv.value - hv.invested)}</em></span>
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------------------------------------------------- page
const TABS = [["table", "Year by year"], ["goal", "Goal planner"], ["wait", "Cost of waiting"], ["tax", "After tax"], ["how", "How it is worked out"]] as const;
type TabKey = (typeof TABS)[number][0];

export function SipCalculator() {
  useDocTitle("SIP calculator", "SIP calculator: the future value of a monthly investment, with step-up, lump sum, inflation, a goal planner, the cost of waiting and an after-tax estimate. Every step shown.");
  const [sp, setSp] = useSearchParams();
  const [s, setS] = useState<SipState>(() => fromQuery(sp));
  const [more, setMore] = useState(() => s.stepKind !== "none" || s.lumpSum > 0 || s.timing !== "end" || s.compounding !== "monthly");
  const [tab, setTab] = useState<TabKey>("table");
  const [showBand, setShowBand] = useState(true);
  const { toast } = useUI();
  const set = <K extends keyof SipState>(k: K, v: SipState[K]) => setS((x) => ({ ...x, [k]: v }));

  // keep the address in step (so the link shares this exact plan), without adding history entries
  useEffect(() => { const t = window.setTimeout(() => setSp(new URLSearchParams(toQuery(s)), { replace: true }), 250); return () => window.clearTimeout(t); }, [s, setSp]);

  const inp = useMemo(() => toInput(s), [s]);
  const r = useMemo(() => project(inp), [inp]);
  const band = useMemo<Band>(() => {
    if (!showBand) return null;
    const loRate = Math.max(0, s.annualReturn - 3), hiRate = Math.min(LIMITS.returnMax, s.annualReturn + 3);
    return { lo: project({ ...inp, annualReturn: loRate }).monthly.map((x) => x.value), hi: project({ ...inp, annualReturn: hiRate }).monthly.map((x) => x.value), loRate, hiRate };
  }, [inp, s.annualReturn, showBand]);
  const real = realValue(r.value, s.inflation, r.n);
  const value = useGlide(r.value), invested = useGlide(r.invested), gain = useGlide(r.gain);

  const copyLink = async () => { try { await navigator.clipboard.writeText(location.href); toast("Link copied: it opens the calculator with this exact plan."); } catch { toast("Copy the address from the browser bar."); } };
  const csv = () => {
    const rows = [["FinLit SIP calculator", new Date().toISOString().slice(0, 10)], [], ["Monthly SIP", s.monthly], ["Years", s.years + s.months / 12], ["Expected annual return %", s.annualReturn],
      ["Instalments", s.timing === "end" ? "end of each month" : "start of each month"], ["Compounding", s.compounding === "monthly" ? "monthly rate = annual / 12" : "effective annual"],
      ["Step-up", s.stepKind === "none" ? "none" : s.stepKind === "pct" ? `${s.stepValue}% a year` : `Rs ${s.stepValue} a year`], ["One-time amount", s.lumpSum], [],
      ["Year", "Monthly SIP that year", "Put in that year", "Total put in", "Value at year end", "Gained"],
      ...r.years.map((y) => [y.year, Math.round(y.sip), Math.round(y.investedInYear), Math.round(y.invested), Math.round(y.value), Math.round(y.gain)])];
    const blob = new Blob([rows.map((x) => x.map((c) => `"${csvText(String(c)).replace(/"/g, '""')}"`).join(",")).join("\n")], { type: "text/csv" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "finlit-sip-plan.csv"; a.click(); URL.revokeObjectURL(a.href);
  };

  return (
    <div className="sip-page">
      <section className="sip-hero">
        <div className="wrap">
          <div className="eyebrow">Free tool · no sign-in</div>
          <h1>SIP calculator</h1>
          <p>Estimate what a monthly investment could grow to, see every year of it, plan for a goal, and check what waiting or tax does to it. Every figure is worked out the same way as the formula shown below.</p>
        </div>
      </section>

      <div className="wrap sip-wrap">
        <section className="sip-card sip-main" aria-label="Calculator">
          <div className="sip-in">
            <Field label="Monthly investment" value={s.monthly} onChange={(v) => set("monthly", v)} min={LIMITS.monthlyMin} max={LIMITS.monthlyMax} prefix="₹" stops={MONTHLY_STOPS} marks={["₹100", "₹10k", "₹1 L", "₹10 L"]} />
            <Field label="Investment period" value={s.years} onChange={(v) => set("years", Math.round(v))} min={1} max={LIMITS.yearsMax} suffix="years" marks={["1", "10", "20", "30", "40", "50"]} />
            <Field label="Expected annual return" value={s.annualReturn} onChange={(v) => set("annualReturn", v)} min={0} max={LIMITS.returnMax} step={0.5} suffix="%" digits={2} marks={["0%", "10%", "20%", "30%"]}
              hint="Not a promise: markets do not grow by the same amount every year." />
            <FundPicker onPick={(rate, label) => { set("annualReturn", Math.round(rate * 100) / 100); toast(`Using ${label}`); }} />
            <button type="button" className="sip-more" aria-expanded={more} onClick={() => setMore((v) => !v)}>{more ? "Fewer options" : "More options: step-up, one-time amount, timing"} <span aria-hidden="true">{more ? "−" : "+"}</span></button>
            {more && (
              <div className="sip-opts">
                <div className="sip-opt">
                  <span className="sip-ol">Raise the SIP every year</span>
                  <Seg label="Step-up" value={s.stepKind} onChange={(v) => set("stepKind", v)} options={[["none", "No"], ["pct", "By %"], ["amount", "By ₹"]]} />
                  {s.stepKind !== "none" && <Field label={s.stepKind === "pct" ? "Yearly step-up" : "Yearly step-up amount"} value={s.stepValue} onChange={(v) => set("stepValue", v)} min={0} max={s.stepKind === "pct" ? 50 : 100000}
                    step={s.stepKind === "pct" ? 1 : 500} prefix={s.stepKind === "amount" ? "₹" : undefined} suffix={s.stepKind === "pct" ? "%" : undefined} />}
                </div>
                <Field label="One-time amount at the start" value={s.lumpSum} onChange={(v) => set("lumpSum", v)} min={0} max={LIMITS.lumpMax} prefix="₹" stops={[0, ...MONTHLY_STOPS.map((x) => x * 10)]} hint="Optional: money you already have to invest on day one." />
                <div className="sip-opt"><span className="sip-ol">Each instalment is paid</span>
                  <Seg label="Instalment timing" value={s.timing} onChange={(v) => set("timing", v)} options={[["end", "End of month"], ["start", "Start of month"]]} />
                  <p className="sip-hint">The formula sheet uses the end of the month. Paying at the start gives every instalment one more month of growth; many apps use it, which is why their figures run a little higher.</p></div>
                <div className="sip-opt"><span className="sip-ol">Monthly rate</span>
                  <Seg label="Compounding" value={s.compounding} onChange={(v) => set("compounding", v)} options={[["monthly", "Annual ÷ 12"], ["effective", "Effective annual"]]} />
                  <p className="sip-hint">{s.compounding === "monthly" ? `Annual ÷ 12 (the formula sheet): ${s.annualReturn}% a year compounds to ${nf((Math.pow(1 + s.annualReturn / 1200, 12) - 1) * 100, 2)}% over a year.` : `Effective: the monthly rate that compounds to exactly ${s.annualReturn}% over a year (${nf(r.i * 100, 4)}% a month).`}</p></div>
              </div>
            )}
          </div>

          <div className="sip-mid"><Donut invested={r.invested} gain={r.gain} value={r.value} />
            <ul className="sip-legend"><li><i className="inv" />Invested</li><li><i className="gain" />Wealth gained</li></ul></div>

          <div className="sip-out">
            <div className="sip-kv"><span>Invested amount</span><b>{rupees(invested)}</b></div>
            <div className="sip-kv gain"><span>Wealth gained</span><b>{rupees(gain)}</b></div>
            <div className="sip-big"><span>Expected amount</span><b>{rupees(value)}</b><small>after {duration(r.n)}{s.lumpSum ? `, including ${rupees(r.lumpValue)} from the one-time amount` : ""}</small></div>
            <div className="sip-real">
              <div><span>In today's money</span><b>{rupees(real)}</b></div>
              <label>at <input type="number" min={0} max={20} step={0.5} value={s.inflation} onChange={(e) => set("inflation", Math.min(20, Math.max(0, Number(e.target.value) || 0)))} aria-label="Inflation a year in per cent" />% inflation a year</label>
            </div>
            <div className="sip-acts">
              <Link className="btn primary" to="/funds">Find funds to compare</Link>
              <button type="button" className="btn" onClick={copyLink}>Copy link</button>
              <button type="button" className="btn" onClick={csv}>Download CSV</button>
            </div>
          </div>
        </section>

        <section className="sip-card" aria-labelledby="sipGrowth">
          <div className="sip-ch">
            <div><h2 id="sipGrowth">How it grows</h2><p>Hover or use the arrow keys to read any year. Dots mark round amounts.</p></div>
            <label className="sip-tog"><input type="checkbox" checked={showBand} onChange={(e) => setShowBand(e.target.checked)} /><span />Range if returns are 3 points lower or higher</label>
          </div>
          <GrowthChart s={s} band={band} />
          <ul className="sip-keys">
            <li><i className="v" />Value</li><li><i className="i" />Money put in</li>
            {band && <li><i className="b" />{band.loRate}% to {band.hiRate}% a year: {short(band.lo[band.lo.length - 1])} to {short(band.hi[band.hi.length - 1])}</li>}
          </ul>
        </section>

        <section className="sip-card">
          <div className="sip-tabs" role="tablist" aria-label="More about this plan">
            {TABS.map(([k, l]) => <button key={k} type="button" role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>{l}</button>)}
          </div>
          <div role="tabpanel" className="sip-pane">
            {tab === "table" && <YearTable s={s} />}
            {tab === "goal" && <GoalPlanner s={s} />}
            {tab === "wait" && <Waiting s={s} />}
            {tab === "tax" && <TaxPane s={s} />}
            {tab === "how" && <HowItWorks s={s} />}
          </div>
        </section>

        <p className="sip-disc">Information only, not investment advice. A SIP calculator assumes the same return every month; real funds go up and down, and past returns do not guarantee future returns. Mutual fund investments are subject to market risks; read all scheme-related documents carefully.</p>
      </div>
    </div>
  );
}

// ------------------------------------------------------------------------------------------------------------- tabs
function YearTable({ s }: { s: SipState }) {
  const r = useMemo(() => project(toInput(s)), [s]);
  const step = s.stepKind !== "none";
  return (
    <div className="sip-tw">
      <table className="sip-t">
        <thead><tr><th>Year</th>{step && <th>Monthly SIP</th>}<th>Put in that year</th><th>Total put in</th><th>Value at year end</th><th>Gained</th><th className="bar">Gained share</th></tr></thead>
        <tbody>{r.years.map((y) => {
          const share = y.value > 0 ? (y.gain / y.value) * 100 : 0;
          return (
            <tr key={y.year}>
              <td>{Number.isInteger(y.year) ? y.year : duration(Math.round(y.year * 12))}</td>{step && <td>{rupees(y.sip)}</td>}<td>{rupees(y.investedInYear)}</td><td>{rupees(y.invested)}</td>
              <td><b>{rupees(y.value)}</b></td><td className="g">{rupees(y.gain)}</td>
              <td className="bar"><span><i style={{ width: `${Math.max(0, share)}%` }} /></span><em>{nf(share, 0)}%</em></td>
            </tr>
          );
        })}</tbody>
      </table>
    </div>
  );
}

function GoalPlanner({ s }: { s: SipState }) {
  const [goal, setGoal] = useState(10_000_000);
  const [today, setToday] = useState(true);
  const months = s.years * 12 + s.months;
  const target = today ? goal * Math.pow(1 + s.inflation / 100, months / 12) : goal;
  const base = { years: s.years, months: s.months, annualReturn: s.annualReturn, timing: s.timing, compounding: s.compounding, lumpSum: s.lumpSum, stepUp: { kind: s.stepKind, value: s.stepValue } };
  const need = requiredMonthly(target, base);
  const when = monthsToTarget(target, { monthly: s.monthly, annualReturn: s.annualReturn, timing: s.timing, compounding: s.compounding, lumpSum: s.lumpSum, stepUp: { kind: s.stepKind, value: s.stepValue } });
  const presets = [2_500_000, 5_000_000, 10_000_000, 50_000_000];
  return (
    <div className="sip-goal">
      <div className="sip-goal-in">
        <Field label="Your goal" value={goal} onChange={setGoal} min={10_000} max={1_000_000_000} prefix="₹" stops={[...scaleSteps([{ at: 100_000, step: 100_000 }, { at: 10_000_000, step: 500_000 }, { at: 100_000_000, step: 5_000_000 }, { at: 1_000_000_000, step: 0 }])]} />
        <div className="sip-chips">{presets.map((p) => <button key={p} type="button" className={goal === p ? "on" : ""} onClick={() => setGoal(p)}>{short(p)}</button>)}</div>
        <label className="sip-tog"><input type="checkbox" checked={today} onChange={(e) => setToday(e.target.checked)} /><span />The goal is in today's money (grow it by {s.inflation}% inflation a year)</label>
      </div>
      <div className="sip-goal-out">
        <div className="sip-gc"><span>To reach {short(target)}{today ? ` (${short(goal)} today)` : ""} in {duration(months)}</span>
          <b>{need == null ? "—" : `${rupees(need)} a month`}</b>
          <small>{need === 0 ? "The one-time amount alone gets there." : s.stepKind !== "none" ? `in the first year, then raised ${s.stepKind === "pct" ? `${s.stepValue}%` : rupees(s.stepValue)} every year` : `at ${s.annualReturn}% a year`}</small></div>
        <div className="sip-gc"><span>With your {rupees(s.monthly)} a month</span>
          <b>{when == null ? "Not within 50 years" : duration(when)}</b>
          <small>{when == null ? "Raise the SIP, the return or add a step-up." : `to reach ${short(target)}${months && when > months ? `, ${duration(when - months)} longer than your plan` : ""}`}</small></div>
      </div>
    </div>
  );
}

function Waiting({ s }: { s: SipState }) {
  const inp = toInput(s);
  const full = project(inp);
  const rows = [1, 3, 5, 10].filter((d) => d * 12 < full.n).map((d) => ({ d, ...delayCost(inp, d) }));
  if (!rows.length) return <p className="sip-note">Make the plan longer than a year to see what starting later costs.</p>;
  const max = full.value;
  return (
    <div className="sip-wait">
      <p className="sip-note">The same SIP, started later but stopping on the same date. Waiting costs far more than the instalments skipped, because the earliest money compounds the longest.</p>
      <div className="sip-wbars">
        <div className="sip-wrow now"><span>Start now</span><i><em style={{ width: "100%" }} /></i><b>{rupees(full.value)}</b></div>
        {rows.map((x) => (
          <div key={x.d} className="sip-wrow"><span>Wait {x.d} year{x.d === 1 ? "" : "s"}</span><i><em style={{ width: `${(x.value / max) * 100}%` }} /></i>
            <b>{rupees(x.value)}<small>{rupees(x.lost)} less, though only {rupees(x.investedLess)} less was put in</small></b></div>
        ))}
      </div>
    </div>
  );
}

function TaxPane({ s }: { s: SipState }) {
  const [rules, setRules] = useState<TaxRules>(EQUITY_TAX_2024);
  const t = equityTax(toInput(s), rules);
  const r = project(toInput(s));
  const setR = (k: keyof TaxRules, v: string) => setRules((x) => ({ ...x, [k]: Math.max(0, Number(v) || 0) }));
  return (
    <div className="sip-tax">
      <div className="sip-tax-out">
        <div className="sip-gc"><span>Value before tax</span><b>{rupees(r.value)}</b></div>
        <div className="sip-gc"><span>Estimated tax if all of it is sold at the end</span><b className="neg">{rupees(t.tax)}</b><small>long-term gain {rupees(t.longGain)}, short-term gain {rupees(t.shortGain)}</small></div>
        <div className="sip-gc hi"><span>After tax</span><b>{rupees(t.afterTax)}</b><small>{nf(r.value ? (t.tax / r.value) * 100 : 0, 1)}% of the value goes in tax</small></div>
      </div>
      <details className="sip-rules">
        <summary>Tax rules used (equity funds, from 23 July 2024) · change them</summary>
        <div className="sip-rule-in">
          <label>Long-term rate <input type="number" step="0.5" value={rules.ltcgPct} onChange={(e) => setR("ltcgPct", e.target.value)} />%</label>
          <label>Yearly long-term exemption ₹<input type="number" step="5000" value={rules.exemption} onChange={(e) => setR("exemption", e.target.value)} /></label>
          <label>Short-term rate <input type="number" step="0.5" value={rules.stcgPct} onChange={(e) => setR("stcgPct", e.target.value)} />%</label>
          <label>Cess <input type="number" step="1" value={rules.cessPct} onChange={(e) => setR("cessPct", e.target.value)} />%</label>
          <button type="button" className="btn" onClick={() => setRules(EQUITY_TAX_2024)}>Reset</button>
        </div>
        <p className="sip-hint">Each instalment is its own purchase: held more than 12 months it is long-term, otherwise short-term. Assumes everything is sold in one financial year, no other gains that year, and no surcharge. Debt funds are taxed at your slab rate and are not modelled. Tax rules change; check the current rules or ask a tax adviser.</p>
      </details>
    </div>
  );
}

function HowItWorks({ s }: { s: SipState }) {
  const r = project(toInput(s));
  const plain = s.stepKind === "none" && !s.lumpSum && s.timing === "end" && s.compounding === "monthly" && !s.months;
  return (
    <div className="sip-how">
      <div className="sip-formula" aria-label="FV equals P times the quantity one plus i to the power n minus one, divided by i">
        <span>FV</span><span>=</span><span>P</span><span>×</span>
        <span className="frac"><span>(1 + i)<sup>n</sup> − 1</span><span>i</span></span>
      </div>
      <dl className="sip-vars">
        <div><dt>P</dt><dd>monthly SIP: {rupees(s.monthly)}</dd></div>
        <div><dt>i</dt><dd>monthly rate: {s.compounding === "monthly" ? `${s.annualReturn} ÷ 1200 = ` : ""}{nf(r.i, 6)}</dd></div>
        <div><dt>n</dt><dd>number of instalments: {s.months ? `12 × ${s.years} + ${s.months}` : `12 × ${s.years}`} = {r.n}</dd></div>
        <div><dt>FV</dt><dd>{plain ? <>{rupees(s.monthly)} × ((1 + {nf(r.i, 6)})<sup>{r.n}</sup> − 1) ÷ {nf(r.i, 6)} = <b>{rupees(r.value)}</b></> : <>worked out month by month with your options: <b>{rupees(r.value)}</b></>}</dd></div>
      </dl>
      <ul className="sip-how-l">
        <li>Total invested = P × n{s.stepKind !== "none" || s.lumpSum ? " (with the step-up and the one-time amount added)" : ""} = {rupees(r.invested)}. Wealth gained = FV − total invested = {rupees(r.gain)}.</li>
        <li>{s.timing === "end" ? "Instalments at the end of each month (the formula above)." : "Instalments at the start of each month: the formula above × (1 + i)."}</li>
        <li>Every figure is calculated to full precision and rounded to the rupee only on screen. With no options, the month-by-month result equals the formula exactly.</li>
        <li>Today's money divides the value by (1 + inflation) for every year: {rupees(r.value)} ÷ (1 + {s.inflation}%)<sup>{nf(r.n / 12, r.n % 12 ? 2 : 0)}</sup> = {rupees(realValue(r.value, s.inflation, r.n))}.</li>
      </ul>
    </div>
  );
}

// ------------------------------------------------------------------------------------------------------------- a real fund's return
function FundPicker({ onPick }: { onPick: (rate: number, label: string) => void }) {
  const [q, setQ] = useState(""), [open, setOpen] = useState(false);
  const [dq, setDq] = useState("");
  useEffect(() => { const t = window.setTimeout(() => setDq(q.trim()), 220); return () => window.clearTimeout(t); }, [q]);
  const res = useQuery<FundList>({ queryKey: ["sip", "mf", dq], queryFn: () => mfGet(`/api/mf?q=${encodeURIComponent(dq)}&size=8&plan=Direct`), enabled: dq.length >= 3, staleTime: 300_000, placeholderData: keepPreviousData, retry: 0 });
  const items = (res.data?.items || []).filter((f: FundRow) => f.r5y != null || f.r1y != null).slice(0, 6);
  if (!open) return <button type="button" className="sip-link" onClick={() => setOpen(true)}>Use a real fund's past return instead</button>;
  return (
    <div className="sip-fund">
      <input className="sip-fund-q" placeholder="Fund name, e.g. flexi cap, Nifty 50 index" value={q} autoFocus onChange={(e) => setQ(e.target.value)} aria-label="Search for a fund" />
      {dq.length >= 3 && (
        <ul>
          {res.isFetching && !items.length && <li className="muted">Searching…</li>}
          {!res.isFetching && !items.length && <li className="muted">No fund with a 1- or 5-year return matches.</li>}
          {items.map((f) => {
            const rate = f.r5y ?? f.r1y!, basis = f.r5y != null ? "5 years, per year" : "1 year";
            return (
              <li key={f.code}><button type="button" onClick={() => { onPick(Math.max(0, Math.min(LIMITS.returnMax, rate)), `${f.name.replace(/\s*-\s*Direct.*$/i, "")}: ${nf(rate, 2)}% over ${basis}`); setOpen(false); setQ(""); }}>
                <span>{f.name.replace(/\s*-\s*Direct.*$/i, "")}<small>{f.amc.replace(/ Mutual Fund$/i, "")}{f.retDate ? ` · to ${dateIN(f.retDate, { day: "numeric", month: "short", year: "numeric" })}` : ""}</small></span>
                <b>{nf(rate, 2)}%<small>{basis}</small></b>
              </button></li>
            );
          })}
        </ul>
      )}
      <p className="sip-hint">Direct plan returns from AMFI's NAV history. A past return is a reference point, not a forecast.{" "}<button type="button" className="sip-link" onClick={() => setOpen(false)}>Close</button></p>
    </div>
  );
}
