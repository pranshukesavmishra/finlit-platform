import { useState } from "react";
import { AlertButton } from "../components/AlertComposer";
import { Link } from "react-router";
import { Icon } from "../lib/icons";
import { MINUS, capSize, dateIN, fmtUnit, initials, nf, num, signed } from "../lib/format";
import { useUI, TIER } from "../lib/ui";
import { watch as wl, useWatchlist } from "../lib/watchlist";
import { Dial } from "../charts/Dial";
import { Spark } from "../charts/Small";
import { Gate } from "../components/Gate";
import { Info } from "../components/Info";
import { ChartHelp } from "../components/ChartHelp";
import { scoreChange, useScoreHistory, type Financials, type Ratios, type Summary } from "../lib/api";
import { PILLAR_COLOR, PILLAR_ICON, csvOf, metric, offlineHtml, saveFile } from "./derive";

const KPI_SPEC: [key: string, label: string, icon: string, color: string][] = [
  ["market_cap", "Market cap", "cap", "--p-growth"], ["pe", "P/E", "tag", "--p-quality"], ["pb", "P/B", "id", "--p-quality"], ["ev_ebitda", "EV/EBITDA", "gauge", "--p-quality"],
  ["dividend_yield", "Div. yield", "coins", "--gold"], ["roe", "ROE", "percent", "--p-quality"], ["roce", "ROCE", "growth", "--p-profit"], ["debt_to_equity", "Debt/Equity", "balance", "--p-balance"],
];


export function Hero({ s, ratios, fin, jump }: { s: Summary; ratios?: Ratios; fin?: Financials; jump: (id: string) => void }) {
  const { has, toast, plan, upgrade } = useUI();
  const hist = useScoreHistory(s.profile.symbol, has("silver") && s.score.overall != null);
  const chg = scoreChange(hist.data?.points);
  const [open, setOpen] = useState<string | null>(null);
  const [dl, setDl] = useState(false);
  const wlState = useWatchlist(); void wlState;
  const watch = wl.has(s.profile.symbol);
  const q = s.quote, p = s.profile, good = (q.change ?? 0) >= 0;
  const asOf = q.asOf ? new Date(q.asOf) : null;
  const need = (tier: "silver" | "gold", what: string) => { if (has(tier)) return true; upgrade(tier, `${what} come with the ${TIER[tier].n} plan.`); return false; };
  const byKey = Object.fromEntries((ratios?.score.pillars || []).map((x) => [x.key, x]));
  const know = [
    ...(s.strengths.slice(0, 2).map((n) => ({ ...n, tone: "good" as const }))), ...(s.watchouts.slice(0, 1).map((n) => ({ ...n, tone: "bad" as const }))),
  ];
  const toggleWatch = () => {
    if (!need("silver", "Watchlist and portfolio tracking")) return;
    const on = !watch;
    if (on) { if (!has("gold") && wl.total() >= 30) { upgrade("gold", "Silver holds up to 30 stocks; Gold holds up to 1,000."); return; } wl.add(p.symbol); } else wl.remove(p.symbol);
    toast(on ? `${p.nse || p.symbol} added to your watchlist.` : `${p.nse || p.symbol} removed from your watchlist.`);
  };
  const download = (kind: "pdf" | "html" | "csv") => {
    setDl(false);
    const name = `${p.nse || p.symbol}-FinLit`;
    if (kind === "csv") { saveFile(name + "-Data.csv", csvOf(s, fin, ratios), "text/csv;charset=utf-8"); toast(`Data saved as ${name}-Data.csv.`); }
    if (kind === "html") { saveFile(name + "-Research.html", offlineHtml(s, fin, ratios), "text/html"); toast("Offline copy saved. It opens in any browser without internet."); }
    if (kind === "pdf") { toast("In the print window, choose “Save as PDF”."); setTimeout(() => window.print(), 400); }
  };
  const ob = open ? byKey[open] : null, os = open ? s.score.pillars.find((x) => x.key === open) : null;

  return (
    <section className="band hero" id="hero" aria-label={`${p.name} research report`}>
      <div className="wrap">
        <div className="crumbs"><Link to="/research">Research</Link><span>›</span><span>{p.macroSector || p.sector}</span><span>›</span><span style={{ color: "var(--text)" }}>{p.nse || p.symbol}</span></div>
        <div className="idrow">
          <div className="idl">
            <div className="badge" aria-hidden="true">{initials(p.name)}</div>
            <div style={{ minWidth: 0 }}>
              <h1>{p.name}</h1>
              <div className="tags"><span className="tag tk">{p.nse || p.symbol}</span><span className="tag">NSE</span>{p.sector && <span className="tag">{p.sector}</span>}{capSize(p.marketCapCr) && <span className="tag">{capSize(p.marketCapCr)}</span>}{p.bse && <span className="tag mono hide-sm">BSE {p.bse}</span>}</div>
            </div>
          </div>
          <div className="idr">
            <div>
              <div className="px"><span className="rs">₹</span>{q.price == null ? MINUS : nf(q.price)}</div>
              <div className="px-sub"><span className={"chip " + (good ? "up" : "down")}>{q.change == null ? "" : (q.change > 0 ? "+" : q.change < 0 ? MINUS : "") + nf(q.change)} · {signed(q.changePct)}</span>
                <span>{asOf && !Number.isNaN(+asOf) ? `NSE · ${dateIN(asOf.toISOString(), { day: "numeric", month: "short" })}, ${asOf.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" })} IST` : "NSE"}</span></div>
            </div>
            <svg className="spark-hero" aria-label="One-year price trend" role="img" viewBox="0 0 150 54"><HeroSpark values={s.sparkline.c} /></svg>
            <div className="actions">
              <AlertButton symbol={s.profile.symbol} className="btn" label="Set alert" />
              <button className={"btn " + (watch ? "on" : "primary")} aria-pressed={watch} onClick={toggleWatch}><Icon name="spark" /><span>{watch ? "Watching" : "Watchlist"}</span>{!has("silver") && <Icon name="lock" className="lk" />}</button>
              <div className="dl" style={{ position: "relative" }}>
                <button className="btn" aria-haspopup="menu" aria-expanded={dl} onClick={() => { if (!dl && !need("silver", "Downloads and data export")) return; setDl((d) => !d); }}>
                  <Icon name="table" /><span>Download</span>{!has("silver") && <Icon name="lock" className="lk" />}</button>
                {dl && (
                  <div className="dl-menu" role="menu">
                    <button role="menuitem" onClick={() => download("pdf")}><b>Research note · PDF</b><span className="d">Print-ready report with charts</span></button>
                    <button role="menuitem" onClick={() => download("html")}><b>Offline copy · HTML</b><span className="d">One file that opens without internet</span></button>
                    <button role="menuitem" onClick={() => download("csv")}><b>Data · CSV</b><span className="d">Statements, ratios and scores for Excel</span></button>
                  </div>
                )}
              </div>
              <button className="btn" aria-label="Copy link to this report" onClick={() => { navigator.clipboard?.writeText(location.href.split("#")[0]).then(() => toast("Link to this report copied."), () => toast(location.href)); }}><Icon name="arrow" /><span>Share</span></button>
            </div>
          </div>
        </div>


        <Gate tier="silver" title="Unlock the FinLit Research Score" points={["Overall score from our proprietary model", "Five-pillar scorecard on every stock page", "See how each parameter drives the score"]}>
          <article className="report" aria-labelledby="reportTitle">
            <div className="rhead">
              <div className="l"><span className="eyebrow" id="reportTitle">FinLit Research Report</span><span className="chip ghost">{s.dataQuality.fundamentalsAsOf} · {s.meta.statement === "consolidated" ? "Consolidated" : "Standalone"}</span>
                {plan === "gold" ? <span className="tier gold">Advanced model</span> : <span className="tier silver">Basic model</span>}<span className="live">Updated {dateIN(s.meta.generatedAt, { day: "numeric", month: "short" })}</span></div>
              <div className="meta">Model {s.score.model} · <a href="#method" onClick={(e) => { e.preventDefault(); jump("method"); }}>Pros & cons →</a></div>
            </div>
            <div className="rmain">
              <div className="dialcol">
                <Dial overall={s.score.overall} pillars={s.score.pillars} onPillar={(k) => setOpen((o) => (o === k ? null : k))} active={open} bandLabel={s.score.band.label} />
                <div className="dcap">Average of five pillars · select a ring segment <ChartHelp id="score-dial" /></div>
                {chg && <div className={"sdelta " + (chg.delta > 0 ? "up" : chg.delta < 0 ? "down" : "")} title={`Compared with ${dateIN(chg.since)}`}>{chg.delta > 0 ? "▲ +" : chg.delta < 0 ? "▼ −" : "● "}{Math.abs(chg.delta)} points <small>since {dateIN(chg.since, { day: "numeric", month: "short" })}</small></div>}
              </div>
              <div className="readcol">
                <div><div className="label" style={{ marginBottom: 10 }}>The read</div><p className="thesis">{s.thesis || (s.score.overall == null && !has("silver") ? "The written read of this company comes with the Silver plan, together with its FinLit score." : "Not enough data to summarise this company yet.")}</p></div>
                <div className="know">
                  {know.map((n) => (
                    <div key={n.key} style={{ "--k": n.tone === "good" ? "var(--p-quality)" : "var(--p-tech)" } as React.CSSProperties}>
                      <div className="kt"><Icon name={n.tone === "good" ? "check" : "alert"} />{n.title}</div><p>{n.text}</p>
                    </div>
                  ))}
                </div>
                <div className="disc"><Icon name="info" /><span>Research summary, not a recommendation to buy or sell. FinLit Ventures is a technology company and is not registered with SEBI or AMFI.</span></div>
              </div>
            </div>
            <div className="label" style={{ margin: "18px 0 8px", display: "flex", alignItems: "center", gap: 8 }}>The five pillars <ChartHelp id="score-pillars" /></div>
            <div className="pillars" role="group" aria-label="Five pillars">
              {s.score.pillars.map((pl, i) => {
                const c = `var(${PILLAR_COLOR[pl.key]})`, r = 22, circ = 2 * Math.PI * r;
                return (
                  <button key={pl.key} className={"ptile" + (open === pl.key ? " hot" : "")} style={{ "--pc": c } as React.CSSProperties} aria-expanded={open === pl.key} onClick={() => setOpen((o) => (o === pl.key ? null : pl.key))}>
                    <div className="pt-top"><span className="pt-ic"><Icon name={PILLAR_ICON[pl.key]} /></span>
                      <span className="ring"><svg viewBox="0 0 54 54" aria-hidden="true"><circle cx="27" cy="27" r={r} fill="none" stroke="var(--s3)" strokeWidth="5" /><circle cx="27" cy="27" r={r} fill="none" stroke={c} strokeWidth="5" strokeLinecap="round" strokeDasharray={`${(circ * (pl.score ?? 0)) / 100} ${circ}`} /></svg><b>{pl.score ?? "—"}</b></span></div>
                    <div className="pt-name">{pl.label}</div>
                    <span className={"vd " + (pl.score == null ? "na" : pl.band.key === "strong" ? "strong" : pl.band.key === "healthy" ? "healthy" : pl.band.key === "mixed" ? "mixed" : "weak")}>{pl.band.label}</span>
                    <div className="pt-ev">{pl.score == null && pl.reason ? pl.reason : (byKey[pl.key]?.inputs || []).filter((x) => x.value != null).slice(0, 2).map((x) => `${x.label} ${num(x.value)}`).join(" · ")}</div>
                    <div className="pt-bar"><i style={{ width: `${pl.score ?? 0}%`, animationDelay: `${0.45 + i * 0.08}s` }} /></div>
                  </button>
                );
              })}
            </div>
            <div className={"pdrawer" + (open ? " open" : "")}><div>
              {os && ob && (
                <div className="pd-in" style={{ "--pc": `var(${PILLAR_COLOR[os.key]})` } as React.CSSProperties}>
                  <div><h4><span className="pt-ic"><Icon name={PILLAR_ICON[os.key]} /></span>{os.label} · {os.score ?? "—"}/100 <span className={"vd " + (os.band.key === "strong" ? "strong" : os.band.key === "healthy" ? "healthy" : os.band.key === "mixed" ? "mixed" : "weak")}>{os.band.label}</span></h4>
                    <p>{os.score == null && os.reason ? os.reason : "Each input scores 18 / 38 / 58 / 76 / 92 against four thresholds; the pillar is the average of the inputs available."}</p></div>
                  <div className="pd-ev">{ob.inputs.map((x) => (
                    <div key={x.key}><div className="k">{x.label}</div><div className="v">{x.value == null ? "—" : num(x.value)}</div>
                      <div className="c">{x.score == null ? "Not reported" : `Scores ${x.score} · ${x.lowerIsBetter ? "≤" : "≥"} ${x.thresholds[3]} is great`}</div></div>
                  ))}</div>
                </div>
              )}
            </div></div>
          </article>
        </Gate>

        <div className="kpis">
          {KPI_SPEC.map(([key, label, icon, color]) => {
            const m = metric(s, key), e = ratios?.latest[key], val = m?.value ?? e?.value, unit = m?.unit ?? e?.unit, period = m?.period ?? e?.period;
            return (
              <div className="kpi" key={key} style={{ "--kc": `var(${color})` } as React.CSSProperties}>
                <div className="kl"><Icon name={icon} />{label} <Info g={ratios?.glossary[key]} /></div>
                <div className="v">{key === "market_cap" && val != null ? <>₹{val >= 100000 ? nf(val / 100000) : nf(val, 0)}<span className="unit">{val >= 100000 ? "L Cr" : "Cr"}</span></> : fmtUnit(val, unit)}</div>
                <div className="s">{period === "latest" ? "Latest" : period || ""}</div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function HeroSpark({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const mn = Math.min(...values), mx = Math.max(...values), n = values.length, X = (i: number) => 2 + (i / (n - 1)) * 140, Y = (p: number) => 48 - ((p - mn) / (mx - mn || 1)) * 42;
  const d = values.map((p, i) => `${i ? "L" : "M"}${X(i).toFixed(1)},${Y(p).toFixed(1)}`).join("");
  return (<><defs><linearGradient id="hsg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="var(--gold)" stopOpacity=".35" /><stop offset="1" stopColor="var(--gold)" stopOpacity="0" /></linearGradient></defs>
    <path d={`${d}L${X(n - 1)},52L2,52Z`} fill="url(#hsg)" /><path d={d} fill="none" stroke="var(--gold)" strokeWidth="1.8" strokeLinejoin="round" /><circle cx={X(n - 1)} cy={Y(values[n - 1])} r="3.5" fill="var(--gold-2)" /></>);
}
void MINUS; void Spark;
