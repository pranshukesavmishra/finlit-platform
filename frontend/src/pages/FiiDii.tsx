// FII / DII data today (free): the latest institutional cash-market flows, streaks, an interactive history (cumulative lines or daily bars with a
// 20-session average), calendars, who absorbs the selling, streak records, monthly and yearly tables, period comparison, F&O positioning, FPI
// all-asset flows, a searchable day-by-day table with a CSV of the whole history, and an honest account of sources. Everything is computed in the
// browser from the /api/flows payload (lib/flowsMath.ts, tested). Where a figure is not published it shows a dash and says why; nothing is
// estimated. Information only, not investment advice.
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useDocTitle } from "../lib/title";
import { useUI } from "../lib/ui";
import { MINUS, dateIN, nf } from "../lib/format";
import { useFlows, type Flows, type FlowDay, type Period, type Side, type Streak } from "../lib/flows";
import {
  RANGES, absorption, ageLabel, combined, commonSpan, corrWords, cumulative, diiGap, diiState, filterDays, grp, indexCorrelation, inr, isRange, level, monthGrid,
  movingAverage, netOf, percentileOf, perDay, rangeRows, sinceMonths, sortDays, splitOf, summarize, toCsv, topRuns, totalSince, type RangeKey, type SideKey, type SortKey,
} from "../lib/flowsMath";
import { BarChart, CAL_LEGEND, CalendarHeat, LineChart } from "../components/FlowsCharts";
import "../styles/flows.css";

const tone = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "gain" : "loss");
const arrow = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "▲ " : "▼ ");
const longDate = (d: string) => dateIN(d, { weekday: "short", day: "numeric", month: "short", year: "numeric" });
const NO_DII = "DII figures are not available from the sources this site can use, so the DII visuals are switched off rather than shown as zeros.";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const compactCr = (v: number) => { const a = Math.abs(v), s = v < 0 ? MINUS : ""; return a >= 100000 ? `${s}${nf(a / 100000, 2)}L` : a >= 10000 ? `${s}${nf(a / 1000, 1)}k` : `${s}${grp(a)}`; };

type Ctx = { f: Flows; st: "full" | "partial" | "none"; range: RangeKey; setRange: (r: RangeKey) => void; view: "cum" | "bars"; setView: (v: "cum" | "bars") => void; day: string | null; setDay: (d: string | null) => void };

// ------------------------------------------------------------------------------------------------------------- latest session
function SideFig({ name, s, word }: { name: string; s: Side | null; word: string }) {
  const n = s?.net ?? null;
  return (
    <div className="fl-fig">
      <div className="l"><span>{name}</span><span>{n == null ? "" : n > 0 ? "Net bought" : n < 0 ? "Net sold" : "Flat"}</span></div>
      <b className={"big " + tone(n)}>{n == null ? "—" : <>{arrow(n)}{inr(n)}</>}</b>
      <div className="w" style={{ color: "var(--muted)" }}>{word}</div>
      <div className="g"><span>Buy <b>{inr(s?.buy ?? null)}</b></span><span>Sell <b>{inr(s?.sell ?? null)}</b></span></div>
    </div>
  );
}
function Latest({ f, st }: Pick<Ctx, "f" | "st">) {
  const l = f.latest; if (!l) return <section className="fl-panel"><p className="fl-na">No session has been published yet.</p></section>;
  const sp = splitOf(l), comb = l.dii?.net != null && l.fii.net != null ? l.fii.net + l.dii.net : null;
  return (
    <section className="fl-panel fl-latest" aria-labelledby="flLatest">
      <div className="fl-ph"><h2 id="flLatest">Latest session</h2><span className="fl-date">{longDate(l.d)} · {ageLabel(l.d, f.today)}</span></div>
      <div className="fl-two">
        <SideFig name="FII / FPI" s={l.fii} word="Foreign portfolio investors, cash market" />
        {l.dii ? <SideFig name="DII" s={l.dii} word="Domestic institutions, cash market" /> : <div className="fl-fig"><div className="l"><span>DII</span></div><b className="big">—</b><div className="w" style={{ color: "var(--muted)" }}>{st === "none" ? "Not published to us" : "No figure for this session"}</div></div>}
      </div>
      <div className="fl-comb"><span>Net combined (FII + DII)</span><b className={tone(comb)}>{comb == null ? "—" : <>{arrow(comb)}{inr(comb)}</>}</b></div>
      {sp ? (
        <div className="fl-split" role="img" aria-label={`${sp.left.label} ${sp.left.pct} per cent, ${sp.right.label} ${sp.right.pct} per cent of the day's net activity`}>
          <div className="fl-split-t"><span className={sp.left.side === "buying" ? "gain" : "loss"}>{sp.left.side === "buying" ? "▲" : "▼"} {sp.left.label} {sp.left.pct}%</span><span className={sp.right.side === "buying" ? "gain" : "loss"}>{sp.right.pct}% {sp.right.label}</span></div>
          <div className="fl-split-b" aria-hidden="true"><i className={sp.left.side} style={{ width: `${sp.left.pct}%` }} /><i className={sp.right.side} style={{ width: `${sp.right.pct}%` }} /></div>
        </div>
      ) : st === "none" ? <p className="fl-na" style={{ marginTop: 14 }}>{NO_DII}</p> : null}
      <p className="fl-foot">Provisional end-of-day figures in ₹ crore. Net = buy − sell. Green and ▲ is buying, red and ▼ is selling.</p>
    </section>
  );
}
function StreakCard({ title, s, avail }: { title: string; s: Streak | null; avail: boolean }) {
  return (
    <div className="fl-panel fl-st">
      <h2>{title}</h2>
      {!avail ? <p className="fl-na">Not published to us.</p> : !s || s.side === "flat" || !s.days ? <div className="v">—</div> : <>
        <div className="v"><span className={s.side === "buying" ? "gain" : "loss"}>{s.side === "buying" ? "▲" : "▼"} {s.days} {s.days === 1 ? "Day" : "Days"}</span><small className={s.side === "buying" ? "gain" : "loss"}>{s.side === "buying" ? "Buying" : "Selling"}</small></div>
        <p>{s.since ? <>Since {dateIN(s.since, { day: "numeric", month: "short" })} · </> : null}<b>{inr(s.sum)}</b> in total{s.velocity != null && <> · velocity <b>{inr(s.velocity, { d: 0 })}/day</b></>}</p></>}
    </div>
  );
}

// ------------------------------------------------------------------------------------------------------------- the main chart
function Activities({ f, st, range, setRange, view, setView }: Ctx) {
  const [show, setShow] = useState<Record<string, boolean>>({ fii: true, dii: true, all: true }), [bside, setBside] = useState<SideKey>("fii");
  const rows = useMemo(() => rangeRows(f.days, range), [f.days, range]);
  const lines = useMemo(() => [
    { key: "fii", label: "FII", color: "var(--k1)", pts: cumulative(rows, "fii") },
    ...(st !== "none" ? [{ key: "dii", label: "DII", color: "var(--k3)", pts: cumulative(rows, "dii") }, { key: "all", label: "Overall", color: "var(--gold)", pts: cumulative(rows, "all") }] : []),
  ], [rows, st]);
  const side: SideKey = st === "none" ? "fii" : bside;
  const maAll = useMemo(() => movingAverage(f.days.map((d) => netOf(d, side)), 20), [f.days, side]);
  const maRows = useMemo(() => { const off = f.days.length - rows.length; return maAll.slice(off); }, [maAll, f.days.length, rows.length]);
  const tot = (s: SideKey) => { const v = rows.map((d) => netOf(d, s)).filter((x): x is number => x != null); return v.length ? v.reduce((a, b) => a + b, 0) : null; };
  const both = useMemo(() => commonSpan(rows), [rows]);                       // DII and Overall are summed over the sessions that have both, never over the whole range
  const gapDays = rows.filter((d) => d.dii?.net == null).length, from = f.coverage.diiPublishedFrom;
  const short = (d: string) => dateIN(d, { day: "numeric", month: "short", year: "2-digit" });
  return (
    <section className="fl-panel" aria-labelledby="flAct" id="chart">
      <div className="fl-ph"><h2 id="flAct">FII/DII activities {view === "cum" ? "· cumulative net flows (₹ crore)" : "· daily net flows (₹ crore)"}</h2>
        <div className="fl-seg" role="radiogroup" aria-label="Range">{RANGES.map(([k]) => <button key={k} type="button" role="radio" aria-checked={range === k} className={range === k ? "on" : ""} onClick={() => setRange(k)}>{k}</button>)}</div></div>
      <div className="fl-ctrl">
        <div className="fl-seg" role="radiogroup" aria-label="Chart type"><button type="button" role="radio" aria-checked={view === "cum"} className={view === "cum" ? "on" : ""} onClick={() => setView("cum")}>Cumulative lines</button><button type="button" role="radio" aria-checked={view === "bars"} className={view === "bars" ? "on" : ""} onClick={() => setView("bars")}>Daily net bars</button></div>
        {view === "cum"
          ? lines.map((l) => <button key={l.key} type="button" className="fl-tog" aria-pressed={show[l.key]} onClick={() => setShow({ ...show, [l.key]: !show[l.key] })}><i style={{ background: l.color }} />{l.label}</button>)
          : <div className="fl-seg" role="radiogroup" aria-label="Whose flow"><button type="button" role="radio" aria-checked={side === "fii"} className={side === "fii" ? "on" : ""} onClick={() => setBside("fii")}>FII</button><button type="button" role="radio" aria-checked={side === "dii"} disabled={st === "none"} className={side === "dii" ? "on" : ""} onClick={() => setBside("dii")}>DII</button></div>}
      </div>
      {st === "none" && <p className="fl-na" style={{ marginBottom: 12 }}>{NO_DII}</p>}
      {view === "cum"
        ? <LineChart series={lines.filter((l) => show[l.key])} label={`Cumulative net flow in rupees crore from the start of the range, ${lines.filter((l) => show[l.key]).map((l) => l.label).join(", ")}`} />
        : <BarChart rows={rows.map((d) => ({ d: d.d, v: netOf(d, side) }))} ma={maRows} maLabel="20-session average" name={side === "fii" ? "FII" : "DII"} />}
      <p className="fl-sum" aria-label="Totals for the range">
        <span>{rows.length} sessions · {rows.length ? `${dateIN(rows[0].d, { day: "numeric", month: "short", year: "2-digit" })} to ${dateIN(rows[rows.length - 1].d, { day: "numeric", month: "short", year: "2-digit" })}` : ""}</span>
        <span>FII{st !== "none" && gapDays > 0 ? " (whole range)" : ""} <b className={tone(tot("fii"))}>{inr(tot("fii"), { sign: true })}</b></span>
        {st !== "none" && !gapDays && <><span>DII <b className={tone(tot("dii"))}>{inr(tot("dii"), { sign: true })}</b></span><span>Overall <b className={tone(both?.overall)}>{inr(both?.overall, { sign: true })}</b></span></>}
        {st !== "none" && gapDays > 0 && both && <span className="fl-sum-b"><em>Where DII exists, {short(both.from)} to {short(both.to)} ({both.n} sessions):</em> FII <b className={tone(both.fii)}>{inr(both.fii, { sign: true })}</b> · DII <b className={tone(both.dii)}>{inr(both.dii, { sign: true })}</b> · Overall <b className={tone(both.overall)}>{inr(both.overall, { sign: true })}</b></span>}
        {view === "bars" && <span><i className="fl-dv" style={{ width: 18, height: 4, background: "var(--gold)", marginLeft: 0, marginRight: 6 }} />20-session average of the net</span>}
      </p>
      <p className="fl-foot">{view === "cum" ? "Each line is a running total of daily net flow from the first session in the range, so it starts at zero. A rising line means net buying over the period; a falling line, net selling. On the axis, k is thousand crore and L is lakh crore (₹1,00,000 crore)." : "Green bars are net buying days and red bars net selling days. The gold line is the average of the latest 20 sessions, which smooths daily noise."}{st === "partial" && gapDays > 0 && (() => { const un = rows.filter((d) => d.dii?.net == null && diiGap(d.d, from) === "unpublished").length, miss = gapDays - un;
          return ` DII and Overall are counted only on sessions that have both FII and DII, so those two lines start where DII starts${both ? ` (${short(both.from)})` : ""}.` + (un ? ` ${f.coverage.diiReason ?? `The official DII report begins ${from ? short(from) : "later"}; earlier days are not published.`}` : "") + (miss ? ` ${miss} session${miss === 1 ? " has" : "s have"} no DII figure although the report exists; ${miss === 1 ? "it adds" : "they add"} nothing to those lines.` : ""); })()}</p>
    </section>
  );
}

// ------------------------------------------------------------------------------------------------------------- flow vs index
function Gauge({ label, r, days }: { label: string; r: number | null; days: number }) {
  return (
    <div className="fl-card">
      <span className="k">{label}</span>
      <b className="n" style={{ color: r == null ? "var(--muted)" : r > 0 ? "var(--gain)" : "var(--loss)" }}>{r == null ? "—" : (r > 0 ? "+" : "") + r.toFixed(2).replace("-", MINUS)}</b>
      {r != null && <><div className="fl-gauge" role="img" aria-label={`Correlation ${r.toFixed(2)} on a scale from minus one to plus one`}><u /><b style={{ left: `${(Math.max(-1, Math.min(1, r)) + 1) * 50}%` }} /></div><div className="fl-gauge-k"><span>{MINUS}1</span><span>0</span><span>+1</span></div></>}
      <p>{r == null ? "Not enough overlapping sessions to say." : <><b>{corrWords(r)}</b> between this flow and the same-day index move, over {days.toLocaleString("en-IN")} sessions.</>}</p>
    </div>
  );
}
function VsIndex({ f, st, range }: Ctx) {
  const c = f.correlation, [side, setSide] = useState<SideKey>("fii"), s: SideKey = st === "none" ? "fii" : side;
  const rows = useMemo(() => rangeRows(f.days, range), [f.days, range]);
  const idx = f.index && f.index.length ? f.index : null;
  const ir = useMemo(() => (idx ? indexCorrelation(rows, idx, s) : null), [rows, idx, s]);
  if (!c && !idx) return null;
  const cum = cumulative(rows, s), cl = new Map((idx || []).map((p) => [p.d, p.close]));
  const ipts = rows.map((d) => [d.d, cl.get(d.d)] as const).filter((p): p is [string, number] => p[1] != null);
  const name = c?.label || "Index";
  return (
    <section className="fl-panel" aria-labelledby="flIdx">
      <div className="fl-ph"><h2 id="flIdx">Flow vs {name}</h2>
        {idx && <div className="fl-seg" role="radiogroup" aria-label="Whose flow"><button type="button" role="radio" aria-checked={s === "fii"} className={s === "fii" ? "on" : ""} onClick={() => setSide("fii")}>FII</button><button type="button" role="radio" aria-checked={s === "dii"} disabled={st === "none"} className={s === "dii" ? "on" : ""} onClick={() => setSide("dii")}>DII</button></div>}</div>
      <p className="fl-note">Do institutional flows and the market move together on the same day? Correlation runs from {MINUS}1 (opposite) to +1 (together). It describes the past and does not show that one causes the other.</p>
      {idx && ipts.length > 1 && <>
        <LineChart height={280} label={`${s === "fii" ? "FII" : "DII"} cumulative net flow in rupees crore against the ${name}, over the selected range`}
          series={[{ key: "f", label: `${s === "fii" ? "FII" : "DII"} cumulative flow`, color: s === "fii" ? "var(--k1)" : "var(--k3)", pts: cum }, { key: "i", label: name, color: "var(--gold)", pts: ipts, axis: "r", fmt: (v) => nf(v, 0), dashed: true }]} />
        <p className="fl-foot">Left axis: running total of the flow since the start of the range (₹ crore). Right axis (dashed): the index close. The range follows the buttons on the main chart.{ir != null && <> Over this range the daily flow and the index's daily move have had <b>{corrWords(ir)}</b> ({ir.toFixed(2).replace("-", MINUS)}).</>}</p></>}
      {c && <div className="fl-cards" style={{ marginTop: 14 }}><Gauge label="FII flow vs index" r={c.fiiVsIndex} days={c.days} />{st === "none" ? <div className="fl-card"><span className="k">DII flow vs index</span><p style={{ marginTop: 8 }}>{NO_DII}</p></div> : <Gauge label="DII flow vs index" r={c.diiVsIndex} days={c.days} />}</div>}
    </section>
  );
}

// ------------------------------------------------------------------------------------------------------------- calendars
function DayDetail({ f, day }: { f: Flows; day: string }) {
  const d = f.days.find((x) => x.d === day); if (!d) return null;
  const pf = percentileOf(f.days, "fii", d.fii.net), pd = percentileOf(f.days, "dii", d.dii?.net ?? null);
  const box = (name: string, s: Side | null, p: ReturnType<typeof percentileOf>) => (
    <div><span>{name}</span><b className={tone(s?.net)}>{s?.net == null ? "—" : <>{arrow(s.net)}{inr(s.net)}</>}</b>
      <small>{s ? `Buy ${inr(s.buy)} · Sell ${inr(s.sell)}` : name.startsWith("DII") && diiGap(d.d, f.coverage.diiPublishedFrom) === "unpublished" ? `Not published: the official DII report begins ${longDate(f.coverage.diiPublishedFrom!)}` : "No figure published"}</small>
      {p && <small>{s!.net! < 0 ? "Selling" : "Buying"} bigger than {p.pct.toFixed(0)}% of sessions</small>}</div>);
  const c = combined(d);
  return (
    <div className="fl-day" role="status" aria-live="polite"><h3>{longDate(d.d)}</h3>
      <div className="fl-day-g">{box("FII / FPI net", d.fii, pf)}{box("DII net", d.dii, pd)}<div><span>Net combined</span><b className={tone(c)}>{c == null ? "—" : <>{arrow(c)}{inr(c)}</>}</b></div></div></div>
  );
}
function Calendars({ f, st, day, setDay }: Ctx) {
  const sel = day && f.days.some((d) => d.d === day) ? day : f.days.length ? f.days[f.days.length - 1].d : null;
  const t1f = totalSince(f.days, "fii", 12), yr = sinceMonths(f.days, 12), t1d = commonSpan(yr), from = f.coverage.diiPublishedFrom;
  const yrGap = yr.filter((d) => d.dii?.net == null), un = yrGap.filter((d) => diiGap(d.d, from) === "unpublished").length, missing = yrGap.length - un;
  const short = (d: string) => dateIN(d, { day: "numeric", month: "short", year: "numeric" });
  return (
    <section className="fl-panel" aria-labelledby="flCal" id="calendar">
      <div className="fl-ph"><h2 id="flCal">Daily flow calendar · last year</h2></div>
      <p className="fl-note">One square per trading day. Deeper green is bigger net buying, deeper red bigger net selling; the scale is set by that side's own 92nd-percentile day, so a few extreme days do not wash out the rest. Select any day to read its figures.</p>
      <div className="fl-cals">
        <div><div className="fl-cal-h"><h3>FII / FPI daily net</h3><b className={tone(t1f)}>1Y FII: {inr(t1f)}</b>{st !== "none" && t1d && yrGap.length > 0 && <small className="fl-cal-sub">same {t1d.n} sessions as DII: {inr(t1d.fii, { sign: true })}</small>}</div>
          <CalendarHeat days={f.days} side="fii" selected={sel} onSelect={setDay} name="FII" /></div>
        <div><div className="fl-cal-h"><h3>DII daily net</h3>{st !== "none" && t1d && <b className={tone(t1d.dii)}>{yrGap.length > 0 ? `DII since ${short(t1d.from)}` : "1Y DII"}: {inr(t1d.dii, { sign: yrGap.length > 0 })}</b>}</div>
          {st === "none" ? <p className="fl-na">{NO_DII}</p> : <CalendarHeat days={f.days} side="dii" selected={sel} onSelect={setDay} name="DII" publishedFrom={from} />}</div>
      </div>
      <div className="fl-legend" aria-label="Colour key"><span style={{ margin: "0 6px 0 0" }}>▼ Selling</span>{CAL_LEGEND.map((l) => <i key={l} className="fl-cell" data-l={l} style={{ aspectRatio: "auto" }} />)}<span>Buying ▲</span><i className="fl-cell" data-n="1" style={{ aspectRatio: "auto" }} /><span style={{ margin: "0 0 0 6px" }}>missing session</span>{un > 0 && <><i className="fl-cell" data-n="2" style={{ aspectRatio: "auto" }} /><span style={{ margin: "0 0 0 6px" }}>not published</span></>}</div>
      {st === "partial" && un > 0 && <p className="fl-foot">DII squares with an empty outline are days before the official DII report begins{from ? ` (${short(from)})` : ""}: not published, not zero. {f.coverage.diiReason ?? ""} The DII total above covers only the {t1d ? `${t1d.n.toLocaleString("en-IN")} sessions from ${short(t1d.from)}` : "sessions that have it"}; the FII figure beside it is shown over the same sessions for a fair comparison.</p>}
      {st === "partial" && missing > 0 && <p className="fl-foot">DII is missing for {missing.toLocaleString("en-IN")} session{missing === 1 ? "" : "s"} although the report exists; those squares are hatched, not zero.</p>}
      {sel && <DayDetail f={f} day={sel} />}
    </section>
  );
}

// ------------------------------------------------------------------------------------------------------------- today in context + absorption
function Context({ f, st }: Ctx) {
  const l = f.latest; if (!l) return null;
  const mk = (name: string, s: SideKey) => {
    const v = s === "fii" ? l.fii.net : l.dii?.net ?? null, p = percentileOf(f.days, s, v);
    return (
      <div className="fl-card" key={s}>
        <span className="k">{name} · latest session</span>
        {p && v != null ? <><b className={"n " + tone(v)}>{p.pct.toFixed(0)}%</b>
          <p>The latest {name} net {v < 0 ? "selling" : "buying"} of <b>{inr(Math.abs(v))}</b> is bigger than <b>{p.pct.toFixed(0)}%</b> of all {p.n.toLocaleString("en-IN")} sessions in our data.</p>
          <div className="fl-meter" aria-hidden="true"><i style={{ width: `${p.pct}%`, background: v < 0 ? "var(--loss)" : "var(--gain)" }} /></div></>
          : <p style={{ marginTop: 8 }}>{s === "dii" && st === "none" ? NO_DII : "No figure for this session, or it was flat."}</p>}
      </div>);
  };
  return (
    <section className="fl-panel" aria-labelledby="flCtx">
      <div className="fl-ph"><h2 id="flCtx">How big was the latest session?</h2></div>
      <div className="fl-cards">{mk("FII", "fii")}{mk("DII", "dii")}</div>
      <p className="fl-foot">Share of all sessions in the data whose flow was smaller in the same direction (selling days are compared with selling size, buying days with buying size).</p>
    </section>
  );
}
function Absorb({ f, st }: Ctx) {
  return (
    <section className="fl-panel" aria-labelledby="flAbs">
      <div className="fl-ph"><h2 id="flAbs">Who is absorbing the selling?</h2></div>
      <p className="fl-note">On the days FIIs were net sellers, how much did domestic institutions buy on those same days? 100% would mean DIIs bought exactly as much as FIIs sold. This describes what happened, not why.</p>
      {st === "none" ? <p className="fl-na">{NO_DII}</p> : (
        <div className="fl-cards">{[30, 90, 365].map((n) => {
          const a = absorption(f.days, n);
          if (!a || a.ratio == null) return <div className="fl-card" key={n}><span className="k">Last {n} sessions</span><p style={{ marginTop: 8 }}>{a ? "FIIs were not net sellers on any of these days." : "Not enough sessions with both figures."}</p></div>;
          const m = Math.max(a.fiiSold, Math.abs(a.diiNetOnThoseDays)) || 1;
          return (
            <div className="fl-card" key={n}><span className="k">Last {a.sessions} sessions</span>
              <b className="n">{Math.round(a.ratio * 100)}%</b>
              <div className="fl-two-bars" aria-hidden="true">
                <div><span>FII sold</span><span className="b"><i style={{ width: `${(a.fiiSold / m) * 100}%`, background: "var(--loss)" }} /></span></div>
                <div><span>DII net</span><span className="b"><i style={{ width: `${(Math.abs(a.diiNetOnThoseDays) / m) * 100}%`, background: a.diiNetOnThoseDays >= 0 ? "var(--gain)" : "var(--loss)" }} /></span></div></div>
              <p>FIIs sold <b>{inr(a.fiiSold)}</b> on {a.sellDays} of {a.sessions} days. On those days DIIs were net {a.diiNetOnThoseDays >= 0 ? "buyers" : "sellers"} of <b>{inr(Math.abs(a.diiNetOnThoseDays))}</b>, and bought on <b>{a.diiBoughtDays}</b> of the {a.sellDays}.</p></div>);
        })}</div>)}
      {st === "partial" && <p className="fl-foot">Only sessions with both FII and DII figures are counted.</p>}
    </section>
  );
}

// ------------------------------------------------------------------------------------------------------------- streak records
function Records({ f, st }: Ctx) {
  const list = (s: SideKey, name: string) => (["buying", "selling"] as const).map((side) => {
    const r = topRuns(f.days, s, side, 5);
    return (
      <div key={s + side}><h4 className={side === "buying" ? "gain" : "loss"}>{side === "buying" ? "▲ Longest buying streaks" : "▼ Longest selling streaks"} · {name}</h4>
        {r.length ? <ol>{r.map((x, i) => (
          <li key={x.from}><span className="r">{i + 1}</span>
            <span className="d"><b>{x.days} sessions</b> · {dateIN(x.from, { day: "numeric", month: "short", year: "2-digit" })} to {dateIN(x.to, { day: "numeric", month: "short", year: "2-digit" })}{x.current && <em>ongoing</em>}{x.touchesStart && <em>began before our data</em>}</span>
            <span className={"s " + tone(x.sum)}>{inr(x.sum)}</span></li>))}</ol> : <p className="fl-na">None in the data.</p>}
      </div>);
  });
  return (
    <section className="fl-panel" aria-labelledby="flRec">
      <div className="fl-ph"><h2 id="flRec">Streak records</h2></div>
      <p className="fl-note">The longest runs of consecutive sessions in the same direction within the {f.days.length.toLocaleString("en-IN")} sessions we have ({f.coverage.from ? dateIN(f.coverage.from, { month: "short", year: "numeric" }) : ""} to {f.coverage.to ? dateIN(f.coverage.to, { month: "short", year: "numeric" }) : ""}).</p>
      <div className="fl-lb"><div style={{ display: "grid", gap: 18 }}>{list("fii", "FII")}</div>
        <div style={{ display: "grid", gap: 18 }}>{st === "none" ? <p className="fl-na">{NO_DII}</p> : list("dii", "DII")}</div></div>
    </section>
  );
}

// ------------------------------------------------------------------------------------------------------------- monthly and yearly
function Monthly({ f, st }: Ctx) {
  const [side, setSide] = useState<SideKey>("fii"), s: SideKey = st === "none" ? "fii" : side, g = useMemo(() => monthGrid(f, s), [f, s]);
  return (
    <section className="fl-panel" aria-labelledby="flMon">
      <div className="fl-ph"><h2 id="flMon">Month by month and year by year</h2>
        <div className="fl-seg" role="radiogroup" aria-label="Whose flow"><button type="button" role="radio" aria-checked={s === "fii"} className={s === "fii" ? "on" : ""} onClick={() => setSide("fii")}>FII</button><button type="button" role="radio" aria-checked={s === "dii"} disabled={st === "none"} className={s === "dii" ? "on" : ""} onClick={() => setSide("dii")}>DII</button></div></div>
      <p className="fl-note">Net flow for each calendar month in ₹ crore (k = thousand, L = lakh). Green is net buying, red is net selling; the last column is the year's total.</p>
      {st === "none" && <p className="fl-na" style={{ marginBottom: 12 }}>{NO_DII}</p>}
      <div className="fl-tw"><table className="fl-t fl-mg"><caption className="sr-only" style={{ position: "absolute", left: -9999 }}>Monthly net {s.toUpperCase()} flow in rupees crore by year</caption>
        <thead><tr><th scope="col">Year</th>{MONTHS.map((m) => <th key={m} scope="col">{m}</th>)}<th scope="col">Year</th></tr></thead>
        <tbody>{g.years.map((y) => { const t = g.total(y); return (
          <tr key={y}><th scope="row">{y}</th>
            {MONTHS.map((_, m) => { const v = g.cell(y, m); return v == null ? <td key={m} className="na" title="no figure">·</td> : <td key={m} data-l={level(v, g.maxAbs)} title={`${MONTHS[m]} ${y}: ${v > 0 ? "net buying " : v < 0 ? "net selling " : ""}${inr(v)}`}>{compactCr(v)}</td>; })}
            <td className={"tot " + tone(t)} title={`${y}: ${inr(t)}`}>{t == null ? "·" : <>{arrow(t)}{compactCr(t)}</>}</td></tr>); })}</tbody></table></div>
      <p className="fl-foot">The current year is partial. Hover or focus a cell for the exact amount.</p>
    </section>
  );
}

// ------------------------------------------------------------------------------------------------------------- compare periods
function Periods({ f, st }: Ctx) {
  const ps = f.periods, [a, setA] = useState(ps.find((p) => p.key === "month")?.key ?? ps[0]?.key), [b, setB] = useState(ps.find((p) => p.key === "fy")?.key ?? ps[1]?.key ?? ps[0]?.key);
  if (!ps.length) return null;
  const pa = ps.find((p) => p.key === a) || ps[0], pb = ps.find((p) => p.key === b) || ps[0];
  const mx = Math.max(1, ...ps.flatMap((p) => [Math.abs(perDay(p, "fii") ?? 0), Math.abs(perDay(p, "dii") ?? 0)]));
  const card = (p: Period) => (
    <div><h3>{p.label}</h3><small>{dateIN(p.from, { day: "numeric", month: "short" })} to {dateIN(p.to, { day: "numeric", month: "short", year: "numeric" })} · {p.days} sessions</small>
      <dl><div><dt>FII net</dt><dd className={tone(p.fii)}>{inr(p.fii, { sign: true })}</dd></div><div><dt>FII per session</dt><dd>{inr(perDay(p, "fii"), { sign: true })}</dd></div>
        {st !== "none" && <><div><dt>DII net</dt><dd className={tone(p.diiNet)}>{inr(p.diiNet, { sign: true })}</dd></div><div><dt>DII per session</dt><dd>{inr(perDay(p, "dii"), { sign: true })}</dd></div></>}
        {st !== "none" && p.diiNet == null && p.common && <div><dt>Where DII exists ({dateIN(p.common.from, { day: "numeric", month: "short" })} to {dateIN(p.common.to, { day: "numeric", month: "short", year: "2-digit" })}, {p.common.days} sessions)</dt><dd>FII {inr(p.common.fii, { sign: true })} · DII {inr(p.common.dii, { sign: true })} · Overall {inr(p.common.overall, { sign: true })}</dd></div>}
        <div><dt>FII gross buy / sell</dt><dd>{p.fiiBuy == null ? "—" : `${compactCr(p.fiiBuy)} / ${compactCr(p.fiiSell ?? 0)}`}</dd></div></dl></div>);
  const sel = (v: string | undefined, set: (s: string) => void, lab: string) => <label>{lab}<select value={v} onChange={(e) => set(e.target.value)}>{ps.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}</select></label>;
  return (
    <section className="fl-panel" aria-labelledby="flPer">
      <div className="fl-ph"><h2 id="flPer">Compare periods</h2></div>
      <p className="fl-note">Pick any two periods. Periods differ in length, so the per-session average is shown too. A DII total is given only when every session in the period has a DII figure; where the period starts before the DII report does, the DII figure beside it covers only the sessions from {f.coverage.diiPublishedFrom ? dateIN(f.coverage.diiPublishedFrom, { day: "numeric", month: "short", year: "numeric" }) : "its first day"}, and says so.</p>
      <div className="fl-pick">{sel(a, setA, "Period A")}{sel(b, setB, "Period B")}</div>
      <div className="fl-cmp">{card(pa)}{card(pb)}</div>
      <div className="fl-tw"><table className="fl-t"><thead><tr><th scope="col">Period</th><th scope="col" className="fl-hide-sm">Sessions</th><th scope="col">FII net</th>{st !== "none" && <th scope="col">DII net</th>}<th scope="col" className="fl-hide-sm">FII per session</th></tr></thead>
        <tbody>{ps.map((p) => (
          <tr key={p.key}><th scope="row">{p.label}</th><td className="fl-hide-sm">{p.days}</td>
            <td className={tone(p.fii)}>{arrow(p.fii)}{inr(p.fii)}</td>{st !== "none" && <td className={tone(p.diiNet)} title={p.diiNet == null && p.common ? `DII exists for ${p.common.days} of ${p.days} sessions, from ${p.common.from}; over those: FII ${inr(p.common.fii, { sign: true })}, DII ${inr(p.common.dii, { sign: true })}` : undefined}>{arrow(p.diiNet)}{inr(p.diiNet)}{p.diiNet == null && p.common ? <small className="fl-since"> {inr(p.common.dii, { sign: true })} since {dateIN(p.common.from, { day: "numeric", month: "short" })}</small> : null}</td>}
            <td className="fl-hide-sm">{inr(perDay(p, "fii"))}<i className="fl-dv" style={{ width: `${Math.max(2, (Math.abs(perDay(p, "fii") ?? 0) / mx) * 60)}px`, background: (p.fii ?? 0) >= 0 ? "var(--gain)" : "var(--loss)" }} /></td></tr>))}</tbody></table></div>
    </section>
  );
}

// ------------------------------------------------------------------------------------------------------------- derivatives + fpi
const PARTS = ["FII", "DII", "Pro", "Client"] as const;
function Derivatives({ f }: Ctx) {
  const d = f.derivatives, [p, setP] = useState<(typeof PARTS)[number]>("FII");
  const rows = d?.rows.filter((r) => r.participant === p) || [];
  return (
    <section className="fl-panel" aria-labelledby="flDer">
      <div className="fl-ph"><h2 id="flDer">Derivatives positioning (F&amp;O) · participant-wise open interest</h2>
        {d && <div className="fl-seg" role="radiogroup" aria-label="Participant">{PARTS.map((x) => <button key={x} type="button" role="radio" aria-checked={p === x} className={p === x ? "on" : ""} onClick={() => setP(x)}>{x}</button>)}</div>}</div>
      {!d ? <p className="fl-na">The exchanges' participant-wise open-interest file is not available to us right now, so there is no positioning to show.</p> : <>
        <p className="fl-note">Contracts outstanding at the close of {dateIN(d.asOf)}, split into long (bought) and short (sold). Net long means more bought than sold. This is positioning, not a view on direction.</p>
        {rows.length ? <div className="fl-oi">{rows.map((r) => {
          const l = r.long ?? null, s = r.short ?? null, t = (l ?? 0) + (s ?? 0), net = r.net ?? (l != null && s != null ? l - s : null);
          return (
            <div className="fl-oi-row" key={r.instrument}><div className="h">{r.instrument}<span className={tone(net)}>{net == null ? "—" : `${net > 0 ? "▲ Net long " : net < 0 ? "▼ Net short " : "Balanced "}${grp(net)}`}</span></div>
              {l != null && s != null && t > 0 ? <div className="fl-oi-bar" role="img" aria-label={`${r.instrument}: long ${grp(l)} contracts (${Math.round((l / t) * 100)} per cent), short ${grp(s)} contracts`}><i className="l" style={{ width: `${(l / t) * 100}%` }}>{Math.round((l / t) * 100)}%</i><i className="s" style={{ width: `${(s / t) * 100}%` }}>{Math.round((s / t) * 100)}%</i></div> : <p className="fl-na">Not published.</p>}
              <div className="fl-oi-n"><span>Long {l == null ? "—" : grp(l)}</span><span>Short {s == null ? "—" : grp(s)}</span></div></div>);
        })}</div> : <p className="fl-na">No positions published for {p}.</p>}
        <p className="fl-foot">Green is long, red is short. Counts are contracts, not ₹.</p></>}
    </section>
  );
}
function Fpi({ f }: Ctx) {
  const p = f.fpi;
  return (
    <section className="fl-panel" aria-labelledby="flFpi">
      <div className="fl-ph"><h2 id="flFpi">FPI flows across asset classes</h2>{p && <span className="fl-chip">NSDL · {dateIN(p.asOf)}</span>}</div>
      {!p ? <p className="fl-na">NSDL's all-asset FPI figures are not available to us right now.</p> : <>
        <p className="fl-note">The cash-market figures above are equity only. NSDL's reporting adds what foreign portfolio investors did in debt and hybrid instruments on the latest reporting day (₹ crore).</p>
        <div className="fl-fpi">{([["Equity", p.equityNet], ["Debt", p.debtNet], ["Hybrid", p.hybridNet], ["Total", p.totalNet]] as const).map(([k, v]) => <div key={k}><span>{k}</span><b className={tone(v)}>{v == null ? "—" : <>{arrow(v)}{inr(v)}</>}</b><small>{v == null ? "not published" : v > 0 ? "net inflow" : v < 0 ? "net outflow" : "flat"}</small></div>)}
          {p.usdMillion != null && <div><span>Total in US$</span><b className={tone(p.usdMillion)}>{p.usdMillion < 0 ? MINUS : ""}${grp(p.usdMillion)} mn</b><small>{p.inr != null ? `at ₹${nf(p.inr, 2)} per US$` : ""}</small></div>}</div></>}
    </section>
  );
}

// ------------------------------------------------------------------------------------------------------------- day table
const download = (name: string, text: string) => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], { type: "text/csv" })); a.download = name; a.click(); URL.revokeObjectURL(a.href); };
function DayTable({ f, st }: Ctx) {
  const { toast } = useUI(), [q, setQ] = useState(""), [key, setKey] = useState<SortKey>("d"), [asc, setAsc] = useState(false), [n, setN] = useState(20);
  const rows = useMemo(() => sortDays(filterDays(f.days, q), key, asc), [f.days, q, key, asc]);
  const th = (k: SortKey, label: string, cls = "") => (
    <th scope="col" className={cls} aria-sort={key === k ? (asc ? "ascending" : "descending") : "none"}><button type="button" className="fl-sort" onClick={() => { if (key === k) setAsc(!asc); else { setKey(k); setAsc(k === "d" ? false : true); } setN(20); }}>{label}{key === k ? (asc ? " ▲" : " ▼") : ""}</button></th>);
  const neg = (v: number | null | undefined) => (v != null && v < 0 ? MINUS : "");
  const csv = () => { download(`finlit-fii-dii-${f.days[0]?.d ?? "all"}-to-${f.days[f.days.length - 1]?.d ?? ""}.csv`, toCsv(f.days)); toast(`Downloaded all ${f.days.length.toLocaleString("en-IN")} sessions.`); };
  return (
    <section className="fl-panel" aria-labelledby="flTab" id="table">
      <div className="fl-ph"><h2 id="flTab">Day-by-day data</h2><button type="button" className="btn" onClick={csv}>Download everything (CSV)</button></div>
      <div className="fl-ctrl"><label className="sr-only" htmlFor="flQ" style={{ position: "absolute", left: -9999 }}>Search sessions</label>
        <input id="flQ" className="fl-search" type="search" placeholder="Search a date: 2026-10, oct 2025, friday…" value={q} onChange={(e) => { setQ(e.target.value); setN(20); }} />
        <span className="fl-foot" style={{ margin: 0 }} aria-live="polite">{rows.length.toLocaleString("en-IN")} of {f.days.length.toLocaleString("en-IN")} sessions · ₹ crore</span></div>
      <div className="fl-tw"><table className="fl-t"><thead><tr>{th("d", "Date")}<th scope="col" className="fl-hide-sm">FII buy</th><th scope="col" className="fl-hide-sm">FII sell</th>{th("fii", "FII net")}{st !== "none" && <><th scope="col" className="fl-hide-sm">DII buy</th><th scope="col" className="fl-hide-sm">DII sell</th>{th("dii", "DII net")}{th("all", "Combined")}</>}</tr></thead>
        <tbody>{rows.slice(0, n).map((d: FlowDay) => { const c = combined(d); return (
          <tr key={d.d}><th scope="row">{dateIN(d.d, { weekday: "short", day: "numeric", month: "short", year: "numeric" })}</th>
            <td className="fl-hide-sm">{d.fii.buy == null ? "—" : grp(d.fii.buy)}</td><td className="fl-hide-sm">{d.fii.sell == null ? "—" : grp(d.fii.sell)}</td>
            <td className={tone(d.fii.net)}>{d.fii.net == null ? "—" : <>{arrow(d.fii.net)}{neg(d.fii.net)}{grp(d.fii.net)}</>}</td>
            {st !== "none" && <><td className="fl-hide-sm">{d.dii?.buy == null ? "—" : grp(d.dii.buy)}</td><td className="fl-hide-sm">{d.dii?.sell == null ? "—" : grp(d.dii.sell)}</td>
              <td className={tone(d.dii?.net)}>{d.dii?.net == null ? "—" : <>{arrow(d.dii.net)}{neg(d.dii.net)}{grp(d.dii.net)}</>}</td><td className={tone(c)}>{c == null ? "—" : <>{arrow(c)}{neg(c)}{grp(c)}</>}</td></>}</tr>); })}</tbody></table></div>
      {rows.length === 0 && <p className="fl-empty">No session matches "{q}".</p>}
      {rows.length > n && <div className="fl-more"><button type="button" className="btn" onClick={() => setN(n + 40)}>Show 40 more</button><button type="button" className="btn" onClick={() => setN(rows.length)}>Show all {rows.length.toLocaleString("en-IN")}</button></div>}
      <p className="fl-foot">Click a column heading to sort. The CSV holds the whole history, not just the rows matching your search; a blank means the figure was not published.</p>
    </section>
  );
}

// ------------------------------------------------------------------------------------------------------------- sources and method
const STATUS = { ok: "Up to date", stale: "Behind", unavailable: "Unavailable" } as const;
function Sources({ f, st }: Ctx) {
  const c = f.coverage;
  return (
    <section className="fl-panel fl-src" aria-labelledby="flSrc" id="sources">
      <div className="fl-ph"><h2 id="flSrc">Sources and method</h2>{f.updatedAt && <span className="fl-chip">Refreshed {dateIN(f.updatedAt)}</span>}</div>
      <p className="fl-note">{c.sessions.toLocaleString("en-IN")} sessions{c.from && c.to ? ` from ${dateIN(c.from)} to ${dateIN(c.to)}` : ""}. {st === "full" ? "DII figures are present for every session." : st === "partial" ? `DII figures exist for ${c.diiSessions.toLocaleString("en-IN")} of them${c.diiFrom ? `, from ${dateIN(c.diiFrom)}` : ""}. ${c.diiReason ?? "The rest are shown as gaps, never as zero."}` : "No DII figures could be obtained from the sources we are allowed to use, so every DII view says so instead of showing a number."}</p>
      <ul>{f.sources.map((s) => (
        <li key={s.id}><a href={s.url} target="_blank" rel="noopener noreferrer">{s.label}</a><span><b className={`fl-badge ${s.status}`}>{STATUS[s.status]}</b>{s.lastDate ? ` · latest ${dateIN(s.lastDate)}` : ""}</span><span>{s.covers}{s.note ? ` ${s.note}` : ""}</span></li>))}</ul>
      <ol className="fl-method">
        <li><b>Net</b> is buy minus sell as published, in ₹ crore, for the cash market. Figures are provisional, end-of-day and can be revised.</li>
        <li><b>FII/FPI</b> are foreign portfolio investors; <b>DII</b> are domestic institutions (mutual funds, insurers, banks and similar).</li>
        <li><b>Cumulative lines</b> add up daily nets from the first session in the range. <b>The 20-session average</b> is the mean of the latest 20 nets.</li>
        <li><b>Calendar colours</b> scale to each side's 92nd-percentile day. <b>Percentiles</b> compare a day with every session in our data.</li>
        <li><b>Absorption</b> = DII net on the days FIIs sold ÷ the FII selling on those days. <b>Streaks</b> are consecutive sessions of the same sign; a flat or missing session ends one.</li>
        <li><b>Correlation</b> is the Pearson coefficient between daily flow and the index's same-day percentage move. It shows association, not cause.</li>
        <li>A missing figure is a dash. We never estimate, interpolate or forecast.</li>
      </ol>
      <p className="fl-foot">{f.disclaimer}{/advice/i.test(f.disclaimer) ? "" : " Information only, not investment advice."} <Link to="/macro">India macro insights</Link> · <Link to="/screener">Screen companies</Link></p>
    </section>
  );
}

// ------------------------------------------------------------------------------------------------------------- page
export function FiiDiiPage() {
  useDocTitle("FII DII data today", "FII and DII data today: net buying and selling by foreign and domestic institutions in the Indian cash market, streaks, 5-year history, calendar heat maps, F&O positioning and FPI flows, with a free CSV download.");
  const q = useFlows(), { toast } = useUI(), [sp, setSp] = useSearchParams();
  const f = q.data;
  const range: RangeKey = isRange(sp.get("range")) ? (sp.get("range") as RangeKey) : "1Y", view: "cum" | "bars" = sp.get("view") === "bars" ? "bars" : "cum", day = sp.get("day");
  const put = (patch: Record<string, string | null>) => setSp((prev) => { const n = new URLSearchParams(prev); for (const [k, v] of Object.entries(patch)) { if (v == null) n.delete(k); else n.set(k, v); } return n; }, { replace: true, preventScrollReset: true });
  const share = async () => {
    const url = window.location.href;
    try { if (navigator.share) { await navigator.share({ title: "FII DII data today · FinLit", url }); return; } } catch { /* cancelled: fall back to copying */ }
    try { await navigator.clipboard.writeText(url); toast("Link copied. It reopens this range and chart type."); } catch { toast("Copy the address from your browser's address bar."); }
  };
  const st = f ? diiState(f) : "full";
  const ctx: Ctx | null = f ? { f, st, range, setRange: (r) => put({ range: r === "1Y" ? null : r }), view, setView: (v) => put({ view: v === "cum" ? null : v }), day, setDay: (d) => put({ day: d }) } : null;
  const mood = f?.latest?.mood ?? null, out = mood?.includes("outflow"), inn = mood?.includes("inflow");
  const summary = useMemo(() => (f ? summarize(f) : []), [f]);
  return (
    <div className="fl-page">
      <section className="fl-hero"><div className="wrap">
        <div className="eyebrow">Free · institutional flows · cash market in ₹ crore</div>
        <h1>FII DII Data Today</h1>
        <p>How much foreign institutions (FII/FPI) and domestic institutions (DII) bought and sold in the Indian stock market on the latest trading day, how long each has been buying or selling, and the history behind it. Net flow is simply what they bought minus what they sold.</p>
        <div className="fl-chips">
          {mood && <span className={"fl-chip " + (out ? "out" : inn ? "in" : "")}>{out ? "▼" : inn ? "▲" : "●"} {mood}</span>}
          {f?.latest && <span className="fl-chip">Last updated {ageLabel(f.latest.d, f.today)} · {dateIN(f.latest.d)}</span>}
          {f && st === "none" && <span className="fl-chip">FII only: DII not available</span>}
          <button type="button" className="fl-chip" onClick={share} aria-label="Share or copy the link to this page, with the current range and chart type">Share ↗</button>
        </div>
      </div></section>
      <div className="wrap fl-wrap">
        {q.isLoading && <div className="fl-skel" aria-busy="true"><i /><i /></div>}
        {q.isError && <div className="fl-panel" role="alert"><h2>The flows data is not available yet</h2><p className="fl-note">It loads each trading evening from the exchanges' published files. {(q.error as { status?: number })?.status === 503 ? "The first load has not finished; please check back soon." : "Please try again in a moment."}</p><button type="button" className="btn" onClick={() => q.refetch()}>Try again</button></div>}
        {f && ctx && <>
          <div className="fl-top"><Latest f={f} st={st} />
            <div className="fl-side"><StreakCard title="FII streak" s={f.streaks.fii} avail /><StreakCard title="DII streak" s={f.streaks.dii} avail={st !== "none"} />
              <div className="fl-panel fl-st"><h2>Last {f.last30.days} sessions · net flows</h2>
                <div className="fl-30"><div><span>FII</span><b className={tone(f.last30.fii)}>{f.last30.fii == null ? "—" : <>{arrow(f.last30.fii)}{inr(f.last30.fii)}</>}</b></div><div><span>DII</span>{f.last30.dii == null ? <b>—</b> : <b className={tone(f.last30.dii)}>{arrow(f.last30.dii)}{inr(f.last30.dii)}</b>}</div></div></div></div></div>
          {summary.length > 0 && <section className="fl-panel fl-say" aria-labelledby="flSay"><div className="fl-ph"><h2 id="flSay">What the numbers say</h2><span className="fl-chip">Automatic reading · describes the past only</span></div><ul>{summary.map((s) => <li key={s}>{s}</li>)}</ul></section>}
          <Activities {...ctx} />
          <Calendars {...ctx} />
          <Context {...ctx} />
          <Absorb {...ctx} />
          <VsIndex {...ctx} />
          <Records {...ctx} />
          <Monthly {...ctx} />
          <Periods {...ctx} />
          <Derivatives {...ctx} />
          <Fpi {...ctx} />
          <DayTable {...ctx} />
          <Sources {...ctx} />
        </>}
      </div>
    </div>
  );
}
