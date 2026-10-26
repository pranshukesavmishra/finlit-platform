import { useContext, useState } from "react";
import { AlertButton } from "../components/AlertComposer";
import { Link } from "react-router";
import { Icon } from "../lib/icons";
import { MINUS, capSize, dateIN, fmtUnit, initials, nf, signed } from "../lib/format";
import { useUI, TIER } from "../lib/ui";
import { watch as wl, useWatchlist } from "../lib/watchlist";
import { Spark } from "../charts/Small";
import { Gate, OpenAccess } from "../components/Gate";
import { PrismCompare, PrismDetail } from "./PrismCompare";
import { ScoreCard, ScoreDetail } from "./ScoreCard";
import { DashToggle, useDashOpen } from "./DashToggle";
import { usePrismLatest } from "./PrismCard";
import { apiUrl } from "../lib/api";
import { Info } from "../components/Info";
import { LeadLine } from "./Leadership";
import { type Financials, type Ratios, type Summary } from "../lib/api";
import { csvOf, metric, offlineHtml, saveFile } from "./derive";
import { TradingFacts } from "./TradingFacts";

const KPI_SPEC: [key: string, label: string, icon: string, color: string][] = [
  ["market_cap", "Market cap", "cap", "--p-growth"], ["pe", "P/E", "tag", "--p-quality"], ["pb", "P/B", "id", "--p-quality"], ["ev_ebitda", "EV/EBITDA", "gauge", "--p-quality"],
  ["dividend_yield", "Div. yield", "coins", "--gold"], ["roe", "ROE", "percent", "--p-quality"], ["roce", "ROCE", "growth", "--p-profit"], ["debt_to_equity", "Debt/Equity", "balance", "--p-balance"],
];


export function Hero({ s, ratios, fin, jump }: { s: Summary; ratios?: Ratios; fin?: Financials; jump: (id: string) => void }) {
  const { has, toast, upgrade } = useUI();
  const [dashOpen, setDashOpen] = useDashOpen();
  const [dl, setDl] = useState(false);
  const open_ = useContext(OpenAccess);
  const two = has("gold") || open_;   // Gold sees the score and FinLit Prism side by side
  const prism = usePrismLatest(s.profile.symbol, s.meta.statement, two).data;
  const prismRep = prism?.kind === "report" ? prism.report : null;
  const wlState = useWatchlist(); void wlState;
  const watch = wl.has(s.profile.symbol);
  const q = s.quote, p = s.profile, good = (q.change ?? 0) >= 0, cov = s.dataQuality.coverage;
  const asOf = q.asOf ? new Date(q.asOf) : null;
  const need = (tier: "silver" | "gold", what: string) => { if (has(tier)) return true; upgrade(tier, `${what} come with the ${TIER[tier].n} plan.`); return false; };
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
              <LeadLine symbol={p.symbol} jump={jump} />
            </div>
          </div>
          <div className="idr">
            <div>
              <div className="px"><span className="rs">₹</span>{q.price == null ? MINUS : nf(q.price)}</div>
              {q.price == null && cov && cov.reasons.length > 0 && <div className="cov-note" role="note">No price shown: {cov.reasons[0]}.</div>}
              <div className="px-sub"><span className={"chip " + (good ? "up" : "down")}>{q.change == null ? "" : (q.change > 0 ? "+" : q.change < 0 ? MINUS : "") + nf(q.change)} · {signed(q.changePct)}</span>
                <span>{asOf && !Number.isNaN(+asOf) ? `NSE · ${dateIN(asOf.toISOString(), { day: "numeric", month: "short" })}, ${asOf.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata" })} IST` : "NSE"}</span></div>
            </div>
            <svg className="spark-hero" aria-label="One-year price trend" role="img" viewBox="0 0 150 54"><HeroSpark values={s.sparkline.c} /></svg>
            <div className="actions">
              <AlertButton symbol={s.profile.symbol} className="btn" label="Set alert" />
              <button className={"btn " + (watch ? "on" : "primary")} aria-pressed={watch} onClick={toggleWatch}><Icon name="spark" /><span>{watch ? "Watching" : "Watchlist"}</span>{!has("silver") && <Icon name="lock" className="lk" />}</button>
              <Link className="btn" to={`/dcf?sym=${encodeURIComponent(s.profile.symbol)}&load=1`} title="Value this company with the DCF calculator (Gold)"><Icon name="rupee" /><span>Value (DCF)</span>{!has("gold") && <Icon name="lock" className="lk" />}</Link>
              <div className="dl" style={{ position: "relative" }}>
                <button className="btn" aria-haspopup="menu" aria-expanded={dl} onClick={() => { if (!dl && !need("silver", "Downloads and data export")) return; setDl((d) => !d); }}>
                  <Icon name="table" /><span>Download</span>{!has("silver") && <Icon name="lock" className="lk" />}</button>
                {dl && (
                  <div className="dl-menu" role="menu">
                    <button role="menuitem" onClick={() => download("pdf")}><b>Research note · PDF</b><span className="d">Print-ready report with charts</span></button>
                    <button role="menuitem" onClick={() => download("html")}><b>Offline copy · HTML</b><span className="d">One file that opens without internet</span></button>
                    {prismRep && (Date.parse(prismRep.pdfAvailableUntil || "") > Date.now()
                      ? <a role="menuitem" href={apiUrl(`/api/prism/reports/${encodeURIComponent(prismRep.id)}/pdf`)} download onClick={() => setDl(false)}><b>FinLit Prism · PDF</b><span className="d">The Prism rating as a report you can keep</span></a>
                      : <Link role="menuitem" to={`/prism/${encodeURIComponent(p.symbol)}`} onClick={() => setDl(false)}><b>FinLit Prism · PDF</b><span className="d">Open the Prism page to save it as a PDF</span></Link>)}
                    <button role="menuitem" onClick={() => download("csv")}><b>Data · CSV</b><span className="d">Statements, ratios and scores for Excel</span></button>
                  </div>
                )}
              </div>
              <button className="btn" aria-label="Copy link to this report" onClick={() => { navigator.clipboard?.writeText(location.href.split("#")[0]).then(() => toast("Link to this report copied."), () => toast(location.href)); }}><Icon name="arrow" /><span>Share</span></button>
            </div>
          </div>
        </div>
        <TradingFacts s={s} />

        <div className="pz-pair dk-pair" data-open={dashOpen}>
        <Gate tier="silver" title="Unlock the FinLit Research Score" points={["Overall score from our proprietary model", "Five-pillar scorecard on every stock page", "See how each parameter drives the score"]}>
          <ScoreCard s={s} ratios={ratios} jump={jump} two={two} expanded={dashOpen} />
        </Gate>
        <PrismCompare symbol={s.profile.symbol} name={p.name} statement={s.meta.statement} />
        </div>
        <DashToggle open={dashOpen} onToggle={setDashOpen} controls="dk-full" />
        <div id="dk-full" className="dk-full" hidden={!dashOpen}>
          {dashOpen && <>
            {(has("silver") || open_) && <ScoreDetail s={s} ratios={ratios} />}
            {two && <PrismDetail symbol={s.profile.symbol} statement={s.meta.statement} />}
          </>}
        </div>

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
