// /methodology/mf-score: the Mutual Fund Health Score in plain language. Describes the model; it never advises.
import { Link } from "react-router";
import { useEffect, useState } from "react";
import { apiGet } from "../lib/api";
import walk from "../lib/fixtures/mfScoreWalk.json";
import { PILLARS, STATE_EXPLAIN, STATE_WORD } from "../lib/mfScoreUp";
import { useDocTitle } from "../lib/title";
import { GROUP_WEIGHTS, MF_SCORE_COMPLIANCE, MF_SCORE_NAME, PILLAR_HELP, SCORE_BANDS } from "../lib/mfScore";
import "../styles/mf.css";

const FAQ: [string, string][] = [
  ["Is a higher score a reason to invest?", "No. The score describes how a fund's past NAVs, costs and holdings compare with funds of the same kind. It is not a forecast and not advice."],
  ["Why do two funds with the same return have different scores?", "Return is one part. Risk (how bumpy and how deep the falls), Cost and Quality (age, size, how the portfolio is built) count too, with weights that depend on the fund group."],
  ["Why is my fund provisional or not rated?", "A fund with 12 to 35 months of NAV history is provisional and its label stops at Healthy. Under 12 months it is not rated. Heavy data gaps also make a score provisional."],
  ["What does a gap mean?", "When a figure is missing the measure takes the group value, which can never be better than a typical fund. The fund page lists every such measure under Data gaps."],
  ["How often does it change?", "The score is worked out every night and stored once a week. The fund page shows the stored weekly history."],
  ["Why are Direct and Regular plans scored separately?", "Each plan is compared with funds of the same plan, because the Regular plan's higher cost would otherwise count against it in every comparison."],
];
const ex = (v: number | null) => (v == null ? "—" : String(Math.round(v * 100) / 100));

export function MfScoreMethodPage() {
  const [runDate, setRunDate] = useState<string | null>(null);
  useEffect(() => { apiGet<{ runDate: string | null }>("/api/mf/scores/categories").then((r) => setRunDate(r.runDate)).catch(() => undefined); }, []);
  useDocTitle("How the Mutual Fund Health Score works", "The FinLit Mutual Fund Health Score in plain language: four parts, weights per fund group, how gaps are treated, and what the score is not.");
  return (
    <div className="wrap mf mfs-method">
      <p className="mf-back"><Link to="/funds">← All mutual fund schemes</Link></p>
      <header><span className="eyebrow">Method</span><h1>How the {MF_SCORE_NAME} works</h1>
        <p className="muted">{MF_SCORE_COMPLIANCE}</p></header>

      <section className="card mf-card"><h2 className="mf-h4">What the score is, and what it is not</h2>
        <ul className="mfs-list">
          <li><b>It is a health check against funds of the same kind.</b> A 75 for a small-cap fund and a 75 for a liquid fund do not mean the same thing. Always read the group, the rank inside it and the risk-o-meter next to the score.</li>
          <li><b>It is not a forecast.</b> Past returns say little about the next year, so Performance is capped at 35% of the score and is measured against similar funds.</li>
          <li><b>It is not a return against an index.</b> FinLit holds no index return series with dividends, so similar funds stand in for the benchmark. If every fund in a category did badly, the median is a low bar; the return-on-its-own measure limits that.</li>
          <li><b>For debt funds it sees the effect of a credit problem, not its cause.</b> The data holds no credit ratings, yield or duration, so a credit problem shows only after it reaches the NAV.</li>
          <li><b>It is not advice.</b> Nothing here tells anyone what to do with a fund. The limits behind the score are starting values set by the designer and are being tested; no accuracy is claimed.</li>
        </ul></section>

      <section className="card mf-card"><h2 className="mf-h4">Four parts, one total</h2>
        <p>The total is 0 to 100: <b>total = Performance × weight + Risk × weight + Cost × weight + Quality × weight</b>. Each part is itself a 0 to 100 score built from a few measures.</p>
        <ul className="mfs-list">{Object.entries(PILLAR_HELP).map(([k, v]) => <li key={k}><b>{k[0].toUpperCase() + k.slice(1)}.</b> {v}</li>)}</ul>
        <p>Every measure is turned into points with one rule: a worst value earns 0 points, a best value earns 100 and the points run in a straight line between them, never below 0 or above 100. Where the best and worst values coincide there is nothing to reward, so the measure scores a neutral 50.</p>
      </section>

      <section className="card mf-card"><h2 className="mf-h4">Weights by fund group</h2>
        <p>Each fund is placed in a group from its AMFI category. Percent of the total score:</p>
        <div className="tw"><table className="mf-cmp"><caption className="sr-only">Weights of the four parts by group</caption>
          <thead><tr><th scope="col">Group</th><th scope="col" className="num">Performance</th><th scope="col" className="num">Risk</th><th scope="col" className="num">Cost</th><th scope="col" className="num">Quality</th></tr></thead>
          <tbody>{GROUP_WEIGHTS.map((g) => <tr key={g.group}><th scope="row">{g.name}</th>{g.w.map((x, i) => <td className="num" key={i}>{x}</td>)}</tr>)}</tbody></table></div>
      </section>

      <section className="card mf-card"><h2 className="mf-h4">Who a fund is compared with</h2>
        <p>Direct and Regular plans are scored separately, each against its own plan. A fund is compared with the active Growth schemes of the same category and plan, with the fund itself left out. At least 8 such funds with the figure are needed; otherwise the comparison widens to the whole group (marked as substituted), and if that is still too small the measure uses the group value. Index funds and ETFs are compared with funds tracking the same index (at least 3). IDCW and other options carry the score of the Growth plan and say so.</p>
      </section>

      <section className="card mf-card"><h2 className="mf-h4">Gaps are shown as gaps</h2>
        <p>A measure with no data takes the <b>group value</b>: the lower of the group's median points and 50, so a gap can never score better than the typical fund. The page says how many measures used the group value and why. A zero that stands for "not reported" (for example an expense ratio of 0) is treated as missing; a zero that is a real result (no fall, no exit load, a risk-o-meter level of Low) is scored.</p>
      </section>

      <section className="card mf-card"><h2 className="mf-h4">History and status</h2>
        <div className="tw"><table className="mf-cmp"><thead><tr><th scope="col">Months of NAV history</th><th scope="col">What is used</th><th scope="col">Status</th></tr></thead><tbody>
          <tr><th scope="row">60 or more</th><td>Every measure</td><td>Rated</td></tr>
          <tr><th scope="row">36 to 59</th><td>3-year measures; the 5-year return measure is filled</td><td>Rated</td></tr>
          <tr><th scope="row">12 to 35</th><td>Window measures, trusted in proportion to their length</td><td>Provisional, label at most Healthy</td></tr>
          <tr><th scope="row">Under 12</th><td>Nothing</td><td>Not rated</td></tr></tbody></table></div>
        <p>A score also says what share of its weight rested on real data. A weak Risk or Quality part holds the total down, so a high return cannot hide weak risk or weak foundations.</p>
      </section>

      <section className="card mf-card" id="states"><h2 className="mf-h4">The five states of a measure</h2>
        <p>Every measure on a fund page carries one of these states, so a gap is never hidden.</p>
        <ul className="mfs-list">{(["A", "Z", "S", "F", "N"] as const).map((k) => <li key={k}><b>{k === "Z" ? "Zero points (loss)" : STATE_WORD[k]}.</b> {STATE_EXPLAIN[k]}</li>)}</ul></section>

      <section className="card mf-card" id="examples"><h2 className="mf-h4">Worked examples</h2>
        <ol className="mfs-list">
          <li><b>Points from a value.</b> A mid-sized equity fund's 3-year return is measured against the median of its similar funds. If the gap is limited to -5 and +5 points, a gap of 0 earns 50 points, +5 or more earns 100, -5 or less earns 0, and +2.5 earns 75. The line between is straight.</li>
          <li><b>A missing expense ratio.</b> If a fund house has not reported it, or reported 0 (a placeholder), the measure is not scored as zero cost. It takes the group value: the lower of the group's median points and 50. The page shows "Filled" with the reason.</li>
          <li><b>A real zero.</b> A month-end fall of exactly 0 over 36 months is not credible for a fund of this kind, so it is treated as missing and shown as a gap. A risk-o-meter level of Low or an exit load of nil are real zeros and are scored.</li>
          <li><b>A loss.</b> A negative 5-year return earns 0 points on the absolute return measure, whatever the peers did.</li>
        </ol>
        <h3 className="mf-h4">One fund, measure by measure</h3>
        <p className="faint">An example fund from our test data, not a real fund: group {walk.group}, {walk.plan} plan, {walk.months} months of NAV history, compared with {walk.peerN} funds. All numbers are the engine's stored output.</p>
        <div className="tw"><table className="mf-cmp"><caption className="sr-only">Worked example, every measure</caption>
          <thead><tr><th scope="col">Measure</th><th scope="col">Part</th><th scope="col" className="num">Value</th><th scope="col" className="num">Peer median</th><th scope="col" className="num">Worst to best</th><th scope="col" className="num">Points</th><th scope="col" className="num">Weight in total</th></tr></thead>
          <tbody>{walk.metrics.map((m) => <tr key={m.label}><th scope="row">{m.label}</th><td>{m.pillar}</td><td className="num">{ex(m.own)}</td><td className="num">{ex(m.peer)}</td><td className="num">{m.limits ? `${m.limits[0]} to ${m.limits[1]}` : "—"}</td><td className="num">{m.points == null ? "—" : Math.round(m.points)}</td><td className="num">{m.weight == null ? "—" : m.weight.toFixed(1) + "%"}</td></tr>)}</tbody></table></div>
        <p>Parts: {PILLARS.map(([k, n]) => `${n} ${(walk.pillars as Record<string, number>)[k]}`).join(", ")}. Each measure's weight in the total is its weight inside its part times the part's weight, so the weights above add to 100%. Total: <b>{walk.final}</b>, label <b>{walk.label}</b>.</p>
      </section>

      <section className="card mf-card"><h2 className="mf-h4">Freshness</h2>
        <p>Scores are worked out every night after the portfolios load and stored once a week for the history chart.{runDate ? ` The latest run was on ${runDate}.` : " The date of the latest run shows here for Gold members once the first run is stored."}</p>
        <p>Gold members can screen every scored fund in the <Link to="/fund-score-screener">Fund score screener</Link>.</p></section>

      <section className="card mf-card" id="faq"><h2 className="mf-h4">Questions</h2>
        {FAQ.map(([q, a]) => <details key={q} className="mfu-faq"><summary>{q}</summary><p>{a}</p></details>)}</section>

      <section className="card mf-card"><h2 className="mf-h4">Labels and colours</h2>
        <p>Labels follow the FinLit scores: {SCORE_BANDS.map(([w, a, b]) => `${w} (${a}${b === 100 ? " to 100" : " to under " + b})`).join(", ")}. Colour is green from 70, orange from 50 and red under 50.</p>
        <p>Not scored in this version: 1 and 6 month returns, daily volatility, exit load of solution-oriented funds (lock-in), fund managers and the five-point checklist. Not available at all: tracking error, index total return, portfolio P/E, credit ratings, yield and duration, portfolio turnover and manager tenure.</p>
      </section>
    </div>
  );
}
