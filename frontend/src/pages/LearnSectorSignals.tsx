// Learn: how to read sector signals (/learn/sector-signals). The text is the design's; the figures that change (stocks counted, groups, the study table) come from the same
// Sector Pulse board the other pages use, and are left out with their reason when that is not available. The worked example is a dated illustration, labelled as one.
import { useRef, useState } from "react";
import { Link } from "react-router";
import { useDocTitle } from "../lib/title";
import { mainFinding, studyRows } from "../lib/sectorStudy";
import { count, failureText, fullDate, mergedReasons, useSectorBoard, type Board, type StudyFigures } from "../lib/sectors";
import { StateChip } from "../components/sectors/Parts";
import { HScroll } from "../components/HScroll";
import { MINUS } from "../lib/format";
import "../styles/sectors.css";

const DESC = "How FinLit reads breadth by NSE industry: Washout, Thrust, Confirmed and Fading, which stocks are counted and why, and what the 2017–2026 study found. Information, not advice.";
const pts = (v: number | null | undefined) => (v == null ? "—" : (v > 0 ? "+" : v < 0 ? MINUS : "") + Math.abs(v).toFixed(1));

const STEPS = [
  ["Measure breadth", "For each NSE industry, the share of its counted stocks above their 9, 20 and 50-day averages: the short, medium and longer trend."],
  ["Place it in the cycle", "Washout, then a broad rebound (Thrust), then an established trend (Confirmed), or Fading when breadth breaks. Read it next to the market: is the Nifty 50 above or below its 200-day average?"],
  ["Look inside the industry", "Which stocks held up or turned first: leader flags, 6-month quarter, bottom timing and the peer label."],
  ["Then the stock itself", "Its own chart trend (the short and long-term scores) and its business (the FinLit health score). Breadth says nothing about either."],
];
const RULES: [string, string, string][] = [
  ["Series", "NSE's normal EQ series", "Trade-for-trade (BE) and suspended stocks settle differently and often trade in bursts."],
  ["Traded value", "Median Rs 2 crore a day or more over 65 sessions; members stay down to Rs 1 crore", "Below this, a few trades decide the close."],
  ["Trading days", "Traded on at least 62 of the last 65 sessions", "Gaps freeze a stock's averages and make it look calmer than it is. A member that goes 5 sessions without a trade is dropped at once."],
  ["Price bands", "Stuck at a band (high = low) on no more than 1 of those 65 sessions", "A stock locked at its upper or lower circuit has no real price that day."],
  ["Price", "Rs 20 or more", "Very low prices move in large percentage steps of a few paise."],
  ["Market cap", "AMFI six-month average of Rs 1,000 crore or more; members stay down to Rs 800 crore", "Very small companies move on news of their own more than with their industry."],
  ["Seasoning", "Listed for at least 6 months (126 sessions)", "New listings swing on allotment and lock-in dates, and need history for a 50-day average and a 6-month return."],
];
const CUTOFFS: [string, string][] = [
  ["How the cut-offs were set", "Before any returns were looked at, each level was checked against signs of noise: how often a price stood still, how often it moved 10% or more in a day, how often it crossed its 9-day average back and forth, and how closely it moved with its industry. The cut-offs are where those signs settled down."],
  ["Reviewed monthly, without hindsight", "The list is rebuilt on the first trading day of each month from what was known then. Between reviews, a stock is dropped at once if it goes 5 sessions without a trade. In past years the rupee floors are scaled down with the market's total turnover and market cap, so the same rules mean the same thing in 2017 and 2026."],
  ["A wider band to stay than to join", "A stock joins at Rs 2 crore a day and Rs 1,000 crore of market cap but stays until it falls below Rs 1 crore and Rs 800 crore. This stops stocks near the line from flipping in and out every month."],
];
const CANNOT = [
  "What will happen next. Every figure on these pages describes the past.",
  "Whether a business is sound or fairly priced. Breadth only counts price trends.",
  "Whether a thrust will last. A thrust often fades: the industry pages list every thrust of the past year and when it turned Fading.",
  "Anything about stocks that are not counted. Their prices are shown, but they are left out of every breadth reading and industry index.",
  "Anything precise about small groups. With 10 stocks, one stock moves breadth by 10 points; that is why small industries are read with their sector.",
];
const LIMITS = [
  "Industries often signal in the same weeks, so the cases are not independent; averaged week by week the edge of a thrust was about zero.",
  "The market-context split was examined after seeing the results, and rests on a small number of separate weeks.",
  "The 15% leader-flag cut-off and the 20% capitulation cut-off come from an earlier study.",
  "Each company's NSE industry is today's label, even for earlier years.",
  "Returns ignore costs and taxes. Expect live results to be weaker than the tested ones.",
];

type Entry = { term: string; chip?: string; text: string; study?: string };
function glossary(f: StudyFigures | undefined): Record<string, Entry[]> {
  const C = f?.C, CAP = f?.CAP, cf = f?.Confirmed, fd = f?.Fading, share = f?.state_share_pct?.["0"];
  const bel = f?.C_below_200d, abv = f?.C_above_200d, pbl = f?.CAP_below_200d, pab = f?.CAP_above_200d;
  return {
    "Sector states": [
      { term: "Washout", chip: "washout", text: "The industry was sold broadly: at some point in the last 30 sessions, fewer than 40% of its counted stocks were above their 50-day average.", study: share != null ? `Every thrust came out of a washout, but industries spent ${Math.round(share)}% of all days in Washout and many washouts lasted weeks. On its own it says nothing about timing.` : undefined },
      { term: "Thrust C", chip: "thrust_c", text: "A broad rebound after a washout: the share of stocks above their 9-day average jumps from 20% or less to 80% or more within 5 sessions. It opens a 20-session thrust window.",
        study: C ? `${count(C.cases)} cases; ${Math.round(C.win_pct)}% rose 15% before falling 8%; ${pts(C.edge_pts)} points over 60 sessions${f?.C_week_avg ? `, ${pts(f.C_week_avg.edge_pts)} averaged week by week` : ""}.${bel && abv ? ` ${pts(bel.edge_pts)} points with the Nifty 50 below its 200-day average, ${pts(abv.edge_pts)} above it.` : ""}` : undefined },
      { term: "Thrust CAP", chip: "thrust_cap", text: "A thrust that comes after a capitulation: when the industry made its last low, fewer than 20% of its stocks were holding a higher low. A thrust also counts here when the share above the 20-day average jumps from 30% or less to 70% or more within 10 sessions.",
        study: CAP ? `${count(CAP.cases)} cases; ${Math.round(CAP.win_pct)}% rose 15% first; ${pts(CAP.edge_pts)} points (${pts(CAP.edge_ex2020_pts)} without 2020).${pbl && pab ? ` ${pts(pbl.edge_pts)} points with the Nifty 50 below its 200-day average, ${pts(pab.edge_pts)} above it.` : ""}` : undefined },
      { term: "Confirmed", chip: "confirmed", text: "70% or more of the industry's counted stocks are above all three averages (9, 20 and 50-day). Most stocks are trending up together.", study: cf ? `${count(cf.cases)} cases${cf.median_sessions_after_low != null ? `, a median ${cf.median_sessions_after_low} sessions after the low` : ""}; ${pts(cf.edge_pts)} points, close to an ordinary period.` : undefined },
      { term: "Fading", chip: "fading", text: "A thrust failed (within 20 sessions the share above the 20-day average fell under 30% and above the 9-day under 50%), or breadth broke after Confirmed (the share above the 50-day average fell under 50% within 60 sessions). Lasts 20 sessions or until a new thrust.", study: fd ? `${count(fd.cases)} cases; ${pts(fd.edge_pts)} points, no different from an ordinary period.` : undefined },
      { term: "Neutral", chip: "neutral", text: "None of the states above." },
      { term: "Thrust window", text: "The 20 sessions after a C or CAP thrust. The industry page marks it with a dotted shade on the chart.", study: "The 20-session length is a design choice, not a tested result." },
    ],
    "Industry numbers": [
      { term: "Breadth: 9, 20 and 50-day", text: "The share of an industry's counted stocks whose price is above their own 9-day, 20-day and 50-day average. The 9-day bar moves first and fastest; the 50-day bar is the slowest and shows whether a trend is established." },
      { term: "Index vs 52-week high", text: "The counted stocks of the industry averaged with equal weight, compared with the highest level that average reached in the last 52 weeks. A figure of −15% means the average stock is 15% below that high." },
      { term: "Higher-low share", text: "At the industry's last 60-day low, the share of counted stocks that had made their own low at least 10 sessions earlier and stayed 3% or more above it. Under 20%, shown in red, is a capitulation: almost every stock was still making new lows." },
      { term: "Last 60-day low", text: "How many sessions ago the equal-weighted industry index made its lowest close of the past 60 sessions." },
      { term: "Stocks counted", text: "The stocks of the industry that pass the counting rules on the last session. Stocks listed but not counted are named, with the reasons, on each industry page (Silver)." },
    ],
    "A stock in its industry": [
      { term: "6-month quarter", text: "Where the stock's 6-month return ranks among the counted stocks of its industry: top quarter, 2nd, 3rd or bottom quarter.", study: f?.quarters_C?.["1"] && f?.quarters_C?.["4"] ? `At a C thrust, the top quarter did ${pts(f.quarters_C["1"].mean_pts)} points against its industry over 60 sessions and the bottom quarter ${pts(f.quarters_C["4"].mean_pts)} points; the median stock in every quarter trailed the industry index.` : undefined },
      { term: "Bottomed before the industry", text: "The stock made its low at least 10 sessions before the industry's low and held 3% or more above it. 'Above its 20-day average' adds that it is also above that average today.", study: f?.bottom_any?.["1"] ? `No meaningful difference: ${pts(f.bottom_any["1"].mean_pts)} points for stocks that bottomed first and were above their 20-day average; ${pts(f.bottom_any["3"]?.mean_pts)} to ${pts(f.bottom_any["2"]?.mean_pts)} for the others.` : undefined },
      { term: "Leader flag", text: "A stock closes at a 52-week high while its industry index is 10% or more below its own high (15% or more is the full flag). The flag stays live for 60 sessions after the last such high.", study: f?.flags_tier2 ? `Full flags: ${count(f.flags_tier2.cases)} cases, ${pts(f.flags_tier2.mean_pct)}% against the industry over the next 120 sessions on average (median ${pts(f.flags_tier2.median_pct)}%; ${Math.round(f.flags_tier2.beat_pct)}% beat it). The softer 10–15% tier showed no difference.` : undefined },
      { term: "Size (AMFI)", text: "Large, mid or small cap from AMFI's list for the last half-year: the top 100 companies by average market cap are large caps, the next 150 mid caps, the rest small caps." },
    ],
    "Peers table": [
      { term: "Peer label", text: "Leader, In line or Laggard: how the stock's last 12 months compare with its closest peers, against the peer group's own sector index. It describes past relative performance only." },
      { term: "Rank among peers", text: "Where the stock stands among the ranked peers of its group by 12-month points against the sector benchmark. Peers with too little history or too thin trading are listed as not ranked, with the reason." },
      { term: "vs sector and vs market", text: "The stock's return minus the return of its sector index (or the peer average when no index exists) and of the market index, in percentage points, over 3 and 12 months." },
      { term: "Peers are not always the NSE industry", text: "The peer card uses its own peer lists, so a steel-tube maker can be compared with steel makers while NSE files it under Industrial Products. The two cards can name different groups." },
    ],
  };
}

function Glossary({ f }: { f: StudyFigures | undefined }) {
  const g = glossary(f), tabs = Object.keys(g);
  const [tab, setTab] = useState(tabs[0]);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const onKey = (e: React.KeyboardEvent, i: number) => {
    const to = e.key === "ArrowRight" ? (i + 1) % tabs.length : e.key === "ArrowLeft" ? (i + tabs.length - 1) % tabs.length : e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : -1;
    if (to < 0) return;
    e.preventDefault(); setTab(tabs[to]); refs.current[to]?.focus();
  };
  return (
    <>
      <div className="sx-glossary-tabs" role="tablist" aria-label="Glossary groups">
        {tabs.map((t, i) => <button key={t} ref={(el) => { refs.current[i] = el; }} type="button" role="tab" id={`gl-t-${i}`} aria-selected={tab === t} aria-controls="gl-panel" tabIndex={tab === t ? 0 : -1} className="sx-fbtn" aria-pressed={undefined} style={tab === t ? { background: "var(--text)", color: "var(--bg)", borderColor: "var(--text)" } : undefined} onClick={() => setTab(t)} onKeyDown={(e) => onKey(e, i)}>{t}</button>)}
      </div>
      <div className="sx-gl" role="tabpanel" id="gl-panel" aria-labelledby={`gl-t-${tabs.indexOf(tab)}`}>
        {g[tab].map((e) => (
          <div className="row" key={e.term}>
            <div className="term"><b>{e.term}</b>{e.chip && <StateChip state={e.chip === "thrust_c" ? "Thrust C" : e.chip === "thrust_cap" ? "Thrust CAP" : e.chip[0].toUpperCase() + e.chip.slice(1)} />}</div>
            <div><p>{e.text}</p>{e.study && <div className="st"><b>Study:</b> {e.study} <em>Past averages, not forecasts.</em></div>}</div>
          </div>
        ))}
      </div>
    </>
  );
}

function Counted({ b }: { b: Board | undefined }) {
  const u = b?.universe;
  const traded = u ? mergedReasons(u.reasons).find((r) => r.reason.startsWith("median traded value"))?.stocks : null;
  return (
    <>
      <h2>Which stocks are counted, and why</h2>
      <p className="sx-sub">A stock that trades a few lakh rupees a day, sits at a price band or has just listed can jump or stand still for reasons that have nothing to do with its industry. Counting it would add noise to the breadth readings, so only liquid, established stocks are counted.{u ? ` On ${fullDate(u.date)} that was ${count(u.meet_rules)} of the ${count(u.stocks_with_industry_traded)} NSE stocks with an industry.` : ""}</p>
      <div className="sx-tablebox"><HScroll label="counting rules" className="sx-scroll"><table className="sx-t" style={{ minWidth: 640 }}>
        <thead><tr><th scope="col">Rule</th><th scope="col" className="l">To be counted</th><th scope="col" className="l">Why</th></tr></thead>
        <tbody>{RULES.map(([r, t, w]) => <tr key={r}><td style={{ fontWeight: 700 }}>{r}</td><td className="l" style={{ whiteSpace: "normal" }}>{t}</td><td className="l" style={{ whiteSpace: "normal", minWidth: 240 }}>{w}{r === "Traded value" && traded != null ? ` ${count(traded)} stocks on ${fullDate(u!.date).replace(/ \d{4}$/, "")} fell short.` : ""}</td></tr>)}</tbody>
      </table></HScroll></div>
      <div className="sx-three">{CUTOFFS.map(([h, t]) => <div className="sx-card" key={h}><h3>{h}</h3><p>{t}</p></div>)}</div>
    </>
  );
}

export function LearnSectorSignalsPage() {
  useDocTitle("How to read sector signals", DESC);
  const q = useSectorBoard();
  const b = q.data, f = b?.study?.figures;
  const rows = studyRows(f), finding = mainFinding(f);
  return (
    <div className="wrap sx" data-testid="learn-sector-signals"><div className="sx-learn">
      <p className="sx-eyebrow">Learn · Sector signals</p>
      <h1>How to read sector signals</h1>
      <p className="lead">Stocks in the same industry tend to move together. When a sell-off ends, an early sign is often not the price of one stock but how many stocks in the industry start rising at the same time. That share is called <b>breadth</b>. Every evening FinLit measures it for each NSE industry with enough liquid stocks, and describes where each one stands.</p>

      <h2>The idea in four steps</h2>
      <div className="sx-four">{STEPS.map(([h, t], i) => <div className="sx-card" key={h}><div className="n">{i + 1}</div><h3>{h}</h3><p>{t}</p></div>)}</div>

      <Counted b={b} />

      <h2>Industries are NSE's</h2>
      <section className="sx-card" style={{ marginTop: 10 }}>
        <p className="sx-sub">NSE classifies every listed company in four levels: macro-economic sector, sector, industry and basic industry. FinLit uses the industry level, the one shown on each NSE quote page. An industry with fewer than 10 counted stocks is read together with the other small industries of its NSE sector, as a <b>sector group</b>. A group needs at least 8 counted stocks for a reading.</p>
        {b ? <div className="sx-ustats" style={{ gridTemplateColumns: "repeat(4, minmax(0, 1fr))" }}>
          <div className="sx-num"><small>Groups</small><b>{count(b.groups + (b.too_few_stocks?.length ?? 0))}</b></div><div className="sx-num"><small>With a reading today</small><b>{count(b.groups)}</b></div>
          <div className="sx-num"><small>Of those, single industries</small><b>{count(b.industries)}</b></div><div className="sx-num"><small>Stocks counted in them</small><b>{count(b.stocks_counted)}</b></div></div>
          : <p className="sx-note" role="status">{q.isLoading ? "Loading the live counts…" : `The live group counts are not shown because ${failureText(q.error).replace(/^Sector data is not loaded yet: /, "the sector data is not loaded yet: ")}`}</p>}
        <p className="sx-note">Example: Metals &amp; Mining is a sector group of several small industries (Diversified Metals, Metals &amp; Minerals Trading, Minerals &amp; Mining and Non-Ferrous Metals), while Ferrous Metals is read on its own once it has enough counted stocks. NSE files a company by what it makes: Sambhv Steel Tubes is in Industrial Products, not Ferrous Metals.</p>
      </section>

      <h2>A worked example: Ferrous Metals and SAMBHV</h2>
      <section className="sx-card" style={{ marginTop: 10 }}>
        <p className="sx-note" style={{ marginTop: 0 }}>A fixed illustration, as of 29 Oct 2026. The pages linked below show today's figures.</p>
        <p>In late October 2026 Ferrous Metals was in a <b>Washout</b>: on some days in the last 30 sessions, none of its 14 counted stocks was above its 50-day average, and its index was 16.9% below its high. Only 2 of the 14 had held a higher low, so a thrust would have counted as CAP. In the year before it had four thrusts, and every one faded, which shows that a thrust is no guarantee. The market around it was weak too: the Nifty 50 was 4.1% below its 200-day average.</p>
        <p>SAMBHV, a steel-tube maker, sits in NSE's <b>Industrial Products</b> industry, also in a Washout. Inside it, SAMBHV ranked 20th of 105 by 6-month return (top quarter) and had made its low before the industry did. Against its steel peers it was a Leader. So the stock was strong while its industry was weak. The pages describe that contrast; they do not say what to do about it.</p>
        <p style={{ display: "flex", gap: 20, flexWrap: "wrap", marginBottom: 0 }}><Link className="sx-link" to="/sectors/ferrous-metals">Open the Ferrous Metals page</Link><Link className="sx-link" to="/stocks/SAMBHV#sector">Open SAMBHV's sector card</Link></p>
      </section>

      <h2>What the 2017–2026 study found</h2>
      <p className="sx-sub">NSE daily data from January 2016, with cases from January 2017 to October 2026 across NSE industry and sector groups. The stock list was rebuilt every month from what was known then, companies later delisted included. "Points" compare a return with the industry's usual return over the same number of sessions. <b>These are past averages, not forecasts.</b></p>
      {rows.length ? <div className="sx-tablebox"><HScroll label="study results" className="sx-scroll"><table className="sx-t" style={{ minWidth: 640 }} data-testid="study-table">
        <thead><tr><th scope="col">Signal</th><th scope="col">Cases</th><th scope="col" className="l">What happened next</th></tr></thead>
        <tbody>{rows.map((r) => <tr key={r.signal}><td style={{ fontWeight: 700 }}>{r.signal}</td><td>{r.cases == null ? "—" : count(r.cases)}</td><td className="l" style={{ whiteSpace: "normal", minWidth: 280 }}>{r.text}</td></tr>)}</tbody></table></HScroll></div>
        : <p className="sx-note" role="status">{q.isLoading ? "Loading the study figures…" : `The study table is filled from the Sector Pulse data, which is not available just now. ${failureText(q.error)}`}</p>}
      {finding && <div className="sx-finding"><b>The main finding: the market mattered more than the thrust</b>{finding}</div>}
      <div className="sx-limbox"><h3>Limits of the study</h3><ul>{LIMITS.map((l) => <li key={l}>{l}</li>)}</ul></div>

      <h2>Glossary</h2>
      <p className="sx-sub">Every term on the sector, industry and peer pages, in plain words.</p>
      <Glossary f={f} />

      <h2>What these signals cannot tell you</h2>
      <section className="sx-card" style={{ marginTop: 10 }}><ul className="sx-cannot">{CANNOT.map((c) => <li key={c}>{c}</li>)}</ul></section>
      <footer className="sx-footer"><p>Educational content. FinLit's sector and peer pages describe price data; they are not recommendations to buy, sell or hold any security, and past results do not predict future returns. Sources: NSE daily files and industry classification, AMFI market-cap lists.</p>
        <p><Link className="sx-link" to="/sectors">Sector Pulse</Link></p></footer>
    </div></div>
  );
}
