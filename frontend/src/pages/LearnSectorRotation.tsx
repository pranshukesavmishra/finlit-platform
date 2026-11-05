// How Sector Rotation is measured (/learn/sector-rotation): the rules, in the package's own words (GET /api/rotation: method, params, study), and what the 2017-2026 study found. Every study number is
// read from the file; every figure is a past average, not a forecast. Describes; never advises. Styles: styles/rotation.css.
import { Link } from "react-router";
import { PageHeader } from "../components/PageHeader";
import { Blank } from "../components/sectors/Parts";
import { CornerBadge } from "../components/rotation/Parts";
import { CORNERS, cornerName, failureText, monthYear, pts, useRotationMap } from "../lib/rotation";
import { useDocTitle } from "../lib/title";

const TITLE = "How Sector Rotation is measured";
const DESC = "Industries take turns leading the market. Sector Rotation shows where each NSE industry stands against the average industry, how long it has been there and how its rank has moved. It uses the same counted stocks and the same equal-weighted industry groups as Sector Pulse.";

export function LearnSectorRotationPage() {
  useDocTitle(TITLE, DESC);
  const q = useRotationMap();
  const m = q.data, s = m?.study, p = m?.params;
  const rules: [string, string][] = m ? [
    ["Groups", `The NSE industries and sector groups with a Sector Pulse reading: ${p?.min_mem ?? 8} or more counted stocks. Each is the equal-weighted average of its counted stocks.`],
    ["Average industry", m.method.benchmark],
    ["Strength (across)", m.method.strength],
    ["Change (up)", m.method.change],
    ["Corner", m.method.corner],
    ["Weekly readings", m.method.week],
    ["Breadth", m.method.breadth],
    ["Rotation rank", m.method.rank],
    ["Rank changes", `Places moved since the previous weekly close and since 4 weekly closes ago. Moves of ${p?.move_places ?? 3} places or more are shown in bold; the 4-week climbers and fallers lists show moves of ${p?.move_places ?? 3} or more.`],
  ] : [];
  return (
    <div className="wrap sx rt" data-testid="learn-rotation">
      <PageHeader eyebrow="Learn · Sector Rotation" title={TITLE} description={DESC} links={["/sectors/rotation"]} learn={false} />
      {q.isLoading && <div className="sx-skel sx-sec" role="status" aria-label="Loading" />}
      {q.isError && <div className="sx-sec"><Blank title="The method is not available right now" reason={failureText(q.error)} /></div>}
      {m && (
        <div className="rt-stack">
          <section className="rt-card"><h2>The rules</h2>
            <dl className="rt-rules">{rules.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
            <p className="rt-note">Groups with fewer than {p?.min_mem ?? 8} counted stocks are not ranked and not placed in a corner.</p></section>
          {s && (
            <section className="rt-card rt-study"><h2>What the {s.period.from.slice(0, 4)}–{s.period.to.slice(0, 4)} study found</h2>
              <p className="rt-sub">{s.period.weeks} weeks from {monthYear(s.period.from)} to {monthYear(s.period.to)}, a median of {s.period.groups_per_week_median} groups a week, with the stock list rebuilt every month from what was known then. “Points” are the group's return minus the average industry's over the period after each weekly close. <b>Past averages, not forecasts.</b></p>
              <HScrollTable>
                <table className="rt-t"><thead><tr><th scope="col" className="l">Corner</th><th scope="col" className="r">Cases</th><th scope="col" className="r">Next 1 month</th><th scope="col" className="r">Next 3 months</th><th scope="col" className="r">Median, 3 months</th><th scope="col" className="r">Beat the average, 3 months</th><th scope="col" className="r">Next 6 months</th></tr></thead>
                  <tbody>{CORNERS.map((c) => { const x = s.corners[c]; return x ? <tr key={c}><th scope="row" className="l"><CornerBadge corner={c} /></th><td className="r">{x.cases.toLocaleString("en-IN")}</td><td className="r">{pts(x.next_1m)}</td><td className="r"><b>{pts(x.next_3m)}</b></td><td className="r">{pts(x.median_3m)}</td><td className="r">{x.beat_3m != null ? `${Math.round(x.beat_3m)}%` : "—"}</td><td className="r">{pts(x.next_6m)}</td></tr> : null; })}</tbody></table>
              </HScrollTable>
              <div className="rt-scards two">
                <div className="rt-sc"><h3>The gap between corners</h3><p>{s.text.spread}</p></div>
                <div className="rt-sc"><h3>Rank moves</h3><p>{s.text.rank}</p></div>
              </div>
              <h3 style={{ marginTop: 18 }}>Where groups went next</h3>
              <p className="rt-note">Share of moves out of each corner, by the corner they moved to (after two weekly closes). {s.text.stay}</p>
              <HScrollTable><table className="rt-t"><thead><tr><th scope="col" className="l">From</th>{CORNERS.map((c) => <th key={c} scope="col" className="r">{cornerName(c)}</th>)}</tr></thead>
                <tbody>{CORNERS.map((a) => <tr key={a}><th scope="row" className="l"><CornerBadge corner={a} /></th>{CORNERS.map((b) => <td key={b} className="r">{a === b ? "–" : s.moves.next_corner[a]?.[b] != null ? `${s.moves.next_corner[a][b]}%` : "—"}</td>)}</tr>)}</tbody></table></HScrollTable>
              {s.rank?.by_year_3m && <><h3 style={{ marginTop: 18 }}>The rank gap, year by year</h3><p className="rt-note">Top third minus bottom third by rotation rank, next 3 months, points. The last year runs to {monthYear(s.period.to)}.</p>
                <ul className="rt-years">{Object.entries(s.rank.by_year_3m as Record<string, number | null>).map(([y, v]) => <li key={y}><span>{y}</span><span className="tr" aria-hidden="true"><i style={{ width: `${Math.max(2, Math.min(100, Math.abs(v ?? 0) * 12))}%` }} /></span><b>{pts(v)}</b></li>)}</ul></>}
            </section>
          )}
          {s && <section className="rt-card warn"><h2>Limits of the study</h2><ul>{s.text.limits.map((x: string) => <li key={x}>{x}</li>)}</ul></section>}
          <footer className="sx-footer"><p>{m.disclaimer} <Link className="sx-link" to="/sectors/rotation">Open Sector Rotation</Link></p></footer>
        </div>
      )}
    </div>
  );
}
import { HScroll } from "../components/HScroll";
function HScrollTable({ children }: { children: React.ReactNode }) { return <div className="rt-tablebox"><HScroll label="table" className="rt-scroll">{children}</HScroll></div>; }
