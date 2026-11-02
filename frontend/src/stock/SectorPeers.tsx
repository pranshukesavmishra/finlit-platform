// "Sector & peers" on the stock page: where the company's NSE industry is in its cycle (card 1), how the stock ranks inside that industry (card 2), how it compares with its
// closest peers (card 3, the Leader / In line / Laggard label already on the page), what its own chart says (card 4, the technical readings already on the page) and the
// business behind it (card 5, the FinLit score). Cards 1 and 2 come from GET /api/technicals/{symbol}/sector, a Gold feature: below Gold the section shows the industry's state (which
// every plan sees on Sector Pulse) and says what Gold adds. Describes price and breadth data; never advice.
import { Link } from "react-router";
import { SectionHead } from "./Sections";
import { LeadChip } from "./Leadership";
import { LockedBlock, StateChip } from "../components/sectors/Parts";
import { useLeadership, pts as ptsFrac } from "../lib/leadership";
import type { Summary, Technical } from "../lib/api";
import { count, failureText, fullDate, ordinal, pct, signedPct, useStockSector, type StockSector } from "../lib/sectors";
import "../styles/sectors.css";

const NOTE = "This section describes price, breadth and peer data. It is not a recommendation to buy, sell or hold any security. Study results are past averages and do not predict future returns.";
const an = (w: string) => (/^[AEIOU]/i.test(w) ? "an" : "a");
const QUARTER_WORD: Record<number, string> = { 1: "top quarter", 2: "2nd quarter", 3: "3rd quarter", 4: "bottom quarter" };

/** The line at the top: what the stock is doing inside its industry, and what the industry and the market are doing. */
export function oneLine(symbol: string, s: StockSector): string | null {
  const g = s.group;
  if (!g) return null;
  const inside = s.rank_6m != null && s.quarter ? `${symbol} is in the ${QUARTER_WORD[s.quarter] ?? s.quarter_name?.toLowerCase()} of ${g.name} stocks over 6 months (${signedPct(s.return_6m_pct, 1)})` : `${symbol} has no 6-month ranking inside ${g.name} today`;
  const mk = s.market?.above_200d;
  return `${inside}, and the industry as a whole is in ${an(g.state)} ${g.state}${mk == null ? "" : ` while the Nifty 50 is ${mk ? "above" : "below"} its 200-day average`}.`;
}
const bottomWord = (code: number | null | undefined) => (code === 1 ? "Yes, and it is above its 20-day average" : code === 2 ? "Yes" : code === 3 ? "No" : null);

function Cards({ symbol, name, s, tech, score, jump }: { symbol: string; name: string; s: StockSector; tech?: Technical; score?: Summary["score"]; jump?: (id: string) => void }) {
  const g = s.group, lead = useLeadership(symbol).data;
  const l = lead && lead.available ? lead : null;
  const counted = s.in_group !== false && g;
  const rel = l?.rel;
  return (
    <>
      <div className="sx-cards5">
        <article className="sx-c5" aria-labelledby={`sxc1-${symbol}`}>
          <header><h3 id={`sxc1-${symbol}`}>1 · Where is its industry in the cycle?</h3>{g && <StateChip state={g.state} />}</header>
          {g ? <>
            <p>{g.summary ?? `${g.name} is in ${an(g.state)} ${g.state}: ${g.meaning.toLowerCase()}.`}</p>
            <div className="sx-mini2">
              <div><small>Higher-low share</small><b className={g.higher_low_share != null && g.higher_low_share < 20 ? "sx-low" : ""}>{pct(g.higher_low_share)}</b></div>
              <div><small>Index's last 60-day low</small><b>{g.last_60d_low ? `${g.last_60d_low.sessions_ago} ${g.last_60d_low.sessions_ago === 1 ? "session" : "sessions"} ago` : "—"}</b></div>
              <div><small>Stocks counted</small><b>{count(g.stocks_counted)} of {count(g.stocks_listed)}</b></div>
              <div><small>Nifty 50 vs 200-day avg</small><b className={s.market?.pct_vs_200d != null && s.market.pct_vs_200d < 0 ? "sx-low" : ""}>{signedPct(s.market?.pct_vs_200d ?? null, 1)}</b></div>
            </div>
            <Link className="more" to={`/sectors/${g.slug}`}>Open the {g.name} page</Link>
          </> : <p>Industry not yet classified. NSE has not given this stock an industry, so there is no industry reading to show. It is picked up at a later run once NSE lists it.</p>}
        </article>
        <article className="sx-c5" aria-labelledby={`sxc2-${symbol}`}>
          <header><h3 id={`sxc2-${symbol}`}>2 · How has it done inside {g?.name ?? "its industry"}?</h3>{counted && s.quarter_name && <span className="sx-chip plain">{s.quarter_name}</span>}</header>
          {!counted ? <>
            <p>{s.note ?? "This stock is not counted in its industry's breadth, so it has no rank inside it."}</p>
            {s.not_counted_because?.length ? <div className="sx-chips" style={{ marginTop: 0 }}>{s.not_counted_because.map((r) => <span className="sx-pill reason" key={r}>{r.charAt(0).toUpperCase() + r.slice(1)}</span>)}</div> : null}
          </> : <>
            <p>{s.rank_6m != null ? `${ordinal(s.rank_6m)} of ${count(s.ranked_6m)} counted ${g!.name} stocks by 6-month return.` : `Not ranked: the stock has too little price history for a 6-month return.`}{s.bottom ? ` ${s.bottom}.` : ""}</p>
            <div className="sx-mini2">
              <div><small>6-month return</small><b className={(s.return_6m_pct ?? 0) < 0 ? "sx-low" : s.return_6m_pct != null ? "sx-ret pos" : ""}>{signedPct(s.return_6m_pct ?? null, 1)}</b></div>
              <div><small>Bottomed before the industry</small><b>{bottomWord(s.bottom_code) ?? "No recent low to compare"}</b></div>
            </div>
            {s.leader_flag_text && <p className="m">{s.leader_flag_text}</p>}
          </>}
        </article>
        <article className="sx-c5" aria-labelledby={`sxc3-${symbol}`}>
          <header><h3 id={`sxc3-${symbol}`}>3 · How does it compare with its peers?</h3>{l && <LeadChip label={l.label} />}</header>
          {l ? <>
            <p>{l.display.line}{l.display.note ? `. ${l.display.note}` : ""}.</p>
            <div className="sx-mini2">
              <div><small>vs {l.benchmarks.sector.name}, 12M</small><b>{rel?.w52 != null ? `${ptsFrac(rel.w52)} pts` : "—"}</b></div>
              <div><small>vs {l.benchmarks.sector.name}, 3M</small><b>{rel?.w13 != null ? `${ptsFrac(rel.w13)} pts` : "—"}</b></div>
              {l.benchmarks.market && <div><small>vs {l.benchmarks.market.name}, 12M</small><b>{rel?.w52Market != null ? `${ptsFrac(rel.w52Market)} pts` : "—"}</b></div>}
              {l.labelSince && <div><small>Label since</small><b>{fullDate(l.labelSince)}</b></div>}
            </div>
            <button type="button" className="more" onClick={() => jump?.("leadership")}>See all {l.peerGroup.ranked} peers</button>
          </> : <p>{lead && !lead.available ? lead.display?.line ?? "No peer label for this stock yet." : "The peer label is loading, or this stock has none yet."}</p>}
          <p className="m">The peer card uses its own peer list (steel makers for a steel stock), so it can name a different group from the NSE industry in card 1.</p>
        </article>
        <article className="sx-c5" aria-labelledby={`sxc4-${symbol}`}>
          <header><h3 id={`sxc4-${symbol}`}>4 · What does its own chart say?</h3></header>
          {tech ? <>
            <p>The price is {tech.vsEma50Pct == null ? "—" : `${pct(Math.abs(tech.vsEma50Pct), 1)} ${tech.vsEma50Pct >= 0 ? "above" : "below"}`} its 50-day average and {tech.vsEma200Pct == null ? "—" : `${pct(Math.abs(tech.vsEma200Pct), 1)} ${tech.vsEma200Pct >= 0 ? "above" : "below"}`} its 200-day average.</p>
            <div className="sx-mini2"><div><small>vs 50-day average</small><b>{signedPct(tech.vsEma50Pct, 1)}</b></div><div><small>vs 200-day average</small><b>{signedPct(tech.vsEma200Pct, 1)}</b></div>
              <div><small>RSI (14)</small><b>{tech.rsi14 == null ? "—" : tech.rsi14.toFixed(0)}</b></div><div><small>RSI zone</small><b>{tech.rsiZone ?? "—"}</b></div></div>
          </> : <p>The stock's own technical readings are loading, or are not available for it yet.</p>}
          <button type="button" className="more" onClick={() => jump?.("price")}>See the price chart and technical levels</button>
        </article>
        <article className="sx-c5" aria-labelledby={`sxc5-${symbol}`}>
          <header><h3 id={`sxc5-${symbol}`}>5 · Is the business sound?</h3></header>
          <p>Price strength says nothing about the balance sheet. A stock rising out of a weak industry can still carry debt, pledged shares or weak cash flow.</p>
          <div className="sx-mini2"><div><small>FinLit score</small><b>{score?.overall ?? "—"}</b></div><div><small>Band</small><b>{score?.overall == null ? "Not scored yet" : score?.band?.label ?? "—"}</b></div></div>
          <button type="button" className="more" onClick={() => jump?.("notes")}>Open the health score</button>
        </article>
        <aside className="sx-c5 study" aria-labelledby={`sxs-${symbol}`}>
          <h3 id={`sxs-${symbol}`}>What the 2017–2026 study found in situations like this</h3>
          {s.study ? <ul>{s.study.quarter && <li>{s.study.quarter}</li>}{s.study.bottom && <li>{s.study.bottom}</li>}{s.study.leader_flag && <li>{s.study.leader_flag}</li>}</ul> : <p className="m">The study notes are part of the same data set and are not in this answer.</p>}
          <p className="m">Past averages with wide spreads across NSE groups, not a forecast for {name || symbol}.</p>
        </aside>
      </div>
      <div className="sx-help"><details><summary>How to read these five cards together</summary>
        <p>The cards go from the widest view to the narrowest. Card 1 describes the whole industry and the market around it: is buying spreading or drying up? Cards 2 and 3 describe how this stock has behaved compared with the rest of its industry and with its closest peers. Card 4 describes the stock's own trend, and card 5 the business behind it.</p>
        <p>The industry is NSE's: it files each company by what it makes, which can differ from the peer list of card 3. When the cards agree, the picture is consistent. When they disagree, the cards show where the tension is. None of them is a forecast, and none of them is a recommendation to buy, sell or hold.</p>
        <p><Link className="sx-link" to="/learn/sector-signals">Learn what each term means</Link></p></details></div>
    </>
  );
}

export function SectorPeersSection({ symbol, name, tech, score, jump }: { symbol: string; name: string; tech?: Technical; score?: Summary["score"]; jump?: (id: string) => void }) {
  const q = useStockSector(symbol);
  const s = q.data;
  const locked = !!s?.locked?.stock;
  const line = s && !locked ? oneLine(symbol, s) : null;
  return (
    <section className="block sx sx-stock" data-testid="sector-peers" style={{ "--sc": "var(--gold-deep)", paddingBlock: 0 } as React.CSSProperties}>
      <SectionHead id="sector" no="Sector & peers" icon="layers" tier="gold" title="Where its industry stands, and how it ranks inside it" sub="The industry's breadth cycle, the stock's rank inside it, its peers and its own chart, side by side." color="--gold-deep" />
      {q.isLoading && <div className="sx-skel" role="status" aria-label="Loading the sector reading" style={{ height: 120 }} />}
      {q.isError && <p className="sx-note" role="status" data-testid="sector-blank">{failureText(q.error)}</p>}
      {s && locked && (
        <div className="sx-oneline">
          <div className="sx-eyebrow">The industry today</div>
          {s.group ? <h3>{s.group.name} is in {an(s.group.state)} <StateChip state={s.group.state} />. <Link className="sx-link" to={`/sectors/${s.group.slug}`}>Open its page</Link></h3> : <h3>Industry not yet classified.</h3>}
          <LockedBlock plan="gold" title="The Sector & peers cards are part of the Gold plan">Open to everyone: the industry's state and breadth on Sector Pulse. Gold adds this stock's rank inside its industry, its 6-month quarter, whether it bottomed before the industry, its leader flag and the peer comparison, side by side.</LockedBlock>
        </div>
      )}
      {s && !locked && (
        <>
          <div className="sx-oneline">
            <div className="sx-eyebrow">In one line</div>
            {line ? <h3>{line}</h3> : <h3>Industry not yet classified.</h3>}
            <p className="sx-note" style={{ margin: 0 }}>{s.group ? `Data as of ${fullDate(s.group.date)} · industry: NSE's classification${s.sector ? ` (${s.sector}${s.industry ? ` · ${s.industry}` : ""}${s.amfi_category ? ` · ${s.amfi_category} (AMFI)` : ""})` : ""} · peer figures use the last completed week.` : (s.note ?? "NSE has not classified this stock's industry yet.")}</p>
          </div>
          <Cards symbol={symbol} name={name} s={s} tech={tech} score={score} jump={jump} />
        </>
      )}
      <p className="sx-note" style={{ marginTop: 14 }}>{NOTE}</p>
    </section>
  );
}
