// Profit and revenue outlook (Gold): estimates of revenue and net profit for the next 1, 3 or 5 financial years from the company's own history and its
// sector's, by a weighted growth rate (the team's methodology, docs/outlook/METHOD.md). "Use our model" or "Set your own" weights. All arithmetic is on the
// server; what stays here is the weight balancing (lib/outlook.ts) and the chart series (lib/outlookChart.ts), both tested. Information only, not advice.
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { useAuth } from "../lib/auth";
import { DEMO } from "../lib/demo";
import { Icon } from "../lib/icons";
import { useUI } from "../lib/ui";
import { useDocTitle } from "../lib/title";
import { nf } from "../lib/format";
import { DEFAULT_WEIGHTS, HORIZONS, KIND_LABEL, PARAM_LABELS, isDefault, rebalance, signedPct, totalOf, useOutlook, type Horizon, type Kind, type Outlook, type Weights } from "../lib/outlook";
import { fmtCr } from "../lib/outlookChart";
import { OutlookChart, buildSeries } from "../charts/OutlookChart";
import { Gate } from "../components/Gate";
import { useIndexFilter } from "../components/SearchFilters";
import "../styles/outlook.css";

const TABS: { kind: Kind; label: string }[] = [{ kind: "profit", label: "Profit" }, { kind: "revenue", label: "Revenue" }];
const NOTE = "Estimates from the company's own history and its sector, not a prediction or advice. The weights are starting values and have not yet been validated.";
const GATE_POINTS = ["Revenue and net profit estimates for the next 1, 3 or 5 years, drawn after the reported years", "Every input, its weight and its contribution shown, with the reason for any blank", "Use our model's weights, or set the weight of each input yourself"];

// ---------------------------------------------------------------------------------------------------------- /outlook (search)
export function OutlookIndexPage() {
  useDocTitle("Profit and revenue outlook", "Revenue and net profit estimates for a listed company over the next 1, 3 or 5 years, from its own reported history and its sector's.");
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const sf = useIndexFilter(true);
  const hits = useMemo(() => {
    const t = q.trim().toUpperCase();
    if (!t || !sf.idx.data) return [];
    const starts = sf.rows.filter((r) => r[0].startsWith(t) || r[1].toUpperCase().startsWith(t));
    return [...starts, ...sf.rows.filter((r) => !starts.includes(r) && r[1].toUpperCase().includes(t))].slice(0, 8);
  }, [q, sf.idx.data, sf.rows]);
  return (
    <>
      <section className="pagehead"><div className="wrap"><div className="eyebrow">Gold tool</div><h1>Profit and revenue outlook</h1>
        <p>Pick a listed company to see its reported revenue and net profit by year, and an estimate for the next 1, 3 or 5 years worked out from its own growth and its sector's. Estimates from past results, not a prediction or advice.</p></div></section>
      <div className="wrap ol">
        <section className="card ol-find" aria-labelledby="ol-find-h">
          <h2 id="ol-find-h">Choose a company</h2>
          <label className="ol-search"><Icon name="search" /><span className="sr-only">Search a company</span>
            <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Company name or NSE symbol" autoComplete="off" spellCheck={false} maxLength={60}
              onKeyDown={(e) => { if (e.key === "Enter" && hits[0]) { e.preventDefault(); nav(`/outlook/${encodeURIComponent(hits[0][0])}`); } }} /></label>
          {hits.length > 0 && <ul className="ol-hits" aria-label="Matching companies">{hits.map((h) => <li key={h[0]}><Link to={`/outlook/${encodeURIComponent(h[0])}`}><b>{h[1]}</b><span className="mono faint">{h[0]}</span></Link></li>)}</ul>}
          {q.trim() && sf.idx.data && hits.length === 0 && <p className="faint">No listed company matches “{q.trim()}”.</p>}
          <p className="ol-disc faint">Estimates from past results, not a prediction or advice.</p>
        </section>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------------------------------------- pieces
const wkey = (kind: Kind, h: Horizon) => `${kind}:${h}`;

function Sliders({ kind, names, weights, onChange, onReset, horizon }: { kind: Kind; names: Record<string, string>; weights: Weights; onChange: (l: string, v: number) => void; onReset: () => void; horizon: Horizon }) {
  const total = totalOf(weights);
  return (
    <fieldset className="ol-sliders"><legend className="sr-only">Weight of each input, in percent</legend>
      {Object.keys(weights).map((l) => (
        <div className="ol-sl" key={l}>
          <label htmlFor={`ol-${kind}-${l}`}>{names[l] ?? PARAM_LABELS[kind][l] ?? l}</label>
          <input id={`ol-${kind}-${l}`} type="range" min={0} max={100} step={0.5} value={weights[l]} onChange={(e) => onChange(l, Number(e.target.value))} aria-valuetext={`${weights[l]} percent`} />
          <output htmlFor={`ol-${kind}-${l}`} className="mono">{nf(weights[l], 1)}%</output>
        </div>))}
      <div className="ol-total" aria-live="polite"><span>Total <b className="mono">{nf(total, 1)}%</b> <span className="faint">· the other weights move with the one you change, so the total stays 100%</span></span>
        <button type="button" className="btn ghost" onClick={onReset} disabled={isDefault(kind, horizon, weights)}>Reset to our model</button></div>
    </fieldset>
  );
}

function Skeleton() {
  return <div className="ol-skel" aria-busy="true" aria-label="Loading the estimate"><div className="sk-lines"><i /><i /><i /><i /><i /></div></div>;
}

/** One metric's chart. Its estimate is the user's own weights when they differ from the model's, else the model's; the model's is then drawn as a second dashed line. */
function ChartCard({ sym, kind, horizon, own, gold }: { sym: string; kind: Kind; horizon: Horizon; own: Weights | null; gold: boolean }) {
  const mine = useOutlook(sym, kind, horizon, own, gold);
  const model = useOutlook(sym, kind, horizon, null, gold && !!own);
  const last = useRef<Outlook | null>(null);
  if (mine.data) last.current = mine.data;
  const d = mine.data ?? (mine.isFetching ? last.current : null);
  const alt = own && model.data?.forecast.available ? model.data.forecast.years : null;
  const series = useMemo(() => (d ? buildSeries(d.history.points, d.forecast.available ? d.forecast.years : null, alt) : null), [d, alt]);
  const who = own ? "Your weights" : "FinLit model";
  return (
    <section className={"card ol-chartcard" + (mine.isFetching ? " is-busy" : "")} aria-labelledby={`ol-ch-${kind}`} aria-busy={mine.isFetching}>
      <h2 id={`ol-ch-${kind}`}>{KIND_LABEL[kind]}: reported and estimate</h2>
      {mine.isLoading && !d ? <Skeleton /> : mine.error && !d ? <p className="formerr" role="alert">{(mine.error.body?.detail as string) || "Could not load this chart."}</p> : d && series ? (
        <>
          <OutlookChart kind={kind} symbol={sym} series={series} who={who} horizonLabel={d.horizon.label.toLowerCase()} />
          {!d.forecast.available && <p className="ol-empty" role="note"><b>No estimate drawn.</b> {d.forecast.reason}</p>}
          {d.forecast.available && <p className="faint ol-chart-note">Estimate from {who === "Your weights" ? "your weights" : "the FinLit model"} · {d.horizon.label.toLowerCase()} ({d.horizon.span}){d.adjustedYears.length ? ` · reported years ${d.adjustedYears.join(", ")} adjusted for one-off items` : ""}</p>}
        </>) : null}
    </section>
  );
}

export function BuildTable({ d }: { d: Outlook }) {
  const k = d.kind;
  return (
    <section className="card" aria-labelledby={`ol-build-${k}`}>
      <h2 id={`ol-build-${k}`}>How this {KIND_LABEL[k].toLowerCase()} estimate is built <span className="tier gold">{d.mode === "custom" ? "Your weights" : "FinLit model"}</span></h2>
      <p className="muted">Each input is a yearly growth rate. The weighted growth rate is the sum of weight × value, using the {d.horizon.label.toLowerCase()} column of weights ({d.horizon.span}). Inputs that cannot be worked out drop out and their weight is shared across the others in proportion.</p>
      <div className="ol-ctable ol-build"><table>
        <caption className="sr-only">Inputs, weights and contributions to the weighted {KIND_LABEL[k].toLowerCase()} growth rate</caption>
        <thead><tr><th scope="col">Input</th><th scope="col" className="num">Value</th><th scope="col" className="num">Weight</th><th scope="col" className="num">Weight used</th><th scope="col" className="num">Adds</th></tr></thead>
        <tbody>
          {d.rate.rows.map((r) => (
            <tr key={r.key} className={r.status === "unavailable" ? "is-na" : ""}>
              <th scope="row">{r.label}<small className="faint">{r.status === "ok" ? r.method + (r.detail && !r.method?.includes("peers") ? ` · ${r.detail}` : "") : r.reason}</small></th>
              <td className="num mono">{r.valuePct == null ? "—" : signedPct(r.valuePct, 2)}{r.capped && r.rawPct != null && <small className="faint">limited from {signedPct(r.rawPct, 1)}</small>}</td>
              <td className="num mono">{nf(r.weightPct, 1)}%</td>
              <td className="num mono">{r.status === "ok" ? `${nf(r.effectiveWeightPct, 1)}%` : "—"}</td>
              <td className="num mono">{r.contributionPts == null ? "—" : signedPct(r.contributionPts, 2)}</td>
            </tr>))}
        </tbody>
        <tfoot><tr><th scope="row">Weighted growth rate, per year</th><td /><td className="num mono">{nf(d.rate.rows.reduce((s, r) => s + r.weightPct, 0), 1)}%</td><td className="num mono">{d.rate.ratePct == null ? "" : "100.0%"}</td><td className="num mono"><b>{d.rate.ratePct == null ? "—" : signedPct(d.rate.ratePct, 2)}</b></td></tr></tfoot>
      </table></div>
      {d.rate.unavailable.length > 0 && <p className="ol-note" role="note"><Icon name="info" />Not available for this company: {d.rate.unavailable.join("; ")}. Their weight was shared across the other inputs in proportion.</p>}
      <p className="faint">Each input is limited to {signedPct(d.inputCapPct, 0).replace("+", "−")} to {signedPct(d.inputCapPct, 0)} a year before it is weighted, and the table says when that applied. Sector figures are the median of the company's industry (or, with fewer than {d.minPeers} peers, its sector). {d.kind === "profit" ? "Net profit is adjusted for one-off items where the report shows them, and the margin trend is the relative change in the net profit margin, not a change in percentage points. " : ""}Banks and lenders use total income as revenue.</p>
    </section>
  );
}

export function YearTable({ d }: { d: Outlook }) {
  const k = d.kind, f = d.forecast;
  return (
    <section className="card" aria-labelledby={`ol-years-${k}`}>
      <h2 id={`ol-years-${k}`}>Year by year, {KIND_LABEL[k].toLowerCase()} <span className="tier gold">Estimate</span></h2>
      {!f.available ? <p className="ol-empty"><b>No estimate.</b> {f.reason}</p> : (
        <>
          <div className="ol-ctable"><table>
            <caption className="sr-only">Reported and estimated {KIND_LABEL[k].toLowerCase()} by financial year, in rupees crore</caption>
            <thead><tr><th scope="col">Year</th><th scope="col">Type</th><th scope="col" className="num">₹ crore</th><th scope="col" className="num">Growth applied</th><th scope="col" className="num">Change</th></tr></thead>
            <tbody>
              <tr><th scope="row">{f.base?.period}</th><td>Reported</td><td className="num mono">{nf(f.base?.valueCr ?? 0, 0)}</td><td className="num">—</td><td className="num">—</td></tr>
              {f.years.map((y) => <tr key={y.period}><th scope="row">{y.period}</th><td>Estimate</td><td className="num mono">{nf(y.valueCr, 0)}</td><td className="num mono">{signedPct(y.growthPct, 2)}</td><td className="num mono">{y.changeCr < 0 ? "−" : "+"}{nf(Math.abs(y.changeCr), 0)}</td></tr>)}
            </tbody>
          </table></div>
          <p className="faint">{f.rule} For example, {fmtCr(f.base?.valueCr)} at {signedPct(d.rate.ratePct ?? 0, 2)} a year gives {fmtCr(f.years[0]?.valueCr)} for {f.years[0]?.period}.</p>
        </>)}
    </section>
  );
}

// ---------------------------------------------------------------------------------------------------------- /outlook/:symbol
export function OutlookPage() {
  const { symbol = "" } = useParams();
  const sym = symbol.toUpperCase();
  useDocTitle(`${sym} profit and revenue outlook`, "Revenue and net profit estimates for the next 1, 3 or 5 years, from the company's own reported history and its sector's. Not a prediction, not advice.");
  const { has } = useUI();
  const { user } = useAuth();
  const gold = has("gold") && !!user && !DEMO;
  const [kind, setKind] = useState<Kind>("profit");
  const [horizon, setHorizon] = useState<Horizon>("short");
  const [mode, setMode] = useState<"model" | "custom">("model");
  const [custom, setCustom] = useState<Record<string, Weights>>({});
  const getW = (k: Kind, h: Horizon): Weights => custom[wkey(k, h)] ?? DEFAULT_WEIGHTS[k][h];
  const [sent, setSent] = useState<Record<string, Weights>>({});   // the weights last settled on: the server is asked after the sliders stop moving
  useEffect(() => { const h = window.setTimeout(() => setSent(custom), 400); return () => window.clearTimeout(h); }, [custom]);
  const own = (k: Kind): Weights | null => { const w = sent[wkey(k, horizon)] ?? DEFAULT_WEIGHTS[k][horizon]; return mode === "custom" && !isDefault(k, horizon, w) ? w : null; };
  const q = useOutlook(sym, kind, horizon, own(kind), gold);
  const last = useRef<Outlook | null>(null);
  if (q.data) last.current = q.data;
  const d = q.data ?? (q.isFetching ? last.current : null);
  const names = useMemo(() => Object.fromEntries((q.data?.rate.rows ?? []).map((r) => [r.key, r.label])), [q.data]);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const onTabKey = (e: React.KeyboardEvent, i: number) => {
    const n = e.key === "ArrowRight" || e.key === "ArrowLeft" ? (i + 1) % 2 : -1;
    if (n >= 0) { e.preventDefault(); setKind(TABS[n].kind); tabRefs.current[n]?.focus(); }
  };
  const err = q.error;
  const hz = HORIZONS.find((h) => h.key === horizon)!;

  return (
    <>
      <section className="pagehead"><div className="wrap"><div className="eyebrow">Gold tool</div><h1>Profit and revenue outlook</h1>
        <p>{d?.name ? <><b>{d.name}</b> <span className="mono faint">{sym}</span> · </> : <><span className="mono">{sym}</span> · </>}Estimates from the company's own history and its sector. <Link to={`/stocks/${encodeURIComponent(sym)}`}>Open its report</Link> · <Link to="/outlook">Another company</Link></p></div></section>
      <div className="wrap ol">
        <Gate tier="gold" title="Profit and revenue outlook" points={GATE_POINTS}>
          <div className="ol-ctl card">
            <div className="ol-ctl-row">
              <span className="ol-ctl-l" id="ol-hz-l">Estimate for</span>
              <div className="ol-mode" role="radiogroup" aria-labelledby="ol-hz-l">
                {HORIZONS.map((h) => <button key={h.key} type="button" role="radio" aria-checked={horizon === h.key} className={horizon === h.key ? "on" : ""} onClick={() => setHorizon(h.key)}>{h.label}<small>{h.span}</small></button>)}
              </div>
            </div>
            <div className="ol-ctl-row">
              <span className="ol-ctl-l" id="ol-md-l">Weights</span>
              <div className="ol-mode" role="radiogroup" aria-labelledby="ol-md-l">
                {([["model", "Our model"], ["custom", "Set your own"]] as const).map(([m, label]) => (
                  <button key={m} type="button" role="radio" aria-checked={mode === m} className={mode === m ? "on" : ""} onClick={() => setMode(m)}>{label}</button>))}
              </div>
            </div>
            <p className="ol-disc">{NOTE}</p>
            <details className="ol-how"><summary>How these estimates are made</summary>
              <p>Each year's figure is the year before, grown by one weighted yearly growth rate: next year = this year × (1 + rate). The rate adds up the company's own growth (last year, and compound growth over 3 and 5 years), the median growth of its sector, and, for profit, the change in its net profit margin. {hz.label} puts the most weight on {horizon === "short" ? "the latest year" : horizon === "mid" ? "the 3-year growth" : "the 5-year growth"}. The same rate is held for every estimate year, because no year-specific inputs are stored. Profit is estimated from its own growth, not as revenue times margin.</p>
              <p>The weights are the team's starting values and have not yet been validated against later results. Reported figures come from the company's own results.</p></details>
          </div>

          {!gold ? null : (
            <div className="ol-charts">
              <ChartCard sym={sym} kind="revenue" horizon={horizon} own={own("revenue")} gold={gold} />
              <ChartCard sym={sym} kind="profit" horizon={horizon} own={own("profit")} gold={gold} />
            </div>)}

          <div className="ol-tabs" role="tablist" aria-label="Details of the estimate">
            {TABS.map((t, i) => (
              <button key={t.kind} ref={(el) => { tabRefs.current[i] = el; }} role="tab" id={`ol-tab-${t.kind}`} aria-selected={kind === t.kind} aria-controls="ol-panel" tabIndex={kind === t.kind ? 0 : -1}
                className={kind === t.kind ? "on" : ""} onClick={() => setKind(t.kind)} onKeyDown={(e) => onTabKey(e, i)}>{t.label} estimate</button>))}
          </div>
          <div id="ol-panel" role="tabpanel" aria-labelledby={`ol-tab-${kind}`} className="ol-panel">
            {mode === "custom" && <Sliders kind={kind} horizon={horizon} names={names} weights={getW(kind, horizon)} onChange={(l, v) => setCustom((c) => ({ ...c, [wkey(kind, horizon)]: rebalance(c[wkey(kind, horizon)] ?? DEFAULT_WEIGHTS[kind][horizon], l, v) }))}
              onReset={() => setCustom((c) => ({ ...c, [wkey(kind, horizon)]: { ...DEFAULT_WEIGHTS[kind][horizon] } }))} />}
            {!gold ? null : q.isLoading && !d ? <Skeleton /> : err && !d ? (
              <p className="formerr" role="alert">{err.status === 404 ? "This company's report is not stored yet. Open its page once, then come back." : (err.body?.detail as string) || "Could not load the estimate."}</p>
            ) : d ? (
              <div className={"ol-out" + (q.isFetching ? " is-busy" : "")} aria-busy={q.isFetching}>
                <BuildTable d={d} />
                <YearTable d={d} />
                <p className="faint">Latest reported year {d.asOf.yearly ?? "—"} · {d.statement} statements · {d.mode === "custom" ? "your weights" : "FinLit model"}.</p>
                {d.isLender && <p className="ol-note" role="note"><Icon name="info" />This is a bank or lender: total income is used as its revenue.</p>}
                <p className="ol-disc">{d.disclaimer} Information only, not investment advice.</p>
              </div>
            ) : null}
          </div>
        </Gate>
      </div>
    </>
  );
}
