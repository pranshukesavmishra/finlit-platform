// One industry or sector group (/sectors/:slug): where it is in the cycle, a year of breadth, the numbers behind the state, what the 2017-2026 study found after
// washouts, the counted stocks ranked by 6-month return, and the stocks that are not counted. From GET /api/sectors/{slug}; the study figures come from the board.
// The ranked table and the not-counted list are Silver, the peer label column Gold: a locked part says so and why. Describes; never advises.
import { useMemo } from "react";
import { Link, useParams } from "react-router";
import { HScroll } from "../components/HScroll";
import { BreadthChart } from "../components/sectors/BreadthChart";
import { Blank, LockedBlock, SectorFooter, StateChip } from "../components/sectors/Parts";
import { useDocTitle } from "../lib/title";
import { studyCards } from "../lib/sectorStudy";
import {
  QUARTER, averageLabel, count, countedText, dayMonth, failureText, flagAge, flagText, fullDate, level, pct, plural, signedPct, stateClass, useSectorBoard, useSectorPage, type IndustryPage, type MarketNow, type RankedStock,
} from "../lib/sectors";

/** Which of the four cycle stages is the current one (null for Neutral, which is none of them). */
const HERE: Record<string, number | null> = { washout: 0, thrust_c: 1, thrust_cap: 1, confirmed: 2, fading: 3, neutral: null };

function MarketStrip({ m }: { m: MarketNow | null }) {
  if (!m || m.pct_vs_200d == null) return <div className="sx-strip" role="note"><span className="k">The market</span><span>The Nifty 50 reading is not in this data set yet, so the market context is blank.</span></div>;
  const below = m.pct_vs_200d < 0;
  return (
    <div className={"sx-strip" + (below ? "" : " above")} role="note">
      <span className="k">The market</span>
      <span><b>Nifty 50 {level(m.nifty50)}</b>, {Math.abs(m.pct_vs_200d).toFixed(1)}% {below ? "below" : "above"} its {averageLabel(m)} of {level(m.nifty50_200d_average)}</span>
      {m.note && <span className="why">{m.note}</span>}
    </div>
  );
}

/** Sessions from a thrust to the next "turned Fading" event, by the history's own session list. */
export function fadeAfter(p: Pick<IndustryPage, "events" | "history">, thrustDate: string): { date: string; sessions: number } | null {
  const next = p.events.find((e) => e.kind === "turned_fading" && e.date > thrustDate);
  if (!next) return null;
  const d = p.history.dates, a = d.indexOf(thrustDate), z = d.indexOf(next.date);
  return a >= 0 && z >= 0 ? { date: next.date, sessions: z - a } : null;
}

function Happening({ p }: { p: IndustryPage }) {
  const here = HERE[p.state_code] ?? null;
  const cap = p.higher_low_share != null && p.higher_low_share < 20;
  const stages = [
    { k: "washout", name: "1 · Washout", text: "Heavily sold; no broad rebound yet" },
    { k: "thrust", name: `2 · Thrust${p.state_code === "washout" && p.higher_low_share != null ? (cap ? " (CAP if it came now)" : " (C if it came now)") : ""}`, text: "Most stocks rise above their 9-day average within 5 sessions" },
    { k: "confirmed", name: "3 · Confirmed", text: "70%+ of stocks above all three averages" },
    { k: "fading", name: "Fading", text: "The rebound or trend loses its breadth" },
  ];
  return (
    <section className="sx-card sx-happen sx-sec" aria-labelledby="sx-hap">
      <h2 id="sx-hap">What is happening in {p.name}</h2>
      <p>{p.summary}</p>
      <div className="sx-cyc4" role="list" aria-label="Where the industry is in the cycle">
        {stages.map((s, i) => {
          const isHere = here === i;
          const lead = isHere ? `${p.name} is here` : i === 3 ? "If it breaks" : here != null && i === here + 1 ? "Next in the cycle" : here != null && i === here + 2 ? "Then" : "Stage";
          return <div role="listitem" key={s.k} className={isHere ? `here ${stateClass(p.state)}` : ""} aria-current={isHere ? "step" : undefined}><small>{lead}</small><b>{s.name}</b>{s.text}</div>;
        })}
      </div>
      {here == null && <p className="sx-note" style={{ marginTop: 10, marginBottom: 0 }}>{p.name} is in none of these stages today (state: Neutral), so none is marked.</p>}
    </section>
  );
}

function ChartCard({ p }: { p: IndustryPage }) {
  const first = p.history.dates[0], last = p.history.dates[p.history.dates.length - 1];
  const thrusts = p.events.filter((e) => e.kind === "thrust_c" || e.kind === "thrust_cap");
  const fades = thrusts.map((t) => fadeAfter(p, t.date)).filter((x): x is { date: string; sessions: number } => !!x);
  const quick = fades.filter((f) => f.sessions <= 5).length;
  const listed = thrusts.map((t) => `${t.kind === "thrust_cap" ? "CAP" : "C"} on ${dayMonth(t.date)}`).join(", ");
  return (
    <section className="sx-card sx-sec" aria-labelledby="sx-chart">
      <h2 id="sx-chart">Breadth over the past year</h2>
      <p className="sx-sub" style={{ marginBottom: 0 }}>Share of counted {p.name} stocks above their own averages, each session{first && last ? ` from ${fullDate(first)} to ${fullDate(last)}` : ""}.</p>
      <BreadthChart page={p} />
      {(p.history_note || p.averages_note) && <p className="sx-note" data-testid="history-note" style={{ marginTop: 10, marginBottom: 0 }}>{p.history_note}{p.history_note && p.averages_note ? " " : ""}{p.averages_note}</p>}
      <p className="sx-sub" style={{ marginTop: 12, marginBottom: 0 }} data-testid="chart-story">
        {thrusts.length ? `${p.name} had ${thrusts.length === 1 ? "one thrust" : plural(thrusts.length, "thrust")} in the past year: ${listed}.${fades.length ? ` ${quick} of the ${plural(fades.length, "thrust")} that turned Fading did so within 5 sessions.` : ""}` : `${p.name} had no thrust in the past year.`}
        {p.since ? ` Since ${dayMonth(p.since)} the industry has been ${p.state === "Neutral" ? "Neutral" : "in " + (/^[AEIOU]/.test(p.state) ? "an " : "a ") + p.state}.` : ""}
      </p>
    </section>
  );
}

function Numbers({ p }: { p: IndustryPage }) {
  const n = p.stocks_counted;
  const h = p.history, last5 = h.above_50.slice(-5), zero5 = last5.filter((v) => v === 0).length;
  const step = n ? 100 / n : null;
  const low = p.last_60d_low, lt = p.last_thrust;
  const hl = p.higher_low_share, hlN = hl != null && n ? Math.round((hl / 100) * n) : null;
  const fade = lt ? fadeAfter(p, lt.date) : null;
  const flags = p.leader_flags;
  return (
    <section className="sx-sec" aria-labelledby="sx-nums">
      <h2 id="sx-nums" style={{ margin: "0 0 4px", font: "600 20px/1.3 var(--sans)" }}>The numbers behind the state</h2>
      <div className="sx-cards6">
        <div className="sx-kc"><small>Breadth today</small><span className="v">{pct(p.breadth.above_9)} · {pct(p.breadth.above_20)} · {pct(p.breadth.above_50)}</span>
          <p>Share of the {n} counted stocks above their 9, 20 and 50-day averages.{step != null && <> With {n} stocks, one move shifts a reading by about {step.toFixed(step >= 10 ? 0 : 1)} points.</>}</p></div>
        <div className="sx-kc"><small>Lowest 50-day reading, last 30 sessions</small><span className="v">{pct(p.breadth.lowest_50_last_30)}</span>
          <p>Under 40% at any point in 30 sessions is what makes an industry a Washout.{last5.length ? <> {zero5 ? ` On ${zero5} of the last ${last5.length} sessions, no counted stock was above its 50-day average.` : ` On all ${last5.length} of the last ${last5.length} sessions, at least one counted stock was above its 50-day average.`}</> : null}</p></div>
        <div className="sx-kc"><small>{p.name} index vs its 52-week high</small><span className={"v" + ((p.index_vs_52w_high ?? 0) < 0 ? " neg" : "")}>{signedPct(p.index_vs_52w_high, 1)}</span>
          <p>The {n} counted stocks averaged with equal weight. At 15% or more below its high, a 52-week closing high by any of them would set a full leader flag.{flags == null ? " Whether any flag is live is part of the Silver plan." : flags === 0 ? " None has one live." : ` ${plural(flags, "stock")} ${flags === 1 ? "has" : "have"} one live.`}</p></div>
        <div className="sx-kc"><small>Index's last 60-day low</small><span className="v">{low ? `${low.sessions_ago} ${low.sessions_ago === 1 ? "session" : "sessions"} ago` : "—"}</span>
          <p>{low ? `The most recent low of the ${p.name} index over the past 60 sessions, on ${dayMonth(low.date)}.` : "No 60-day low is recorded for this group."}</p></div>
        <div className="sx-kc"><small>Higher-low share at that low</small><span className={"v" + (hl != null && hl < 20 ? " neg" : "")}>{pct(hl)}</span>
          <p>{hl != null && hlN != null ? <>Only {hlN} of the {n} stocks had made their own low at least 10 sessions earlier and stayed 3% or more above it. Under 20% is a capitulation, so a thrust now would count as CAP.</> : (p.higher_low_note ?? "Not available for this group.")}</p></div>
        <div className="sx-kc"><small>Last thrust</small><span className="v">{lt ? `${lt.type} · ${fullDate(lt.date)}` : "None"}</span>
          <p>{lt ? <>{lt.sessions_ago} {lt.sessions_ago === 1 ? "session" : "sessions"} ago.{fade ? ` It turned Fading ${fade.sessions <= 1 ? "the next session" : `after ${fade.sessions} sessions`}, on ${dayMonth(fade.date)}.` : " It has not turned Fading since."}</> : "No thrust in the past year."}</p></div>
      </div>
    </section>
  );
}

function StudyBox({ p }: { p: IndustryPage }) {
  const board = useSectorBoard();
  const cards = useMemo(() => studyCards(board.data?.study?.figures), [board.data]);
  const cap = p.higher_low_share != null && p.higher_low_share < 20;
  const possible = p.state_code === "washout" ? (cap ? "CAP" : "C") : null;
  return (
    <section className="sx-studybox" aria-labelledby="sx-study">
      <h2 id="sx-study">What the 2017–2026 study found after washouts</h2>
      <p className="sx-sub" style={{ marginBottom: 0 }}>NSE industry and sector groups, January 2017 to October 2026, with the stock list rebuilt every month from what was known then, companies later delisted included. "Points" compare the industry's next 60 sessions with its usual 60 sessions. Past averages, not forecasts.</p>
      {cards.length ? (
        <div className="sx-scards">{cards.map((c) => {
          const isNow = (c.key === "C" && possible === "C") || (c.key === "CAP" && possible === "CAP");
          const mk = c.key === "market" && p.market?.above_200d != null;
          return <div key={c.key} className={"sx-sc" + (isNow ? " now" : "")}><h3>{c.title}{c.cases != null ? ` · ${count(c.cases)} cases` : ""}</h3>
            {isNow && <span className="tag">The type possible here now</span>}
            {mk && <span className={"tag" + (p.market!.above_200d ? "" : " warn")}>{p.market!.above_200d ? "Today: Nifty above 200-day" : "Today: Nifty below 200-day"}</span>}
            <p style={{ margin: 0 }}>{c.text}</p></div>;
        })}</div>
      ) : <p className="sx-note" role="status" style={{ margin: "14px 0" }}>{board.isLoading ? "Loading the study figures…" : "The study figures come with the Sector Pulse board, which could not be loaded just now; the notes below are this page's own."}</p>}
      {p.study?.state && <p className="sx-sub" style={{ marginBottom: 8 }}><b>The state itself.</b> {p.study.state}</p>}
      {p.study?.limits && <p className="sx-limits">Limits: {p.study.limits} <Link className="sx-link" to="/learn/sector-signals">How the study works</Link></p>}
    </section>
  );
}

const RET = (v: number | null) => (v == null ? "sx-na" : v > 0 ? "sx-ret pos" : v < 0 ? "sx-ret neg" : "sx-ret");
function RankedTable({ p }: { p: IndustryPage }) {
  const locked = p.locked ?? {};
  const rows = p.stocks;
  const peerLocked = !!locked.peer_label;
  return (
    <section className="sx-sec sx-ranked" aria-labelledby="sx-ranked">
      <h2 id="sx-ranked" style={{ margin: "0 0 4px", font: "600 20px/1.3 var(--sans)" }}>The {p.stocks_counted} counted stocks, ranked by 6-month return</h2>
      <p className="sx-sub" style={{ marginBottom: 12 }}>How each stock has behaved inside its industry.</p>
      {rows == null ? (
        <LockedBlock plan={locked.stocks ?? "silver"} title="The ranked stock table is part of the Silver plan">Open to everyone: the state, the breadth chart and the numbers above. Silver adds each counted stock's 6-month return and quarter in the industry, whether it bottomed before the industry, its leader flag and its size.</LockedBlock>
      ) : !rows.length ? (
        <p className="sx-note" role="status">No stock is ranked: this group has no counted stocks with six months of prices today.</p>
      ) : (
        <>
          <div className="sx-tablebox"><HScroll label="ranked stocks table" className="sx-scroll">
            <table className="sx-t" data-testid="ranked-table">
              <caption className="sx-visually">Counted stocks of {p.name} ranked by 6-month return</caption>
              <thead><tr><th scope="col">Stock</th><th scope="col">#</th><th scope="col">6-month return</th><th scope="col" className="l">Quarter in the industry</th><th scope="col" className="l">Bottomed before the industry</th><th scope="col" className="l">Leader flag</th><th scope="col" className="l">Size (AMFI)</th><th scope="col" className="l">Peer label</th></tr></thead>
              <tbody>{rows.map((s) => <StockRow key={s.symbol} s={s} peerLocked={peerLocked} />)}</tbody>
            </table></HScroll></div>
          <div className="sx-notes">
            <p><b>Quarter in the industry.</b> Where the 6-month return ranks among the counted stocks. {p.study?.quarter}</p>
            <p><b>Bottomed before the industry.</b> The stock made its low 10+ sessions before the industry's low and held 3%+ above it. "Above 20-day avg": it is also above its 20-day average today. {p.study?.bottom}</p>
            <p><b>Size.</b> Large, mid or small cap from AMFI's list for the last half-year: the top 100 companies by average market cap are large caps, the next 150 mid caps, the rest small caps.{peerLocked ? " The peer label (Leader, In line, Laggard) is part of the Gold plan." : " Peer label: the stock's Leader / In line / Laggard label against its peers over 12 months."}</p>
          </div>
          {p.study?.leader_flag && <p className="sx-note" style={{ marginTop: 10 }}><b>Leader flag.</b> {p.study.leader_flag} <em>Past averages, not forecasts.</em></p>}
        </>
      )}
      {p.leader_flag_note && <p className="sx-note" style={{ marginTop: 10 }}>{p.leader_flag_note}</p>}
    </section>
  );
}
function StockRow({ s, peerLocked }: { s: RankedStock; peerLocked: boolean }) {
  return (
    <tr>
      <td><div className="sx-name"><Link to={`/stocks/${s.symbol}`}>{s.symbol}</Link><small>{s.name}</small></div></td>
      <td>{s.rank_6m ?? "—"}</td>
      <td className={RET(s.return_6m_pct)}>{signedPct(s.return_6m_pct, 1)}</td>
      <td className="l">{s.quarter_name ?? (s.quarter ? QUARTER[s.quarter] : <span className="sx-na">Not ranked</span>)}</td>
      <td className="l">{s.bottom_code === 1 ? "Yes, above its 20-day avg" : s.bottom_code === 2 ? "Yes" : s.bottom_code === 3 ? "No" : <span className="sx-na">No recent low to compare</span>}</td>
      <td className="l">{s.leader_flag ? <span className="sx-chip info">{flagText(s.leader_flag)} · {flagAge(s.leader_flag.sessions_ago)}</span> : <span className="sx-na">None</span>}</td>
      <td className="l">{s.amfi_category ?? <span className="sx-na">Not in AMFI's list</span>}</td>
      <td className="l">{peerLocked ? <span className="sx-na" title="The peer label is part of the Gold plan">Gold</span> : s.peer_label ?? <span className="sx-na" title="No peer label: too few peers or too little history">No label</span>}</td>
    </tr>
  );
}

function NotCounted({ p }: { p: IndustryPage }) {
  const locked = p.locked ?? {};
  const list = p.not_counted;
  if (list == null) {
    return <section className="sx-card sx-sec"><h2>Not counted</h2><LockedBlock plan={locked.not_counted ?? "silver"} title="The list of stocks that are not counted is part of the Silver plan">It names each stock of this industry that is left out of the breadth readings and the reasons, one by one.</LockedBlock></section>;
  }
  return (
    <section className="sx-card sx-sec" aria-labelledby="sx-nc">
      <h2 id="sx-nc">Not counted: {list.length} {p.name} {list.length === 1 ? "stock" : "stocks"}</h2>
      <p className="sx-sub">{list.length ? "These stocks traded on NSE but miss one or more of the rules, so they are left out of the breadth readings and the industry index. They are checked again at the next monthly review, on the first trading day of the month." : "Every listed stock of this industry that traded on the last session is counted."} <Link className="sx-link" to="/sectors#sx-counted">How stocks are chosen</Link></p>
      {list.length > 0 && <div className="sx-nclist">{list.map((s) => (
        <div className="sx-nc" key={s.symbol}><div className="nm"><b><Link to={`/stocks/${s.symbol}`} style={{ color: "inherit", textDecoration: "none" }}>{s.symbol}</Link></b><small>{s.name}</small></div>
          <div className="rs">{s.not_counted_because.length ? s.not_counted_because.map((r) => <span className="sx-pill reason" key={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</span>) : <span className="sx-pill reason">No rule is missed; it joins at the next monthly review</span>}</div></div>
      ))}</div>}
    </section>
  );
}

export function SectorIndustryPage() {
  const { slug = "" } = useParams();
  const q = useSectorPage(slug);
  const p = q.data;
  useDocTitle(p ? `${p.name}: sector breadth` : "Sector breadth", p ? `${p.name} on NSE: where its stocks stand against their 9, 20 and 50-day averages, its state in the cycle and what the 2017–2026 study found.` : undefined);
  const notCountedN = p?.not_counted?.length;
  return (
    <div className="wrap sx" data-testid="sector-industry">
      <p className="sx-back"><Link to="/sectors">Sector Pulse</Link> / {p?.name ?? slug}</p>
      {q.isLoading && <div className="sx-skel" role="status" aria-label="Loading the industry" />}
      {q.isError && <Blank title={q.error?.status === 404 ? "No such industry" : "This industry is not available right now"} reason={failureText(q.error)}><Link className="btn" to="/sectors">Back to Sector Pulse</Link></Blank>}
      {p && (
        <>
          <div className="sx-title"><h1>{p.name}</h1><StateChip state={p.state} big extra={p.since ? `since ${dayMonth(p.since)}` : undefined} /></div>
          <p className="sx-meta">{p.kind === "sector" ? `NSE sector group of ${p.industries.length} small industries (${p.industries.join(", ")}) in the ${p.sector} sector` : `NSE industry in the ${p.sector} sector`} · {countedText(p)}{notCountedN != null ? `, ${notCountedN} not counted` : `, ${Math.max(0, p.stocks_listed - p.stocks_counted)} listed stocks not counted`} · data as of {fullDate(p.date)}</p>
          <MarketStrip m={p.market} />
          <Happening p={p} />
          <ChartCard p={p} />
          <Numbers p={p} />
          <StudyBox p={p} />
          <RankedTable p={p} />
          <NotCounted p={p} />
          <p className="sx-note" style={{ marginTop: 14 }}>{p.universe_rules}</p>
          <SectorFooter disclaimer={p.disclaimer} />
        </>
      )}
    </div>
  );
}
