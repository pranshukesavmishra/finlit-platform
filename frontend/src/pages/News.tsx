import { PageHeader } from "../components/PageHeader";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import { dayLabel, useFeed, type FeedItem } from "../lib/feed";
import { useWatchlist } from "../lib/watchlist";

const RESULTS = "Quarterly results";
/** A company's results filing: the exchange's own category or the headline names financial results, the quarter ended, or an integrated filing of financials. */
const isResults = (i: FeedItem) => /financial results?|quarterly results?|integrated filing.{0,3}financial|results? for the (quarter|year|half)/i.test(i.category || "") || /(un)?audited.{0,40}results?|financial results?|quarterly results?|results? for the (quarter|year|half)|quarter ended|half year ended|integrated filing.{0,3}financial/i.test(i.title || "");

export function NewsPage() {
  useDocTitle("News and filings", "Company announcements and curated market news: filter by company, category or your own watchlist.");
  const wl = useWatchlist();
  const mine = useMemo(() => [...new Set(wl.lists.flatMap((l) => l.symbols))], [wl]);
  const [onlyMine, setOnlyMine] = useState(false);
  const [cat, setCat] = useState("All");   // "All", a category, or RESULTS (the quarterly results filings, found by their wording)
  const [q, setQ] = useState("");
  const { data, isLoading, isError } = useFeed("news", { scoped: onlyMine, symbols: onlyMine ? mine : [], q: q.trim().length > 1 ? q.trim() : "", limit: 150 });
  const cats = useMemo(() => ["All", RESULTS, ...[...new Set((data || []).map((i) => i.category).filter((c): c is string => !!c))].sort()], [data]);
  const nResults = useMemo(() => (data || []).filter(isResults).length, [data]);
  const shown = (data || []).filter((i) => cat === "All" || (cat === RESULTS ? isResults(i) : i.category === cat));
  const groups = useMemo(() => { const m = new Map<string, FeedItem[]>(); shown.forEach((i) => m.set(i.date, [...(m.get(i.date) || []), i])); return [...m.entries()]; }, [shown]);
  return (
    <div className="wrap ipo">
      <PageHeader plan="free" title="News & filings" art="news" links={["/results", "/documents", "/ipo"]} actions={<label className="sw"><input type="checkbox" checked={onlyMine} onChange={(e) => setOnlyMine(e.target.checked)} /><span aria-hidden="true" /><b>Only my watchlist{mine.length ? ` (${mine.length})` : ""}</b></label>}
        description={<>Exchange announcements for <b>every company we cover</b>, plus market news chosen by the FinLit team.</>} />
      <div className="ipo-bar2"><input className="cs-in" aria-label="Search news" placeholder="Search company or headline" value={q} onChange={(e) => setQ(e.target.value)} style={{ minWidth: 260 }} />
        <div className="fchips" role="group" aria-label="Category">{cats.slice(0, 13).map((c) => <button key={c} className={"chip-b" + (cat === c ? " on" : "")} aria-pressed={cat === c} onClick={() => setCat(c)}>{c}{c === RESULTS && data ? ` (${nResults})` : ""}</button>)}</div></div>
      {isError && <div className="formerr">News could not be loaded. Please try again shortly.</div>}
      {isLoading && <div className="skeleton" style={{ height: 240 }} />}
      {!isLoading && !shown.length && <div className="card dw-empty"><span className="dw-ei"><Icon name="notes" /></span><b>{onlyMine && !mine.length ? "Your watchlist is empty" : "Nothing here yet"}</b><p>{onlyMine && !mine.length ? "Add stocks to a watchlist to follow their announcements." : "Announcements appear as companies are loaded."}</p>{onlyMine && !mine.length && <Link className="btn" to="/watchlist">Open watchlist</Link>}</div>}
      {groups.map(([day, items]) => (
        <section key={day} className="feed-g"><h2>{dayLabel(day)}</h2>
          <div className="card feed-card"><ul className="feed-n">{items.map((i) => (
            <li key={i.id}>{i.symbol ? <Link className="feed-sym" to={`/stocks/${i.symbol}`}>{i.symbol}</Link> : <span className="feed-sym alt">Market</span>}
              <div><p>{i.link ? <a href={i.link} target="_blank" rel="noopener noreferrer">{i.title}</a> : i.title}</p><small>{[i.category, i.company && i.symbol ? i.company : null, i.source].filter(Boolean).join(" · ")}</small>{i.summary && <p className="muted" style={{ margin: "4px 0 0", fontSize: 14 }}>{i.summary}</p>}</div></li>))}</ul></div></section>))}
    </div>
  );
}
