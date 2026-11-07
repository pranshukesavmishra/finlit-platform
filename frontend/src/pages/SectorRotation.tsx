// Sector Rotation (/sectors/rotation): which NSE industry groups are pulling ahead of the average industry, which are falling behind, and how their ranks change, from GET /api/rotation.
// Every number and group name is the server's. Corners always carry their name and 2x2 glyph; a corner is confirmed after two weekly closes, and a hollow dot / "this week reads" says when
// the week's reading differs. Describes past prices; never advice; every study figure is a past average, not a forecast. Styles: styles/rotation.css.
import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { PageHeader } from "../components/PageHeader";
import { HScroll } from "../components/HScroll";
import { Blank, StateChip } from "../components/sectors/Parts";
import { CornerBadge, RankMove, SectorTabs, Spark } from "../components/rotation/Parts";
import { RotationMapChart } from "../components/rotation/RotationMap";
import { useDocTitle } from "../lib/title";
import { level } from "../lib/sectors";
import {
  CORNERS, asFilter, cornerName, failureText, inCorner, longDate, monthYear, nextCorners, pts, rankGrid, rowsByRank, shade, shortDate, shortName, tileStudyLine, useRotationMap, weeksText,
  type CornerFilter, type RotationMap, type RotationRow,
} from "../lib/rotation";

const TITLE = "Sector Rotation";
const DESC = "Which NSE industries are pulling ahead of the average industry, and which are falling behind? Every evening we compare each industry's 6-month and last-month returns with the average industry, place it in one of four corners, and rank all of them. A corner changes only after two weekly closes, so one noisy week does not move it.";
export const DATA_LINE = "NSE daily data, equal-weighted industry groups";

function dataLine(m: RotationMap): string {
  const ind = m.rows.filter((r) => r.kind === "industry").length;
  const a = m.average_industry;
  return `Data as of ${longDate(m.date)}, after the close${m.week_closed ? "" : " (week in progress)"} · ${DATA_LINE} · ${m.groups} groups with a reading (${ind} NSE industries and ${m.groups - ind} sector groups) · the same counted stocks as Sector Pulse · the average industry: ${pts(a.return_6m)}% over 6 months, ${pts(a.return_1m)}% over 1 month`;
}

function Tiles({ m, filter, setFilter }: { m: RotationMap; filter: CornerFilter; setFilter: (f: CornerFilter) => void }) {
  return (
    <ul className="rt-tiles" aria-label="Industries in each corner. Select one to filter the lists below." style={{ listStyle: "none", padding: 0 }}>
      {CORNERS.map((c) => {
        const name = cornerName(c), n = m.counts?.[name] ?? 0, on = filter === c;
        return (
          <li key={c}>
            <button type="button" className={`rt-tile c-${c}${on ? " on" : ""}`} aria-pressed={on} onClick={() => setFilter(on ? "all" : c)} data-testid={`tile-${c}`}>
              <span className="rt-top"><CornerBadge corner={c} name={name} /><b className="n">{n}</b></span>
              <span className="mean">{m.corner_meanings?.[name]}</span>
              <span className="study">{tileStudyLine(m.study, c)}{c === "ahead_gaining" && m.study?.breadth?.ahead_gaining ? ` Broad breadth ${pts(m.study.breadth.ahead_gaining.broad.mean)}, narrow ${pts(m.study.breadth.ahead_gaining.narrow.mean)}.` : ""}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function MarketStrip({ m }: { m: RotationMap }) {
  const k = m.market;
  const t = m.study?.text?.spread as string | undefined;
  if (!k || k.pct_vs_200d == null) return <div className="rt-card rt-strip" role="note"><span className="k">The market</span><span>The Nifty 50 reading is not in this data set yet, so the market context is blank.</span></div>;
  return (
    <div className="rt-card rt-strip" role="note">
      <span className="k">The market</span>
      <span><b>Nifty 50 {level(k.nifty50)}</b>, {Math.abs(k.pct_vs_200d).toFixed(1)}% {k.pct_vs_200d < 0 ? "below" : "above"} its {k.average_label ?? "200-day exponential average"} of {level(k.nifty50_200d_average)}</span>
      {t && <span className="why">{t} <em>Past averages, not forecasts.</em></span>}
    </div>
  );
}

function CornerBoxes({ m, filter, onOpen }: { m: RotationMap; filter: CornerFilter; onOpen: (s: string) => void }) {
  const order: CornerFilter[] = ["behind_gaining", "ahead_gaining", "behind_slipping", "ahead_slowing"];
  return (
    <div className="rt-boxes">
      <span className="rt-axl y">Gaining last month</span>
      <div className="rt-grid2">
        {order.map((c) => {
          const rows = m.rows.filter((r) => r.corner === c).sort((a, b) => (b.strength_pts ?? 0) - (a.strength_pts ?? 0));
          const nx = nextCorners(m.study, c as never);
          return (
            <section key={c} className={`rt-box c-${c}${filter !== "all" && filter !== c ? " dim" : ""}`} aria-label={`${cornerName(c)}: ${rows.length} groups`}>
              <h3><CornerBadge corner={c} /><span className="cnt">{rows.length} groups</span></h3>
              <p className="rt-note">{m.corner_meanings?.[cornerName(c)]}</p>
              <table className="rt-mini">
                <thead><tr><th scope="col">Industry</th><th scope="col">6 months</th><th scope="col">Last month</th></tr></thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.slug}>
                      <th scope="row"><button type="button" className="rt-link" onClick={() => onOpen(r.slug)}>{r.name}</button>{r.weeks_in_corner === 1 && r.previous_corner ? <span className="rt-new">New</span> : null}
                        <small>Rank {r.rank} · {weeksText(r.weeks_in_corner)} here{r.this_week_reading_name ? ` · this week reads ${r.this_week_reading_name}` : ""}</small></th>
                      <td className="num">{pts(r.strength_pts)}</td><td className="num">{pts(r.change_pts)}</td>
                    </tr>
                  ))}
                  {!rows.length && <tr><td colSpan={3} className="rt-note">No group is in this corner today.</td></tr>}
                </tbody>
              </table>
              {nx.length > 0 && <p className="rt-note rt-foot">In the study, {nx[0].pct}% of moves out of this box went to {cornerName(nx[0].to)}{nx[1] ? ` and ${nx[1].pct}% to ${cornerName(nx[1].to)}` : ""}. Past averages, not forecasts.</p>}
            </section>
          );
        })}
      </div>
      <span className="rt-axl x"><span>Behind the average over 6 months</span><span>Ahead of the average over 6 months</span></span>
    </div>
  );
}

function Stands({ m, filter, onOpen }: { m: RotationMap; filter: CornerFilter; onOpen: (s: string) => void }) {
  const [view, setView] = useState<"corners" | "map">("corners");
  return (
    <section className="rt-card rt-stands" aria-labelledby="rt-stands">
      <div className="rt-bar"><div><h2 id="rt-stands">Where each industry stands</h2>
        <p className="rt-sub">Each industry is compared with the average industry twice: over 6 months (ahead or behind) and over the last month (gaining or slowing). The two answers put it in one of four boxes. Numbers are points against the average.</p></div>
        <div className="rt-seg" role="group" aria-label="View"><button type="button" aria-pressed={view === "corners"} onClick={() => setView("corners")}>Corners</button><button type="button" aria-pressed={view === "map"} onClick={() => setView("map")}>Map</button></div></div>
      {view === "corners" ? <CornerBoxes m={m} filter={filter} onOpen={onOpen} /> : <RotationMapChart rows={m.rows} date={m.date} onOpen={onOpen} filterCorner={filter === "all" ? undefined : filter} />}
      <p className="rt-note">“New”: moved into this box this week. “this week reads”: this week's reading is in another box, and a second weekly close there would move it. Select a name to open its page.</p>
    </section>
  );
}

function Rail({ m }: { m: RotationMap }) {
  const moved = m.moved_this_week;
  return (
    <aside className="rt-rail" aria-label="This week">
      <section className="rt-card">
        <h2>Changed corner this week</h2>
        <p className="rt-note">After a second weekly close in the new corner. {moved.length} of {m.groups}.</p>
        {moved.length ? <ul className="rt-moved">{moved.map((x) => <li key={x.slug}><Link to={`/sectors/${x.slug}`}>{x.name}</Link><span>{x.from} <i aria-hidden="true">→</i> <b>{x.to}</b></span></li>)}</ul> : <p className="rt-note" role="status">No industry changed corner this week.</p>}
      </section>
      <section className="rt-card">
        <h2>Biggest rank moves, 4 weeks</h2>
        <div className="rt-two">
          <div><h3 className="up">Climbed</h3>{m.climbers_4w.length ? <ul>{m.climbers_4w.map((x) => <li key={x.slug}><Link to={`/sectors/${x.slug}`}>{x.name}</Link><span><RankMove v={x.change} /> <small>rank {x.rank}</small></span></li>)}</ul> : <p className="rt-note">None climbed 3 or more places.</p>}</div>
          <div><h3 className="down">Fell</h3>{m.fallers_4w.length ? <ul>{m.fallers_4w.map((x) => <li key={x.slug}><Link to={`/sectors/${x.slug}`}>{x.name}</Link><span><RankMove v={x.change} /> <small>rank {x.rank}</small></span></li>)}</ul> : <p className="rt-note">None fell 3 or more places.</p>}</div>
        </div>
        <p className="rt-note">Places moved since 4 weekly closes ago, then the rank now. {m.study?.text?.rank ? <>{m.study.text.rank.split(". ").slice(1).join(". ")} <em>Past averages, not forecasts.</em></> : null}</p>
      </section>
    </aside>
  );
}

function Ranking({ m, filter, setFilter }: { m: RotationMap; filter: CornerFilter; setFilter: (f: CornerFilter) => void }) {
  const rows = useMemo(() => rowsByRank(m.rows).filter((r) => inCorner(r, filter)), [m.rows, filter]);
  const worst = Math.max(...m.rows.map((r) => r.rank_worst_26w ?? r.ranked ?? 1), m.groups);
  return (
    <section className="rt-card rt-rank" aria-labelledby="rt-rank">
      <h2 id="rt-rank">Rotation rank</h2>
      <p className="rt-sub">All {m.groups} groups, ranked every week by their 3, 6 and 12-month returns against the average industry (three quarters of the score) and the share of their stocks above the 50-day average (one quarter). The arrows show the places moved since last week and since 4 weeks ago.</p>
      <div className="rt-pills" role="group" aria-label="Show">
        <button type="button" aria-pressed={filter === "all"} onClick={() => setFilter("all")}>All {m.groups}</button>
        {CORNERS.map((c) => <button key={c} type="button" aria-pressed={filter === c} onClick={() => setFilter(filter === c ? "all" : c)}>{cornerName(c)} · {m.counts?.[cornerName(c)] ?? 0}</button>)}
      </div>
      <div className="rt-tablebox"><HScroll label="rotation ranking table" className="rt-scroll">
        <table className="rt-t" data-testid="rank-table">
          <caption className="sx-visually">Every group with a rotation reading, by rank: places moved in 1 and 4 weeks, corner, strength and change against the average industry, breadth, Sector Pulse state and the rank over 26 weeks</caption>
          <thead><tr><th scope="col" className="r">Rank</th><th scope="col">1 wk</th><th scope="col">4 wks</th><th scope="col" className="l">Industry or sector group</th><th scope="col" className="l">Corner</th><th scope="col" className="r">6M vs avg</th><th scope="col" className="r">1M vs avg</th><th scope="col" className="l">Breadth</th><th scope="col" className="l">Sector Pulse</th><th scope="col" className="l">Rank, last 26 weeks</th></tr></thead>
          <tbody>
            {rows.map((r) => <RankRow key={r.slug} r={r} worst={worst} />)}
            {!rows.length && <tr><td colSpan={10} className="rt-note">No group is in this corner today.</td></tr>}
          </tbody>
        </table>
      </HScroll></div>
      <p className="rt-note">Breadth: share of the group's counted stocks above their 50-day average; 50% or more is broad, under 40% narrow. A sparkline higher up means a better rank. Ties share a rank. {m.disclaimer}</p>
    </section>
  );
}
function RankRow({ r, worst }: { r: RotationRow; worst: number }) {
  const b = r.breadth_above_50;
  return (
    <tr>
      <td className="r rk">{r.rank ?? "—"}</td>
      <td><RankMove v={r.rank_change_1w} /></td><td><RankMove v={r.rank_change_4w} /></td>
      <th scope="row" className="l nm"><Link to={`/sectors/${r.slug}`}>{r.name}</Link><small>{r.stocks_counted} stocks counted{r.kind === "sector" ? " · sector group" : ""}{r.leader_flags ? ` · ${r.leader_flags} leader ${r.leader_flags === 1 ? "flag" : "flags"}` : ""}</small></th>
      <td className="l"><CornerBadge corner={r.corner} /><small className="sub">{weeksText(r.weeks_in_corner)}{r.weeks_in_corner === 1 && r.previous_corner ? " · new this week" : ""}{r.this_week_reading_name ? ` · this week reads ${r.this_week_reading_name}` : ""}</small></td>
      <td className="r num v1">{pts(r.strength_pts)}</td><td className="r num v2">{pts(r.change_pts)}</td>
      <td className="l br">{b == null ? <span className="rt-note">No reading</span> : <><span className="rt-bar" aria-hidden="true"><i style={{ width: `${Math.max(0, Math.min(100, b))}%` }} className={r.breadth ?? ""} /></span><b>{Math.round(b)}%</b><small className="sub">{r.breadth_name}</small></>}</td>
      <td className="l">{r.sector_state ? <StateChip state={r.sector_state} /> : <span className="rt-note">—</span>}</td>
      <td className="l sp"><Spark hist={r.rank_history} worst={worst} /><small className="sub">best {r.rank_best_26w ?? "—"}<br />worst {r.rank_worst_26w ?? "—"}</small></td>
    </tr>
  );
}

function RankGrid({ m }: { m: RotationMap }) {
  const g = useMemo(() => rankGrid(m.rows, 12), [m.rows]);
  return (
    <section className="rt-card" aria-labelledby="rt-grid">
      <h2 id="rt-grid">How the ranking changed</h2>
      <p className="rt-note">Each group's rank at the last {g.weeks.length} weekly closes, in today's order. Darker cells are higher ranks.</p>
      <div className="rt-tablebox"><HScroll label="rank history grid" className="rt-scroll"><table className="rt-grid" data-testid="rank-grid">
        <caption className="sx-visually">Rank of each group at each of the last {g.weeks.length} weekly closes</caption>
        <thead><tr><th scope="col" className="l">Group</th>{g.weeks.map((d) => <th key={d} scope="col">{shortDate(d)}</th>)}</tr></thead>
        <tbody>{g.rows.map(({ row, cells }) => (
          <tr key={row.slug}><th scope="row" className="l" title={row.name}>{row.rank}. {shortName(row.name)}</th>
            {cells.map((c, j) => <td key={j} className={`s${shade(c, row.ranked)}`}>{c ?? "–"}</td>)}</tr>))}</tbody>
      </table></HScroll></div>
    </section>
  );
}

function Study({ m }: { m: RotationMap }) {
  const s = m.study;
  if (!s) return <section className="rt-card"><h2>What the study found</h2><p className="rt-note" role="status">The study figures are not part of this data set.</p></section>;
  const t = s.text;
  return (
    <section className="rt-card rt-study" aria-labelledby="rt-study">
      <h2 id="rt-study">What the {s.period.from.slice(0, 4)}–{s.period.to.slice(0, 4)} study found</h2>
      <p className="rt-sub">The same rules on {s.period.groups_per_week_median} NSE industry and sector groups a week, {monthYear(s.period.from)} to {monthYear(s.period.to)} ({s.period.weeks} weeks), with the stock list rebuilt every month from what was known then. “Points” are a group's return minus the average industry's over the next 3 months. <b>Past averages, not forecasts.</b></p>
      <div className="rt-scards">
        {CORNERS.map((c) => { const x = s.corners[c]; return x ? (
          <div key={c} className="rt-sc"><h3><CornerBadge corner={c} /></h3><div className="big">{pts(x.next_3m)} pts</div><p>{t[c]}</p></div>) : null; })}
      </div>
      <div className="rt-scards two">
        {t.rank && <div className="rt-sc"><h3>The ranking</h3><p>{t.rank} {t.stay}</p></div>}
        {t.sector_indices && <div className="rt-sc"><h3>Where it did not work</h3><p>{t.sector_indices}</p></div>}
      </div>
      <p className="rt-note">Limits: {t.limits.join(" ")} <Link className="sx-link" to="/learn/sector-rotation">How rotation is measured</Link></p>
    </section>
  );
}

function HowTo({ m }: { m: RotationMap }) {
  const bg = m.study?.moves?.next_corner?.behind_gaining ?? {};
  return (
    <section className="rt-card" aria-labelledby="rt-how">
      <h2 id="rt-how">How to read this page</h2>
      <div className="rt-three">
        <div><h3>Corners describe the past</h3><p>A corner says how an industry did against the average industry over 6 months and last month. It is not a forecast, and it is not a reason to act.</p></div>
        <div><h3>Read the corner with breadth</h3><p>A lead carried by most of an industry's stocks (broad) held up better in the study than one carried by a few (narrow). <Link className="sx-link" to="/sectors">Sector Pulse</Link> shows the breadth cycle for each industry.</p></div>
        <div><h3>“Behind but gaining” is usually a bounce</h3><p>{bg.ahead_gaining != null ? `In the study only ${bg.ahead_gaining}% of it led to Ahead and gaining${bg.behind_slipping != null ? `; ${bg.behind_slipping}% went back to Behind and slipping` : ""}.` : "The study figures for moves out of this corner are not in this data set."}</p></div>
      </div>
    </section>
  );
}

export function SectorRotationPage() {
  useDocTitle(TITLE, DESC);
  const q = useRotationMap();
  const m = q.data;
  const [sp, setSp] = useSearchParams();
  const nav = useNavigate();
  const filter = asFilter(sp.get("corner"));
  const setFilter = (f: CornerFilter) => { const n = new URLSearchParams(sp); if (f === "all") n.delete("corner"); else n.set("corner", f); setSp(n, { replace: true }); };
  const open = (slug: string) => nav(`/sectors/${slug}`);
  return (
    <div className="wrap sx rt" data-testid="sector-rotation">
      <PageHeader eyebrow="Sectors" title={TITLE} description={DESC} meta={m ? dataLine(m) : undefined} links={["/learn/sector-rotation"]} learn={false}><SectorTabs active="rotation" /></PageHeader>
      {q.isLoading && <div className="sx-skel sx-sec" role="status" aria-label="Loading the rotation readings" />}
      {q.isError && <div className="sx-sec"><Blank title="Sector Rotation is not available right now" reason={failureText(q.error)}><button type="button" className="btn" onClick={() => q.refetch()}>Try again</button></Blank></div>}
      {m && (
        <div className="rt-stack">
          {!m.week_closed && <p className="rt-week" role="status">Week in progress: readings as of {shortDate(m.date)}</p>}
          <Tiles m={m} filter={filter} setFilter={setFilter} />
          <MarketStrip m={m} />
          <div className="rt-main"><Stands m={m} filter={filter} onOpen={open} /><Rail m={m} /></div>
          <Ranking m={m} filter={filter} setFilter={setFilter} />
          <RankGrid m={m} />
          <Study m={m} />
          <HowTo m={m} />
          <footer className="sx-footer"><p>{m.disclaimer} Study results are past averages from {m.study?.period.groups_per_week_median ?? "the"} NSE industry and sector groups a week{m.study ? `, ${monthYear(m.study.period.from)} to ${monthYear(m.study.period.to)}` : ""}, and do not predict future returns. Prices: NSE daily files, adjusted for splits, bonuses and rights. Industries: NSE's classification as of {longDate(m.date)}. Market caps: AMFI.</p></footer>
        </div>
      )}
    </div>
  );
}
