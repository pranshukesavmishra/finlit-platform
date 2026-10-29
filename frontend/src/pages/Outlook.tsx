// Profit and revenue outlook (Gold): an outlook score per tab with a score per group, and an indicative growth range for the next four quarters,
// from the company's own reported history. "Use our model" or "Set your own" group percentages. All arithmetic is on the server; the logic that
// stays here is the weight balancing (lib/outlook.ts, tested). Information only, not investment advice.
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { useAuth } from "../lib/auth";
import { DEMO } from "../lib/demo";
import { Icon } from "../lib/icons";
import { useUI } from "../lib/ui";
import { useDocTitle } from "../lib/title";
import { nf } from "../lib/format";
import { bandInk, bandVar } from "../lib/scoreBands";
import { DEFAULT_WEIGHTS, isDefault, outlookBand, rangePos, rebalance, signedPct, totalOf, useOutlook, type Kind, type Outlook, type OutlookGroup, type Weights } from "../lib/outlook";
import { Gate } from "../components/Gate";
import { useIndexFilter } from "../components/SearchFilters";
import "../styles/outlook.css";

const TABS: { kind: Kind; label: string }[] = [{ kind: "profit", label: "Profit" }, { kind: "revenue", label: "Revenue" }];
const GATE_POINTS = ["An outlook score for profit and for revenue, with a score for each area", "An indicative growth range for the next four quarters, from the company's own history", "Use our model, or set the weight of each area yourself"];
const crs = (v: number) => `₹${nf(v, 0)} Cr`;

// ---------------------------------------------------------------------------------------------------------- /outlook (search)
export function OutlookIndexPage() {
  useDocTitle("Profit and revenue outlook", "An outlook score and an indicative growth range for a listed company's profit and revenue, from its own reported history.");
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
        <p>Pick a listed company to see how its reported history points for profit and for revenue, and an indicative range for the next four quarters. A scenario from the company's own numbers, not a forecast.</p></div></section>
      <div className="wrap ol">
        <section className="card ol-find" aria-labelledby="ol-find-h">
          <h2 id="ol-find-h">Choose a company</h2>
          <label className="ol-search"><Icon name="search" /><span className="sr-only">Search a company</span>
            <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Company name or NSE symbol" autoComplete="off" spellCheck={false} maxLength={60}
              onKeyDown={(e) => { if (e.key === "Enter" && hits[0]) { e.preventDefault(); nav(`/outlook/${encodeURIComponent(hits[0][0])}`); } }} /></label>
          {hits.length > 0 && <ul className="ol-hits" aria-label="Matching companies">{hits.map((h) => <li key={h[0]}><Link to={`/outlook/${encodeURIComponent(h[0])}`}><b>{h[1]}</b><span className="mono faint">{h[0]}</span></Link></li>)}</ul>}
          {q.trim() && sf.idx.data && hits.length === 0 && <p className="faint">No listed company matches “{q.trim()}”.</p>}
          <p className="ol-disc faint">Scenario from the company's reported history. Not a forecast, not advice.</p>
        </section>
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------------------------------------- pieces
function Ring({ value }: { value: number | null }) {
  const b = outlookBand(value), r = 52, c = 2 * Math.PI * r;
  return (
    <svg className="ol-ring" viewBox="0 0 120 120" role="img" aria-label={value == null ? "No outlook score" : `Outlook score ${Math.round(value)} out of 100`}>
      <circle cx="60" cy="60" r={r} fill="none" stroke="var(--s3)" strokeWidth="10" />
      {value != null && <circle cx="60" cy="60" r={r} fill="none" stroke={bandVar(b)} strokeWidth="10" strokeLinecap="round" strokeDasharray={`${(value / 100) * c} ${c}`} transform="rotate(-90 60 60)" />}
      <text x="60" y="66" textAnchor="middle" className="ol-ring-n" fill={value == null ? "var(--faint)" : bandInk(b)}>{value == null ? "—" : Math.round(value)}</text>
    </svg>
  );
}

function RangeGraphic({ r }: { r: Extract<Outlook["range"], { available: true }> }) {
  const MIN = -40, MAX = 60, zero = rangePos(0, MIN, MAX);
  const lo = rangePos(r.low, MIN, MAX), mid = rangePos(r.mid, MIN, MAX), hi = rangePos(r.high, MIN, MAX);
  return (
    <div className="ol-range">
      <div className="ol-track" role="img" aria-label={`Indicative range ${signedPct(r.low)} to ${signedPct(r.high)}, middle ${signedPct(r.mid)}`}>
        <span className="ol-zero" style={{ left: `${zero}%` }}><i>0%</i></span>
        <span className="ol-span" style={{ left: `${lo}%`, width: `${Math.max(hi - lo, 0.8)}%` }} />
        {([["Low", r.low, lo], ["Middle", r.mid, mid], ["High", r.high, hi]] as const).map(([n, v, p]) => <span key={n} className={"ol-pin " + n.toLowerCase()} style={{ left: `${p}%` }} title={`${n} ${signedPct(v)}`} />)}
      </div>
      <dl className="ol-vals">
        {([["Low", r.low, r.lowCr], ["Middle", r.mid, r.midCr], ["High", r.high, r.highCr]] as const).map(([n, v, cr]) => <div key={n}><dt>{n}</dt><dd>{signedPct(v)}</dd><dd className="faint">{crs(cr)}</dd></div>)}
      </dl>
    </div>
  );
}

function GroupRow({ g }: { g: OutlookGroup }) {
  const b = outlookBand(g.score);
  return (
    <li className={"ol-g" + (g.status === "unavailable" ? " is-na" : "")}>
      <div className="ol-g-top"><span className="ol-g-name">{g.name}</span><span className="ol-g-w faint">{nf(g.weightPct, 1)}%</span>
        <span className="ol-g-score mono" style={{ color: bandInk(b) }}>{g.score == null ? "—" : Math.round(g.score)}</span></div>
      <div className="ol-bar" role="img" aria-label={g.score == null ? `${g.name}: not available` : `${g.name}: ${Math.round(g.score)} out of 100, ${g.band.color}`}>
        {g.score != null && <span style={{ width: `${g.score}%`, background: bandVar(b) }} />}</div>
      <div className="ol-g-sub faint">{g.status === "unavailable" ? <><b>Not available for this company.</b> {g.reason}</> : `${g.coverage.measured} of ${g.coverage.total} measures worked out`}</div>
    </li>
  );
}

function Sliders({ kind, names, weights, onChange, onReset }: { kind: Kind; names: Record<string, string>; weights: Weights; onChange: (l: string, v: number) => void; onReset: () => void }) {
  const total = totalOf(weights);
  return (
    <fieldset className="ol-sliders"><legend className="sr-only">Weight of each area, in percent</legend>
      {Object.keys(weights).map((l) => (
        <div className="ol-sl" key={l}>
          <label htmlFor={`ol-${kind}-${l}`}>{names[l] ?? `Group ${l}`}</label>
          <input id={`ol-${kind}-${l}`} type="range" min={0} max={100} step={0.5} value={weights[l]} onChange={(e) => onChange(l, Number(e.target.value))} aria-valuetext={`${weights[l]} percent`} />
          <output htmlFor={`ol-${kind}-${l}`} className="mono">{nf(weights[l], 1)}%</output>
        </div>))}
      <div className="ol-total" aria-live="polite"><span>Total <b className="mono">{nf(total, 1)}%</b></span>
        <button type="button" className="btn ghost" onClick={onReset} disabled={isDefault(kind, weights)}>Reset to our model</button></div>
    </fieldset>
  );
}

function Skeleton() {
  return <div className="ol-skel" aria-busy="true" aria-label="Loading the outlook"><div className="sk-ring" /><div className="sk-lines"><i /><i /><i /><i /><i /></div></div>;
}

// ---------------------------------------------------------------------------------------------------------- /outlook/:symbol
export function OutlookPage() {
  const { symbol = "" } = useParams();
  const sym = symbol.toUpperCase();
  useDocTitle(`${sym} profit and revenue outlook`, "An outlook score and an indicative growth range for profit and revenue, from the company's own reported history. Not a forecast, not advice.");
  const { has } = useUI();
  const { user } = useAuth();
  const gold = has("gold") && !!user && !DEMO;
  const [kind, setKind] = useState<Kind>("profit");
  const [mode, setMode] = useState<"model" | "custom">("model");
  const [custom, setCustom] = useState<Record<Kind, Weights>>({ profit: { ...DEFAULT_WEIGHTS.profit }, revenue: { ...DEFAULT_WEIGHTS.revenue } });
  const weights = custom[kind];
  const [sent, setSent] = useState<Weights>(weights);          // the weights last settled on: the server is asked after the sliders stop moving
  useEffect(() => { const h = window.setTimeout(() => setSent(weights), 400); return () => window.clearTimeout(h); }, [weights]);
  const q = useOutlook(sym, kind, mode === "custom" ? sent : null, gold);
  const names = useMemo(() => Object.fromEntries((q.data?.groups ?? []).map((g) => [g.letter, g.name])), [q.data]);
  const last = useRef<Outlook | null>(null);
  if (q.data) last.current = q.data;
  const d = q.data ?? (q.isFetching ? last.current : null);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const onTabKey = (e: React.KeyboardEvent, i: number) => {
    const n = e.key === "ArrowRight" ? (i + 1) % 2 : e.key === "ArrowLeft" ? (i + 1) % 2 : -1;
    if (n >= 0) { e.preventDefault(); setKind(TABS[n].kind); tabRefs.current[n]?.focus(); }
  };
  const err = q.error;

  return (
    <>
      <section className="pagehead"><div className="wrap"><div className="eyebrow">Gold tool</div><h1>Profit and revenue outlook</h1>
        <p>{d?.name ? <><b>{d.name}</b> <span className="mono faint">{sym}</span> · </> : <><span className="mono">{sym}</span> · </>}From the company's own reported history. <Link to={`/stocks/${encodeURIComponent(sym)}`}>Open its report</Link> · <Link to="/outlook">Another company</Link></p></div></section>
      <div className="wrap ol">
        <Gate tier="gold" title="Profit and revenue outlook" points={GATE_POINTS}>
          <div className="ol-tabs" role="tablist" aria-label="Forecast">
            {TABS.map((t, i) => (
              <button key={t.kind} ref={(el) => { tabRefs.current[i] = el; }} role="tab" id={`ol-tab-${t.kind}`} aria-selected={kind === t.kind} aria-controls="ol-panel" tabIndex={kind === t.kind ? 0 : -1}
                className={kind === t.kind ? "on" : ""} onClick={() => setKind(t.kind)} onKeyDown={(e) => onTabKey(e, i)}>{t.label} outlook</button>))}
          </div>
          <div id="ol-panel" role="tabpanel" aria-labelledby={`ol-tab-${kind}`} className="ol-panel">
            <div className="ol-mode" role="radiogroup" aria-label="How the areas are weighted">
              {([["model", "Our model"], ["custom", "Set your own"]] as const).map(([m, label]) => (
                <button key={m} type="button" role="radio" aria-checked={mode === m} className={mode === m ? "on" : ""} onClick={() => setMode(m)}>{label}</button>))}
            </div>
            {mode === "custom" && <Sliders kind={kind} names={names} weights={weights} onChange={(l, v) => setCustom((c) => ({ ...c, [kind]: rebalance(c[kind], l, v) }))} onReset={() => setCustom((c) => ({ ...c, [kind]: { ...DEFAULT_WEIGHTS[kind] } }))} />}
            {mode === "custom" && !d && <p className="faint">Group names appear once the first result has loaded.</p>}

            {!gold ? null : q.isLoading && !d ? <Skeleton /> : err && !d ? (
              <p className="formerr" role="alert">{err.status === 404 ? "This company's report is not stored yet. Open its page once, then come back." : (err.body?.detail as string) || "Could not load the outlook."}</p>
            ) : d ? (
              <div className={"ol-out" + (q.isFetching ? " is-busy" : "")} aria-busy={q.isFetching}>
                <section className="card ol-result" aria-labelledby="ol-res-h">
                  <h2 id="ol-res-h">{kind === "profit" ? "Profit" : "Revenue"} outlook score</h2>
                  <div className="ol-res">
                    <Ring value={d.score.value} />
                    <div>
                      {d.score.value == null ? <><p className="ol-word">Not enough data for an outlook</p><p className="muted">{d.score.reason}</p></>
                        : <p className="ol-word" style={{ color: bandInk(outlookBand(d.score.value)) }}>{d.score.band.word} <span className="faint">· {d.score.band.color}</span></p>}
                      <p className="ol-cov">{d.coverage.measured} of {d.coverage.total} measures could be worked out for this company</p>
                      <p className="faint">Latest year {d.asOf.yearly ?? "—"} · latest quarter {d.asOf.quarterly ?? "—"} · {d.statement} statements{d.mode === "custom" ? " · your weights" : ""}</p>
                    </div>
                  </div>
                  {d.isLender && kind === "profit" && <p className="ol-note" role="note"><Icon name="info" />This is a bank or lender: margins, operating costs and borrowing are not meaningful for it, so those measures are left out.</p>}
                </section>

                <section className="card" aria-labelledby="ol-grp-h">
                  <h2 id="ol-grp-h">Score by area</h2>
                  <ul className="ol-groups">{d.groups.map((g) => <GroupRow key={g.letter} g={g} />)}</ul>
                </section>

                <section className="card" aria-labelledby="ol-rng-h">
                  <h2 id="ol-rng-h">Indicative range, next four quarters <span className="tier gold">Scenario</span></h2>
                  {d.range.available ? (
                    <>
                      <p className="muted">{d.range.metric[0].toUpperCase() + d.range.metric.slice(1)} for the next four quarters in total, against the same four quarters a year earlier ({d.range.baseline}: {crs(d.range.baselineAmountCr)}).</p>
                      <RangeGraphic r={d.range} />
                      <p className="faint">Built from {d.range.basedOn} and how much this company's own quarterly growth has varied{d.range.tilted ? ", nudged by the outlook score" : ""}.{d.range.cappedNote ? ` ${d.range.cappedNote} An end was held at that limit.` : ""}</p>
                    </>
                  ) : <p className="ol-empty"><b>Not enough history for a range.</b> {d.range.reason.replace(/^Not enough history for a range: /, "")}</p>}
                </section>
                <p className="ol-disc">Scenario from the company's reported history. Not a forecast, not advice. Information only, not investment advice.</p>
              </div>
            ) : null}
          </div>
        </Gate>
      </div>
    </>
  );
}
