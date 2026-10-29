import { Link } from "react-router";
import { PageArt } from "../components/PageArt";
import { Reveal } from "../components/Reveal";
import { useDocTitle } from "../lib/title";
import { LEAD_NOTE } from "../stock/Leadership";

/** "How this works": the rules of the Leader / In line / Laggard label in plain words, and the evidence from four sectors (21 years of weekly prices,
 *  a research study; the figures here are fixed results of that study, not live data). */
type Sector = { name: string; tier: "consistent" | "mixed" | "not_reliable"; rate: number; checks: number; periods: [string, number][]; gap: string; t: string; index: string; best: string; worst: string };
const SECTORS: Sector[] = [
  { name: "Pharma", tier: "consistent", rate: 64, checks: 278, periods: [["05–09", 58], ["10–14", 73], ["15–19", 59], ["20–26", 67]], gap: "+2.8", t: "1.6", index: "+83.6%", best: "Glenmark +347.9%", worst: "Gland −18.0%" },
  { name: "IT", tier: "mixed", rate: 60, checks: 269, periods: [["05–09", 35], ["10–14", 68], ["15–19", 48], ["20–26", 74]], gap: "+2.6", t: "1.3", index: "−11.0%", best: "Persistent +192.3%", worst: "Wipro −46.7%" },
  { name: "Banks", tier: "mixed", rate: 60, checks: 278, periods: [["05–09", 59], ["10–14", 59], ["15–19", 76], ["20–26", 43]], gap: "+1.3", t: "0.5", index: "+37.6%", best: "Indian Bank +369.6%", worst: "IndusInd Bank −27.7%" },
  { name: "Auto", tier: "not_reliable", rate: 46, checks: 278, periods: [["05–09", 38], ["10–14", 68], ["15–19", 52], ["20–26", 34]], gap: "−1.1", t: "−0.6", index: "+123.8%", best: "TVS Motor +556.8%", worst: "Balkrishna −16.5%" },
];
const TIER = { consistent: "Consistent", mixed: "Mixed", not_reliable: "Not reliable" } as const;

function Persistence() {
  const W = 760, H = 250, top = 34, bot = 196, colW = 26, gap = 10;
  const y = (v: number) => bot - (v / 100) * (bot - top);
  return (
    <svg className="lx-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Pharma is the only sector where leaders beat laggards in every five-year period. IT and banks did in some periods and not others. Auto did so in two of four periods and in 46 percent of checks overall.">
      {SECTORS.map((s, si) => {
        const x0 = 18 + si * 186;
        return (
          <g key={s.name}>
            <text x={x0} y="16" className="lx-sn">{s.name}</text><text x={x0 + 70} y="16" className={"lx-st " + s.tier}>{TIER[s.tier]}</text>
            <line x1={x0 - 4} x2={x0 + 4 * (colW + gap)} y1={y(50)} y2={y(50)} className="lx-coin" />
            {s.periods.map(([p, v], i) => (
              <g key={p}>
                <rect x={x0 + i * (colW + gap)} y={y(v)} width={colW} height={bot - y(v)} rx="3" className={"lx-col " + (s.tier === "consistent" ? "ok" : "")} />
                <text x={x0 + i * (colW + gap) + colW / 2} y={y(v) - 5} textAnchor="middle" className="lx-v">{v}%</text>
                <text x={x0 + i * (colW + gap) + colW / 2} y={bot + 14} textAnchor="middle" className="lx-t">{p}</text>
              </g>
            ))}
          </g>
        );
      })}
      <text x="18" y={H - 6} className="lx-t">Dashed line: 50%, a coin flip. Consistent = 55% or more overall and at least 50% in every period.</text>
    </svg>
  );
}

function Overall() {
  return (
    <div className="lx-bars" role="img" aria-label="Share of checks where the top 30 percent beat the bottom 30 percent over the next six months: pharma 64, IT 60, banks 60, auto 46.">
      {SECTORS.map((s) => (
        <div key={s.name} className="lx-bar-row"><span className="n">{s.name}</span><div className="lx-bar"><i style={{ width: `${s.rate}%` }} className={s.tier} /><u style={{ left: "50%" }} /><u className="c55" style={{ left: "55%" }} /></div><b>{s.rate}%</b><span className={"ld-tier " + s.tier}>{TIER[s.tier]}</span></div>
      ))}
      <div className="lx-bar-key"><span style={{ left: "50%" }}>50% coin flip</span><span style={{ left: "55%" }} className="c55">55% shown as consistent</span></div>
    </div>
  );
}

function WithinSector() {
  // five-year price return of the index, the best and the worst stock: the spread inside a sector dwarfs the sector's own move
  const rows = [
    { n: "IT", idx: -11.0, best: 192.3, worst: -46.7, b: "Persistent", w: "Wipro" }, { n: "Banks", idx: 37.6, best: 369.6, worst: -27.7, b: "Indian Bank", w: "IndusInd Bank" },
    { n: "Pharma", idx: 83.6, best: 347.9, worst: -18.0, b: "Glenmark", w: "Gland" }, { n: "Auto", idx: 123.8, best: 556.8, worst: -16.5, b: "TVS Motor", w: "Balkrishna" },
  ];
  const lo = -60, hi = 600, W = 760, rowH = 46, H = rows.length * rowH + 40, x = (v: number) => 120 + ((v - lo) / (hi - lo)) * (W - 150);
  return (
    <svg className="lx-svg" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Five-year price return of each sector index, its best stock and its worst stock. In IT the index fell 11 percent while Persistent rose 192 percent and Wipro fell 47 percent.">
      <line x1={x(0)} x2={x(0)} y1="8" y2={H - 28} className="lx-zero" />
      {rows.map((r, i) => { const yy = 22 + i * rowH; return (
        <g key={r.n}>
          <text x="10" y={yy + 4} className="lx-sn">{r.n}</text>
          <line x1={x(r.worst)} x2={x(r.best)} y1={yy} y2={yy} className="lx-span" />
          <circle cx={x(r.worst)} cy={yy} r="6" className="lx-pw" /><circle cx={x(r.best)} cy={yy} r="6" className="lx-pb" /><rect x={x(r.idx) - 5} y={yy - 9} width="10" height="18" rx="2" className="lx-pi" />
          <text x={x(r.worst)} y={yy + 22} textAnchor="middle" className="lx-t">{r.w} {r.worst.toFixed(1).replace("-", "−")}%</text>
          <text x={Math.min(x(r.best), W - 80)} y={yy - 12} textAnchor="middle" className="lx-t">{r.b} +{r.best.toFixed(1)}%</text>
          <text x={x(r.idx) + 8} y={yy + 22} className="lx-t strong">Index {r.idx > 0 ? "+" : "−"}{Math.abs(r.idx).toFixed(1)}%</text>
        </g>); })}
      <text x={x(0)} y={H - 8} textAnchor="middle" className="lx-t">0%</text>
    </svg>
  );
}

export function LeadershipLabelPage() {
  useDocTitle("How the Leader label works", "How FinLit labels a stock Leader, In line or Laggard from its last 12 months against its peers, and what 21 years of weekly prices say about whether leadership lasts.");
  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><PageArt kind="why" /><div className="eyebrow">How this works</div><h1>Leader, In line, Laggard</h1><p>A plain description of how a stock's last 12 months compare with its peers. It looks back; it does not predict.</p></div></section>

      <section className="sec" style={{ paddingTop: 16 }}><div className="wrap lx">
        <Reveal><div className="lx-note" role="note"><b>{LEAD_NOTE}</b> The label is not advice and not a signal to trade. It is one way to see where a company stands among similar companies.</div></Reveal>

        <Reveal className="sec-h"><div className="eyebrow">The rules</div><h2>How a stock gets its label</h2></Reveal>
        <ol className="lx-rules">
          <li><b>Peers.</b> A list of similar companies. For IT, pharma, private banks, PSU banks and autos it is the researched list of leading names behind the study below. For other companies it is the list of the 35 largest actively traded companies in the same industry, or in the same sector when the industry has no list. A list is used when at least 6 of its companies have a year of prices; a company on no list, or on a list too thin to rank here, is compared with the companies in its industry as FinLit's data provider groups them (widened to the whole sector if fewer than 6 have a year of prices). The page says which group was used and how many of its names are ranked.</li>
          <li><b>Two yardsticks.</b> The sector index for the list (Nifty IT for IT, Nifty PSU Bank for PSU banks, Nifty Metal for steel and so on), and a market index by company size: Nifty 50 for companies worth ₹1,07,000 crore or more, Nifty Midcap 150 for ₹32,800 crore or more, Nifty Smallcap 250 for the rest, and Nifty 500 when the size is not known. Where a list has no index, we use the average of its ranked peers and say so.</li>
          <li><b>Relative return.</b> The stock's price return minus the yardstick's, in percentage points, over 3, 6 and 12 months.</li>
          <li><b>Rank.</b> Peers are ordered by their 12-month return against the sector index. The 3 and 6 month figures are shown but not ranked on.</li>
          <li><b>The label.</b> <span className="ld-chip leader"><i className="ld-dot" />Leader</span> means in the top 30% of peers and ahead of the sector index over 12 months. <span className="ld-chip laggard"><i className="ld-dot" />Laggard</span> means in the bottom 30% and behind it. Everything else is <span className="ld-chip in_line"><i className="ld-dot" />In line</span>. If a whole group is behind its index, nobody is a Leader.</li>
          <li><b>Direction.</b> “Gaining” when the 3-month relative return is 5 points or more; “weakening” when it is minus 5 or less.</li>
          <li><b>Fundamentals note.</b> A Leader whose fundamentals rank in the bottom 30% of its peers gets a caution note, and a Laggard whose fundamentals rank in the top 30% gets a note that fundamentals are stronger than the price.</li>
          <li><b>Steadiness.</b> Labels are refreshed weekly after Friday's close. A new label must come out the same way two weeks running before it replaces the old one; until then the page shows this week's own answer beside the label and says so. Thinly traded stocks (under ₹1 crore a day), stocks with under a year of prices and stale prices are left out rather than guessed, and each list names the companies it left out and why.</li>
        </ol>

        <Reveal className="sec-h"><div className="eyebrow">Why the stock's own group matters</div><h2>The gap inside a sector is bigger than the sector's move</h2></Reveal>
        <p className="lx-p">Five years to 19 October 2026, price only. In IT the index fell 11% while Persistent rose 192% and Wipro fell 47%. In every sector, the best and worst stock were far apart, so it helps to know where a stock sits in its group and not only how its sector did. The label is about the last year, and it changes: Gland, the five-year laggard in pharma, is a Leader today.</p>
        <WithinSector />

        <Reveal className="sec-h"><div className="eyebrow">Has leadership lasted?</div><h2>It depends on the sector</h2></Reveal>
        <p className="lx-p">We tested the 12-month rank on weekly prices back to 2005: about 270 checks per sector, one every 4 weeks, each looking 6 months ahead. Pharma is the only sector where leaders beat laggards in every five-year period. IT and banks worked in some periods and failed in others, and auto failed more often than it worked.</p>
        <Persistence />
        <Overall />
        <div className="lx-tblw"><table className="lx-tbl"><caption>Four sectors, 2005 to 2026</caption>
          <thead><tr><th scope="col">Sector</th><th scope="col">Checks</th><th scope="col">Verdict</th><th scope="col">Average gap over 6 months, leaders minus laggards</th><th scope="col">Strength (t, adjusted for overlap)</th></tr></thead>
          <tbody>{SECTORS.map((s) => <tr key={s.name}><th scope="row">{s.name}</th><td>{s.checks}</td><td>{TIER[s.tier]}</td><td>{s.gap.replace("-", "−")} pts</td><td>{s.t.replace("-", "−")}</td></tr>)}</tbody></table></div>
        <p className="lx-p">Even where leadership held, the edge was small: two to three points over six months, and no sector cleared the usual t of 2. So the label is a description with a weak, sector-dependent tendency behind it, not a forecast. Leaders also fell as hard as everything else in 2008 and 2020: being ahead is no protection in a crash.</p>

        <Reveal className="sec-h"><div className="eyebrow">What you see on a stock page</div><h2>The “Has leadership held here?” card</h2></Reveal>
        <p className="lx-p">Each stock page shows the verdict for its own group: <b>Consistent</b> (leaders beat laggards in 55% or more of checks and in every five-year period), <b>Mixed</b> (50% or more overall, not in every period) or <b>Not reliable</b> (under 50%). It needs about 10 years of weekly prices. For IT, pharma, private banks, PSU banks and autos the card shows the study's own result (the figures above, labelled as the study's) until FinLit's stored weekly prices are long enough to repeat the test, and then it shows FinLit's own. For every other group, until the history is long enough the card says “Not enough history to judge” rather than guess. The figures above come from a separate research study and are fixed results, not live data.</p>

        <Reveal className="sec-h"><div className="eyebrow">Limits</div><h2>What to keep in mind</h2></Reveal>
        <ul className="lx-rules plain">
          <li><b>Survivorship.</b> The study used today's industry lists. Companies that collapsed or were taken over are missing, which flatters the averages. Leaders against laggards is less affected, but treat the figures as approximate.</li>
          <li><b>Overlap.</b> Checks every 4 weeks that each look 6 months ahead overlap, so there are about 42 independent six-month windows per sector.</li>
          <li><b>Small groups early on.</b> IT had about 7 rankable stocks in 2005–09, so that period's 35% rests on few names.</li>
          <li><b>Prices only.</b> Splits and bonuses are adjusted. Dividends are not included; adding them moved the results by four points at most.</li>
        </ul>
        <p className="lx-p"><Link to="/research" className="btn primary">Browse research</Link></p>
      </div></section>
    </>
  );
}
