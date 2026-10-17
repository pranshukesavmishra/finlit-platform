import { useMemo, useState } from "react";
import { Link } from "react-router";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import { dayLabel, useFeed, type FeedItem } from "../lib/feed";
import { useWatchlist } from "../lib/watchlist";

const ymd = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export function ResultsPage() {
  useDocTitle("Results calendar", "When companies report quarterly results: a month calendar of board-meeting dates and recently declared results, with the filings.");
  const wl = useWatchlist();
  const mine = useMemo(() => [...new Set(wl.lists.flatMap((l) => l.symbols))], [wl]);
  const [onlyMine, setOnlyMine] = useState(false);
  const [month, setMonth] = useState(() => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), 1); });
  const [pick, setPick] = useState<string | null>(null);
  const { data, isLoading, isError } = useFeed("result", { limit: 200 });
  const items = useMemo(() => (data || []).filter((i) => !onlyMine || (i.symbol && mine.includes(i.symbol))), [data, onlyMine, mine]);
  const byDay = useMemo(() => { const m = new Map<string, FeedItem[]>(); items.forEach((i) => m.set(i.date, [...(m.get(i.date) || []), i])); return m; }, [items]);
  const today = ymd(new Date());
  const first = new Date(month.getFullYear(), month.getMonth(), 1), pad = (first.getDay() + 6) % 7, days = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const cells = Array.from({ length: Math.ceil((pad + days) / 7) * 7 }, (_, i) => (i < pad || i >= pad + days ? null : new Date(month.getFullYear(), month.getMonth(), i - pad + 1)));
  const upcoming = items.filter((i) => i.date >= today).sort((a, b) => a.date.localeCompare(b.date)).slice(0, 40);
  const declared = items.filter((i) => i.date < today).slice(0, 30);
  const sel = pick ? byDay.get(pick) || [] : [];
  return (
    <div className="wrap ipo">
      <header className="dash-h"><div><div className="eyebrow">Market</div><h1>Results calendar</h1><p className="muted">Board-meeting dates for quarterly results, and the filings once they are out. Dates are as announced to the exchanges.</p></div>
        <label className="sw"><input type="checkbox" checked={onlyMine} onChange={(e) => setOnlyMine(e.target.checked)} /><span aria-hidden="true" /><b>Only my watchlist{mine.length ? ` (${mine.length})` : ""}</b></label></header>
      {isError && <div className="formerr">The calendar could not be loaded. Please try again shortly.</div>}
      <div className="rc-grid">
        <section className="card">
          <div className="card-h"><h3><span className="ci"><Icon name="calendar" /></span>{month.toLocaleDateString("en-IN", { month: "long", year: "numeric" })}</h3>
            <span className="row"><button className="btn" aria-label="Previous month" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() - 1, 1))}>←</button><button className="btn" onClick={() => { const d = new Date(); setMonth(new Date(d.getFullYear(), d.getMonth(), 1)); }}>Today</button><button className="btn" aria-label="Next month" onClick={() => setMonth(new Date(month.getFullYear(), month.getMonth() + 1, 1))}>→</button></span></div>
          {isLoading ? <div className="skeleton" style={{ height: 320 }} /> : (
            <div className="rcal" role="grid" aria-label="Results calendar">
              {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((d) => <div key={d} className="rcal-h" role="columnheader">{d}</div>)}
              {cells.map((d, i) => { const k = d ? ymd(d) : ""; const its = d ? byDay.get(k) || [] : []; return (
                !d ? <div key={i} className="rcal-c off" role="gridcell" aria-hidden="true" /> : <button key={i} role="gridcell" disabled={!its.length} className={"rcal-c" + (!d ? " off" : "") + (k === today ? " today" : "") + (pick === k ? " on" : "") + (its.length ? " has" : "")} onClick={() => setPick(pick === k ? null : k)} aria-label={d ? `${d.toDateString()}: ${its.length} results` : undefined}>
                  {d && <><b>{d.getDate()}</b>{its.slice(0, 3).map((x) => <span key={x.id} className={x.date < today ? "done" : ""}>{x.symbol || x.company}</span>)}{its.length > 3 && <em>+{its.length - 3} more</em>}</>}
                </button>); })}
            </div>)}
          {sel.length > 0 && <div className="rcal-sel"><h4>{dayLabel(pick!)}</h4><ul>{sel.map((x) => <li key={x.id}><Link to={x.symbol ? `/stocks/${x.symbol}` : "#"}><b>{x.symbol}</b> {x.company}</Link><span>{x.period || x.category}</span>{x.link && <a href={x.link} target="_blank" rel="noopener noreferrer">Filing ↗</a>}</li>)}</ul></div>}
        </section>
        <aside className="rc-side">
          <section className="card"><div className="card-h"><h3><span className="ci"><Icon name="bell" /></span>Coming up</h3></div>
            {upcoming.length ? <ul className="feed-l">{upcoming.map((x) => <li key={x.id}><span className="feed-d">{dayLabel(x.date)}</span><span className="feed-t"><b>{x.symbol || x.company}</b> {x.period ? `· ${x.period}` : ""} <small>{x.category}</small></span></li>)}</ul> : <p className="muted">{isLoading ? "Loading…" : onlyMine && !mine.length ? "Add stocks to your watchlist to see their dates here." : "No upcoming dates have been added yet. The FinLit team adds them as companies announce."}</p>}</section>
          <section className="card"><div className="card-h"><h3><span className="ci"><Icon name="notes" /></span>Recently reported</h3></div>
            {declared.length ? <ul className="feed-l">{declared.map((x) => <li key={x.id}><span className="feed-d">{dayLabel(x.date)}</span><span className="feed-t"><Link to={x.symbol ? `/stocks/${x.symbol}#quarter` : "#"}><b>{x.symbol}</b></Link> <small>{x.title}</small>{x.link && <> <a href={x.link} target="_blank" rel="noopener noreferrer">Filing ↗</a></>}</span></li>)}</ul> : <p className="muted">{isLoading ? "Loading…" : "Nothing reported recently."}</p>}</section>
        </aside>
      </div>
    </div>
  );
}
