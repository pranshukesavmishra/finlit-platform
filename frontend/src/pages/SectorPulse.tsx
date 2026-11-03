// Sector Pulse (/sectors): is buying spreading through an industry, or drying up? Every NSE industry (or sector group of small ones) with its state, breadth, thrust
// and leader flags, from GET /api/sectors. Every number is the server's; what the plan does not include arrives null with a reason and is said in words.
// Describes price and breadth data; never advice. Styles: styles/sectors.css.
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { PageHeader } from "../components/PageHeader";
import { HScroll } from "../components/HScroll";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import {
  FILTERS, SORT_LABEL, STATES, count, failureText, filterCounts, flagAge, flagText, fullDate, groupKindText, groupsLine, inFilter, level, mergedReasons, pct, plural, signedPct, sortRows, thrustText,
  useSectorBoard, type Board, type FilterKey, type GroupRow, type SortKey,
} from "../lib/sectors";
import { BreadthBars, Blank, LockedBlock, SectorFooter, StateChip } from "../components/sectors/Parts";

const TITLE = "Sector Pulse";
const DESC = "Is buying spreading through an industry, or drying up? Every evening we check how many stocks in each NSE industry are above their short, medium and longer-term averages. Only liquid, established stocks are counted, so a few thinly traded names cannot swing the reading.";

function Tiles({ b }: { b: Board }) {
  return (
    <ul className="sx-tiles" aria-label="How many groups are in each state" style={{ listStyle: "none", padding: 0 }}>
      {STATES.map((s) => {
        const n = b.counts?.[s.name] ?? 0;
        return <li key={s.code} className={"sx-tile" + (n === 0 ? " zero" : "")}><div className="top"><span className="n">{count(n)}</span><span className={`sx-chip st-${s.code}`}>{s.name}</span></div><p>{b.state_meanings?.[s.name]}</p></li>;
      })}
    </ul>
  );
}

function Market({ b }: { b: Board }) {
  const m = b.market;
  if (!m) return <section className="sx-card"><h2>The market behind the industries</h2><p className="sx-sub">The Nifty 50 index file is not part of this data set yet, so the market context is blank. It appears with the next nightly run that includes it.</p></section>;
  const below = m.above_200d === false;
  return (
    <section className="sx-card" aria-labelledby="sx-mkt">
      <div className="sx-mkt-h"><h2 id="sx-mkt">The market behind the industries</h2>{m.above_200d != null && <span className={`sx-chip ${below ? "st-fading" : "st-confirmed"}`}>{below ? "Below its 200-day average" : "Above its 200-day average"}</span>}</div>
      <div className="sx-nums">
        <div className="sx-num"><small>Nifty 50</small><b>{level(m.nifty50)}</b></div>
        <div className="sx-num"><small>200-day average</small><b>{level(m.nifty50_200d_average)}</b></div>
        <div className="sx-num"><small>Difference</small><b className={m.pct_vs_200d != null ? (m.pct_vs_200d < 0 ? "neg" : "pos") : ""}>{signedPct(m.pct_vs_200d, 1)}</b></div>
      </div>
      {b.study?.market && <p className="sx-sub" style={{ marginBottom: 8 }}>{b.study.market}</p>}
      <p className="sx-note">This split was examined after seeing the results, and rests on a small number of separate weeks. It describes the past; it is not a rule.</p>
    </section>
  );
}

function HowTo() {
  return (
    <div className="sx-two even">
      <section className="sx-card" aria-labelledby="sx-how">
        <h2 id="sx-how">How to read this page</h2>
        <ol className="sx-steps">
          <li><i>1</i><span><b>The coloured state</b> shows where an industry is in its cycle, from a broad sell-off (Washout) through a broad rebound (Thrust) to an established trend (Confirmed).</span></li>
          <li><i>2</i><span><b>The three bars</b> show the share of its counted stocks above their 9, 20 and 50-day averages: the short, medium and longer trend. Long bars mean most stocks are rising together.</span></li>
          <li><i>3</i><span><b>Industries are NSE's.</b> An industry with fewer than 10 counted stocks is read together with the other small industries of its NSE sector, as a sector group.</span></li>
          <li><i>4</i><span><b>Open an industry</b> to see a year of its history, how each stock compares inside it, which stocks are not counted and why, and what the 2017–2026 study found for its state.</span></li>
        </ol>
        <p style={{ marginTop: 14 }}><Link className="sx-link" to="/learn/sector-signals">Learn how sector signals work →</Link></p>
      </section>
      <section className="sx-card" aria-labelledby="sx-cyc">
        <h2 id="sx-cyc">The industry cycle</h2>
        <div className="sx-cycle">
          <div className="sx-stage st-washout"><b>Washout</b>Fewer than 40% of stocks above their 50-day average</div><span className="arrow" aria-hidden="true">→</span>
          <div className="sx-stage st-thrust"><b>Thrust C / CAP</b>A sudden, broad rebound within 5 sessions</div><span className="arrow" aria-hidden="true">→</span>
          <div className="sx-stage st-confirmed"><b>Confirmed</b>70%+ of stocks above all three averages</div>
        </div>
        <div className="sx-cycle-fade"><span className="arrow" aria-hidden="true">↓</span><div className="sx-stage st-fading"><b>Fading</b>A rebound or an uptrend lost its breadth. Industries that match none of these are Neutral.</div></div>
      </section>
    </div>
  );
}

function Th({ k, label, sort, dir, onSort, cls = "" }: { k: SortKey; label: string; sort: SortKey | null; dir: "asc" | "desc"; onSort: (k: SortKey) => void; cls?: string }) {
  const on = sort === k;
  return (
    <th scope="col" className={cls} aria-sort={on ? (dir === "asc" ? "ascending" : "descending") : "none"}>
      <button type="button" className={"sx-sortbtn" + (on ? " on" : "")} onClick={() => onSort(k)}>{label}<span className="ar" aria-hidden="true">{on ? (dir === "asc" ? "▲" : "▼") : ""}</span></button>
    </th>
  );
}

function GroupsTable({ b }: { b: Board }) {
  const [filter, setFilter] = useState<FilterKey>("all");
  const [sort, setSort] = useState<SortKey | null>(null);
  const [dir, setDir] = useState<"asc" | "desc">("desc");
  const counts = useMemo(() => filterCounts(b.rows), [b.rows]);
  const rows = useMemo(() => sortRows(b.rows.filter((r) => inFilter(r, filter)), sort, dir), [b.rows, filter, sort, dir]);
  const flagsLocked = b.rows.some((r) => r.leader_flags == null);
  const onSort = (k: SortKey) => { if (sort === k) setDir(dir === "asc" ? "desc" : "asc"); else { setSort(k); setDir(k === "name" || k === "state" || k === "thrust" || k === "index" ? "asc" : "desc"); } };
  return (
    <section className="sx-sec" aria-labelledby="sx-all">
      <div className="sx-bar">
        <div><h2 id="sx-all">All industries and sector groups</h2><p className="sx-sub" style={{ margin: 0 }}>Fresh thrusts first, then Washout, then Fading. Select a name to open it.</p></div>
        <div className="sx-filters" role="group" aria-label="Show">
          {FILTERS.map((f) => {
            const n = counts[f.key];
            const off = f.key === "flags" && flagsLocked;
            return <button key={f.key} type="button" className="sx-fbtn" aria-pressed={filter === f.key} disabled={off} title={off ? "Leader flags are part of the Silver plan" : undefined} onClick={() => setFilter(f.key)}>{f.label}{f.key === "all" ? ` ${count(b.rows.length)}` : n == null ? "" : ` · ${n}`}{off ? <Icon name="lock" /> : null}</button>;
          })}
        </div>
      </div>
      <div className="sx-sortsel"><label htmlFor="sx-sort">Sort by</label>
        <select id="sx-sort" value={sort ?? ""} onChange={(e) => { const v = e.target.value as SortKey | ""; if (v) { setSort(v); setDir(v === "name" || v === "state" || v === "thrust" || v === "index" ? "asc" : "desc"); } else setSort(null); }}>
          <option value="">The board's order</option>{(Object.keys(SORT_LABEL) as SortKey[]).map((k) => <option key={k} value={k}>{SORT_LABEL[k]}</option>)}
        </select>
        {sort && <button type="button" className="btn" style={{ height: 38 }} onClick={() => setDir(dir === "asc" ? "desc" : "asc")} aria-label={dir === "asc" ? "Lowest first; switch to highest first" : "Highest first; switch to lowest first"}>{dir === "asc" ? "▲ Low to high" : "▼ High to low"}</button>}
      </div>
      <div className="sx-tablebox" style={{ marginTop: 10 }}>
        <HScroll label="industries table" className="sx-scroll">
          <table className="sx-t" data-testid="groups-table">
            <caption className="sx-visually">Every industry and sector group with a reading: state, breadth, index against its 52-week high, higher-low share, last thrust and leader flags</caption>
            <thead><tr>
              <Th k="name" label="Industry or sector group" sort={sort} dir={dir} onSort={onSort} />
              <Th k="state" label="State" sort={sort} dir={dir} onSort={onSort} cls="l" />
              <th scope="col" className="l">Above 9 / 20 / 50-day avg<span className="sx-visually"> (sort with the Sort by menu)</span>
                {(["above_9", "above_20", "above_50"] as const).map((k) => <button key={k} type="button" className={"sx-sortbtn sx-mini" + (sort === k ? " on" : "")} aria-label={`Sort by the share above the ${k.slice(6)}-day average`} onClick={() => onSort(k)}>{k.slice(6)}{sort === k ? (dir === "asc" ? "▲" : "▼") : ""}</button>)}</th>
              <Th k="index" label="Index vs 52-wk high" sort={sort} dir={dir} onSort={onSort} />
              <Th k="higher_low" label="Higher-low share" sort={sort} dir={dir} onSort={onSort} />
              <Th k="thrust" label="Last thrust" sort={sort} dir={dir} onSort={onSort} cls="l" />
              <Th k="flags" label="Leader flags" sort={sort} dir={dir} onSort={onSort} />
            </tr></thead>
            <tbody>
              {rows.map((r) => <Row key={r.slug} r={r} />)}
              {!rows.length && <tr><td colSpan={7} className="l" style={{ whiteSpace: "normal", textAlign: "left" }}>{filter === "thrust" ? "No group is in a fresh thrust today." : "No group matches this filter today."}</td></tr>}
            </tbody>
          </table>
        </HScroll>
      </div>
      <p className="sx-note sx-foot">Higher-low share: of the counted stocks, the share that did not make a new low when the industry index did (under 20%, shown in red, is a capitulation). Index: the counted stocks averaged with equal weight. Thrust ages are in trading sessions.
        {flagsLocked && <> Leader-flag counts are part of the Silver plan.</>}</p>
    </section>
  );
}

function Row({ r }: { r: GroupRow }) {
  return (
    <tr>
      <td><div className="sx-name"><Link to={`/sectors/${r.slug}`}>{r.name}</Link><small>{groupKindText(r)}</small></div></td>
      <td className="l"><StateChip state={r.state} /></td>
      <td className="l"><BreadthBars b={r.breadth} name={r.name} /></td>
      <td>{signedPct(r.index_vs_52w_high, 1)}</td>
      <td className={r.higher_low_share != null && r.higher_low_share < 20 ? "sx-low" : ""}>{pct(r.higher_low_share)}{r.higher_low_share != null && r.higher_low_share < 20 ? <span className="sx-visually"> (under 20%: a capitulation)</span> : null}</td>
      <td className="l" style={{ whiteSpace: "normal", minWidth: 118 }}>{thrustText(r.last_thrust)}</td>
      <td className="sx-flagn">{r.leader_flags == null ? <span className="sx-na" title="Leader flags are part of the Silver plan">Silver</span> : r.leader_flags > 0 ? r.leader_flags : <span className="sx-na" aria-label="none">—</span>}</td>
    </tr>
  );
}

function TooFew({ b }: { b: Board }) {
  if (!b.too_few_stocks?.length) return null;
  const total = b.too_few_stocks.reduce((s, x) => s + x.stocks_counted, 0);
  return (
    <section className="sx-card sx-sec" aria-labelledby="sx-few">
      <h2 id="sx-few">Too few stocks for a reading</h2>
      <p className="sx-sub">A group needs at least 8 counted stocks before its breadth means much: with fewer, one stock moves a reading by more than 12 points. These {b.too_few_stocks.length} NSE sector groups hold {count(total)} counted stocks between them, so they are shown without a state until they grow.</p>
      <ul className="sx-chips" style={{ listStyle: "none", padding: 0 }}>{b.too_few_stocks.map((g) => <li key={g.slug} className="sx-pill">{g.name} <small>· {g.stocks_counted} counted</small></li>)}</ul>
    </section>
  );
}

function Counted({ b }: { b: Board }) {
  const u = b.universe;
  if (!u) return null;
  const reasons = mergedReasons(u.reasons);
  const max = Math.max(1, ...reasons.map((r) => r.stocks));
  return (
    <section className="sx-card sx-sec" aria-labelledby="sx-counted">
      <h2 id="sx-counted">Which stocks are counted</h2>
      <p className="sx-sub">Thinly traded, very small or newly listed stocks move on a handful of trades and would add noise to the breadth readings, so they are left out. The list is reviewed on the first trading day of each month.</p>
      <div className="sx-ustats">
        <div className="sx-num"><small>NSE stocks with an industry, traded on {fullDate(u.date).replace(/ \d{4}$/, "")}</small><b>{count(u.stocks_with_industry_traded)}</b></div>
        <div className="sx-num"><small>Meet the rules</small><b>{count(u.meet_rules)}</b></div>
        <div className="sx-num on"><small>Counted in the {b.groups} groups with a reading</small><b>{count(u.counted_in_groups_with_reading)}</b></div>
      </div>
      <div className="sx-ucols">
        <div><h3>A stock is counted when it</h3><ul className="sx-rules">
          <li>trades in NSE's normal EQ series</li><li>has a median traded value of Rs 2 crore a day or more over 65 sessions (once counted, it stays down to Rs 1 crore)</li>
          <li>traded on at least 62 of those 65 sessions, and was stuck at a price band on no more than 1</li><li>is priced Rs 20 or more</li>
          <li>has an AMFI average market cap of Rs 1,000 crore or more (stays down to Rs 800 crore)</li><li>has been listed for at least 6 months (126 sessions)</li></ul>
          <p className="sx-note" style={{ marginTop: 10 }}>{b.universe_rules}</p></div>
        <div><h3>Why the other {count(u.not_counted)} are not counted</h3>
          <div className="sx-rb" role="list">{reasons.map((r) => <div className="r" role="listitem" key={r.reason}><span>{r.reason.charAt(0).toUpperCase() + r.reason.slice(1)}</span><span className="t" aria-hidden="true"><i style={{ width: `${(r.stocks / max) * 100}%` }} /></span><b>{count(r.stocks)}</b></div>)}</div>
          <p className="sx-note" style={{ marginTop: 10 }}>Most of these stocks miss more than one rule, so the counts add up to more than {count(u.not_counted)}. Each industry page lists its own stocks that are not counted, with the reasons.</p></div>
      </div>
    </section>
  );
}

function Flags({ b }: { b: Board }) {
  const [all, setAll] = useState(false);
  if (b.leader_flags == null) {
    return (
      <section className="sx-card sx-sec" aria-labelledby="sx-flags">
        <h2 id="sx-flags">Leader flags: 52-week highs inside weak industries</h2>
        <LockedBlock plan="silver" title="The list of leader flags is part of the Silver plan">The industry states and breadth above are open to everyone. Silver adds the stocks that closed at a 52-week high while their industry is 10% or more below its own high, with the industry, the age of the flag and the stock's 6-month quarter.</LockedBlock>
      </section>
    );
  }
  const list = all ? b.leader_flags : b.leader_flags.slice(0, 10);
  const full = b.leader_flags.filter((f) => f.tier_code === 2).length;
  const groups = new Set(b.leader_flags.map((f) => f.group_slug)).size;
  return (
    <section className="sx-card sx-sec" aria-labelledby="sx-flags">
      <div className="sx-bar" style={{ marginBottom: 0 }}><div><h2 id="sx-flags">Leader flags: 52-week highs inside weak industries</h2>
        <p className="sx-sub">A stock gets a flag when it closes at a 52-week high while its industry index is 15% or more below its own high (10–15% is the softer tier). The flag stays live for 60 sessions after the last such high. {b.leader_flags.length} flags are live in {groups} groups: {full} full flags and {b.leader_flags.length - full} in the softer tier.</p></div>
        {b.leader_flags.length > 10 && <button type="button" className="btn" aria-expanded={all} onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${b.leader_flags.length}`}</button>}</div>
      {!b.leader_flags.length ? <p className="sx-note" role="status">No stock is flagged today: none closed at a 52-week high in the last 60 sessions while its industry was 10% or more below its own high.</p> :
        <ul className="sx-flags" style={{ listStyle: "none", padding: 0 }}>{list.map((f) => (
          <li className="sx-flag" key={f.symbol + f.group_slug}><div className="h"><Link to={`/stocks/${f.symbol}`}>{f.symbol}</Link><span className={"tier" + (f.tier_code === 2 ? "" : " soft")}>{flagText(f)}</span></div>
            <span>{f.group}</span><span>{flagAge(f.sessions_ago)}{f.quarter ? ` · 6-month quarter ${f.quarter}` : ""}</span></li>))}</ul>}
      {b.leader_flag_study && <div className="sx-study"><b>What the 2017–2026 study found</b>{b.leader_flag_study} <em>Past averages, not forecasts.</em></div>}
    </section>
  );
}

export function SectorPulsePage() {
  useDocTitle(TITLE, DESC);
  const q = useSectorBoard();
  const b = q.data;
  return (
    <div className="wrap sx" data-testid="sector-pulse">
      <PageHeader eyebrow="Sectors" title={TITLE} description={DESC} meta={b ? groupsLine(b) : undefined} links={["/learn/sector-signals"]} learn={false} />
      {q.isLoading && <div className="sx-skel sx-sec" role="status" aria-label="Loading the sector readings" />}
      {q.isError && <div className="sx-sec"><Blank title="Sector Pulse is not available right now" reason={failureText(q.error)}><button type="button" className="btn" onClick={() => q.refetch()}>Try again</button></Blank></div>}
      {b && (
        <>
          <Tiles b={b} />
          <div className="sx-two">
            <Market b={b} />
            {b.market_note && <section className="sx-warn" role="note" aria-labelledby="sx-wn"><h2 id="sx-wn"><Icon name="alert" /> Breadth is weak almost everywhere</h2><p>{b.market_note}{b.counts ? ` ${plural(b.counts.Washout ?? 0, "group")} ${(b.counts.Washout ?? 0) === 1 ? "is" : "are"} in a Washout; ${b.counts.Confirmed ? plural(b.counts.Confirmed, "group") + " Confirmed" : "none is Confirmed"} and ${(b.counts["Thrust C"] ?? 0) + (b.counts["Thrust CAP"] ?? 0) ? plural((b.counts["Thrust C"] ?? 0) + (b.counts["Thrust CAP"] ?? 0), "group") + " had a thrust today" : "none had a thrust today"}.` : ""}</p></section>}
          </div>
          <div style={{ marginTop: 16 }}><HowTo /></div>
          <GroupsTable b={b} />
          <TooFew b={b} />
          <Counted b={b} />
          <Flags b={b} />
          <SectorFooter disclaimer={b.disclaimer} />
        </>
      )}
    </div>
  );
}
