import { useState } from "react";
import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { PHILOSOPHY, PROCESS } from "../content/site";
import { getPortfolio, type PortfolioReport } from "../lib/siteApi";
import { asOfLabel, usableReport, winRatePct } from "../lib/portfolioView";
import { Reveal } from "./Reveal";
import { Icon } from "../lib/icons";
import "../styles/f3.css";

/** The founder's own recorded numbers, from the same report the Portfolio page uses. No report, no section: nothing is ever filled in. */
export function Performance() {
  const { data } = useQuery<PortfolioReport>({ queryKey: ["portfolio"], queryFn: getPortfolio, retry: 1, staleTime: 300_000 });
  if (!usableReport(data)) return null;
  const k: [string, string, string][] = [
    ["Net P&L", data.headline.netPnl, "After all charges"],
    ["Net ROI", data.headline.netRoi, `On ${data.profile.deployedCapital} deployed capital`],
    ["Win rate", winRatePct(data), `${data.summary.winningTrades} of ${data.summary.tradeCount} realised trades made a profit`],
    ["Realised trades", String(data.summary.tradeCount), `Through ${asOfLabel(data)}`],
  ];
  return (
    <section className="sec hh-sec" id="performance" aria-labelledby="perfT"><div className="wrap">
      <Reveal className="hh-head"><div className="hh-kicker">Recorded results</div><h2 id="perfT">The founder's own realised trades</h2><p>As of {asOfLabel(data)} · {data.profile.reportPeriod} · {data.profile.financialYear}</p></Reveal>
      <dl className="pf-kpis">{k.map(([t, v, d]) => <div key={t}><dt>{t}</dt><dd>{v}</dd><small>{d}</small></div>)}</dl>
      <p className="pf-basis"><b>Basis:</b> realised profit and loss only (positions sold in the period), taken from the broker's statement ({data.sourceFileName}), after brokerage, taxes and other charges, on {data.profile.deployedCapital} of average deployed capital. One personal account, unaudited. It is not a track record of any FinLit service or product.</p>
      <p className="pf-basis"><b>Past performance does not indicate future returns; not a recommendation.</b> {" "}<Link to="/portfolio" className="hh-link">See every trade and the charges <Icon name="arrow" /></Link></p>
    </div></section>
  );
}

const STAGE_TEXT: Record<string, string> = {
  "Idea Generation": "Identify businesses and themes worth researching.",
  "Industry Analysis": "Understand industry trends, competition and business cycles.",
  "Business Quality": "Assess financial strength, management and competitive advantages.",
  "Valuation & Modelling": "Evaluate assumptions and valuation against business fundamentals.",
  "Position Sizing & Risk": "Consider portfolio exposure, position size and downside risk.",
  "Monitoring & Review": "Review results and developments against the original thesis.",
  "Exit Discipline": "Reassess holdings when the thesis, valuation or risk changes.",
};

export function Process() {
  const [on, setOn] = useState(0);
  const a = PROCESS[on];
  return (
    <section className="sec hh-sec" id="process" aria-labelledby="procT"><div className="wrap">
      <Reveal className="hh-head"><div className="hh-kicker">How we think</div><h2 id="procT">From research to portfolio decisions</h2><p>The seven steps we follow in our own research. Tap a step to read it.</p></Reveal>
      <ol className="pr-steps" aria-label="Seven-step research process">{PROCESS.map((s, i) => (
        <li key={s.n}><button type="button" className={i === on ? "on" : ""} aria-pressed={i === on} aria-label={`Step ${i + 1}: ${s.title}`} onClick={() => setOn(i)}><span className="pr-n">{s.n}</span><span>{s.title}</span></button></li>))}
      </ol>
      <div className="pr-detail" aria-live="polite"><span className="pr-n">{a.n}</span><div><h3>{a.title}</h3><p>{STAGE_TEXT[a.title] ?? a.detail}</p></div></div>
    </div></section>
  );
}

export function Philosophy() {
  return (
    <section className="ph-band" aria-label="Investment principles"><div className="wrap">
      <ul>{PHILOSOPHY.map((p) => <li key={p}>{p}</li>)}</ul>
    </div></section>
  );
}
