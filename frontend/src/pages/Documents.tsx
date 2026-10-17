import { useMemo, useState } from "react";
import { Link } from "react-router";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import { dayLabel, docType, useFeed } from "../lib/feed";
import { useWatchlist } from "../lib/watchlist";

const TYPES = ["All", "Annual report", "Investor presentation", "Call transcript", "Offer document", "Results filing", "Other filing"];
const COLOUR: Record<string, string> = { "Annual report": "var(--k1)", "Investor presentation": "var(--k2)", "Call transcript": "var(--k3)", "Offer document": "var(--k7)", "Results filing": "var(--k5)", "Other filing": "var(--k4)" };

export function DocumentsPage() {
  useDocTitle("Documents", "Annual reports, investor presentations, call transcripts and filings for the companies you follow, in one place.");
  const wl = useWatchlist();
  const mine = useMemo(() => [...new Set(wl.lists.flatMap((l) => l.symbols))], [wl]);
  const [onlyMine, setOnlyMine] = useState(false);
  const [type, setType] = useState("All");
  const [q, setQ] = useState("");
  const docs = useFeed("document", { symbols: onlyMine ? mine : [], q: q.trim().length > 1 ? q.trim() : "", limit: 150 });
  const res = useFeed("result", { symbols: onlyMine ? mine : [], q: q.trim().length > 1 ? q.trim() : "", limit: 100 });
  const all = useMemo(() => [...(docs.data || []), ...(res.data || []).filter((r) => r.link)].sort((a, b) => b.date.localeCompare(a.date)), [docs.data, res.data]);
  const shown = all.filter((i) => type === "All" || docType(i) === type);
  const loading = docs.isLoading || res.isLoading;
  return (
    <div className="wrap ipo">
      <header className="dash-h"><div><div className="eyebrow">Library</div><h1>Documents</h1><p className="muted">Annual reports, presentations, transcripts and results filings, linked straight to the exchange. Open any file in a new tab.</p></div>
        <label className="sw"><input type="checkbox" checked={onlyMine} onChange={(e) => setOnlyMine(e.target.checked)} /><span aria-hidden="true" /><b>Only my watchlist{mine.length ? ` (${mine.length})` : ""}</b></label></header>
      <div className="ipo-bar2"><input className="cs-in" aria-label="Search documents" placeholder="Search company or title" value={q} onChange={(e) => setQ(e.target.value)} style={{ minWidth: 260 }} />
        <div className="fchips" role="group" aria-label="Type">{TYPES.map((t) => <button key={t} className={"chip-b" + (type === t ? " on" : "")} aria-pressed={type === t} onClick={() => setType(t)}>{t}</button>)}</div></div>
      {loading && <div className="skeleton" style={{ height: 220 }} />}
      {!loading && !shown.length && <div className="card dw-empty"><span className="dw-ei"><Icon name="book" /></span><b>No documents yet</b><p>Filings appear as companies are loaded.</p></div>}
      <div className="doc-grid">{shown.map((i) => { const t = docType(i); return (
        <article key={i.id} className="card doc-c" style={{ "--tc": COLOUR[t] } as React.CSSProperties}>
          <span className="doc-t"><i />{t}</span><h3>{i.link ? <a href={i.link} target="_blank" rel="noopener noreferrer">{i.title}</a> : i.title}</h3>
          <p>{i.symbol ? <Link to={`/stocks/${i.symbol}`}><b>{i.symbol}</b></Link> : null}{i.company ? ` ${i.company}` : ""} · {dayLabel(i.date)}</p></article>); })}</div>
    </div>
  );
}
