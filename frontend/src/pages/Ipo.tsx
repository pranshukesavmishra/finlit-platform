import { useMemo, useState } from "react";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import { listingGain, minInvest, useIpos, type Ipo } from "../lib/ipo";
import { MINUS, nf } from "../lib/format";

const DAY = 86_400_000;
const d0 = (iso: string) => new Date(iso + "T00:00:00").getTime();
const short = (iso: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : "—");
const STATUS: Record<Ipo["status"], { label: string; colour: string }> = { open: { label: "Open now", colour: "var(--gain)" }, upcoming: { label: "Upcoming", colour: "var(--k1)" }, closed: { label: "Closed", colour: "var(--k4)" }, listed: { label: "Listed", colour: "var(--k7)" } };
const money = (v: number | null) => (v == null ? "—" : "₹" + nf(v, v % 1 ? 2 : 0));
const FILTERS = [["all", "All"], ["open", "Open now"], ["upcoming", "Upcoming"], ["closed", "Closed"], ["listed", "Listed"]] as const;

/** A two-month strip: every issue is a bar from its opening to its closing day, so overlaps and quiet weeks are obvious. */
function Strip({ rows }: { rows: Ipo[] }) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const start = today.getTime() - 10 * DAY, span = 50 * DAY;
  const x = (t: number) => Math.max(0, Math.min(100, ((t - start) / span) * 100));
  const show = rows.filter((r) => d0(r.closeDate) >= start && d0(r.openDate) <= start + span).slice(0, 8);
  const days = Array.from({ length: 11 }, (_, i) => start + i * 5 * DAY);
  return (
    <div className="ipo-strip" role="img" aria-label="Timeline of open and upcoming issues">
      <div className="ipo-axis">{days.map((t) => <span key={t} style={{ left: `${x(t)}%` }}>{new Date(t).toLocaleDateString("en-IN", { day: "numeric", month: "short" })}</span>)}</div>
      <div className="ipo-rows">
        <i className="ipo-today" style={{ left: `${x(today.getTime())}%` }}><b>Today</b></i>
        {show.length ? show.map((r) => (
          <div className="ipo-row" key={r.id}><span className="ipo-bar" style={{ left: `${x(d0(r.openDate))}%`, width: `${Math.max(1.6, x(d0(r.closeDate) + DAY) - x(d0(r.openDate)))}%`, background: STATUS[r.status].colour }} title={`${r.name}: ${short(r.openDate)} to ${short(r.closeDate)}`} />
            <em style={{ left: `${Math.min(x(d0(r.closeDate) + DAY) + 1, 70)}%` }}>{r.name}</em></div>)) : <p className="muted" style={{ padding: "18px 4px" }}>No issues in this window.</p>}
      </div>
    </div>
  );
}

export function IpoPage() {
  useDocTitle("IPO calendar", "Open, upcoming and recently listed IPOs in India: dates, price band, lot size, minimum investment and listing gain.");
  const { data, isLoading, isError } = useIpos();
  const [f, setF] = useState<(typeof FILTERS)[number][0]>("all");
  const [kind, setKind] = useState<"all" | "mainboard" | "sme">("all");
  const [q, setQ] = useState("");
  const rows = data || [];
  const by = (s: Ipo["status"]) => rows.filter((r) => r.status === s);
  const shown = useMemo(() => rows.filter((r) => (f === "all" || r.status === f) && (kind === "all" || r.kind === kind) && (!q.trim() || r.name.toLowerCase().includes(q.trim().toLowerCase()))).sort((a, b) => {
    const rank = { open: 0, upcoming: 1, closed: 2, listed: 3 } as const;
    return rank[a.status] - rank[b.status] || (a.status === "upcoming" ? d0(a.openDate) - d0(b.openDate) : d0(b.openDate) - d0(a.openDate));
  }), [rows, f, kind, q]);
  const month = rows.filter((r) => r.status === "listed" && Date.now() - d0(r.listingDate || r.closeDate) < 31 * DAY);
  const avgGain = (() => { const g = month.map(listingGain).filter((v): v is number => v != null); return g.length ? g.reduce((a, b) => a + b, 0) / g.length : null; })();

  return (
    <div className="wrap ipo">
      <header className="dash-h"><div><div className="eyebrow">Market</div><h1>IPO calendar</h1><p className="muted">Issues that are open, coming up and recently listed, updated automatically from exchange data. For information only; read the offer document before you apply.</p></div></header>
      <div className="ipo-k">
        {([["open", "Open now", by("open").length], ["upcoming", "Upcoming", by("upcoming").length], ["listed", "Listed in the last 30 days", month.length]] as const).map(([k, l, n]) => <div key={k} className="card ipo-t" style={{ "--tc": STATUS[k].colour } as React.CSSProperties}><b>{n}</b><span>{l}</span></div>)}
        <div className="card ipo-t" style={{ "--tc": "var(--k3)" } as React.CSSProperties}><b className={avgGain == null ? "" : avgGain >= 0 ? "up" : "down"}>{avgGain == null ? "—" : (avgGain >= 0 ? "+" : MINUS) + nf(Math.abs(avgGain), 1) + "%"}</b><span>Average listing gain (last 30 days)</span></div>
      </div>
      <section className="card ipo-s"><div className="card-h"><h3><span className="ci"><Icon name="calendar" /></span>Next seven weeks</h3><span className="s">Bar = application window</span></div>{isLoading ? <div className="skeleton" style={{ height: 160 }} /> : <Strip rows={rows} />}
        <div className="clg">{(Object.keys(STATUS) as Ipo["status"][]).map((s) => <span key={s}><i style={{ background: STATUS[s].colour }} />{STATUS[s].label}</span>)}</div></section>
      <div className="ipo-bar2">
        <div className="seg" role="group" aria-label="Status">{FILTERS.map(([k, l]) => <button key={k} aria-pressed={f === k} onClick={() => setF(k)}>{l}</button>)}</div>
        <div className="seg" role="group" aria-label="Board">{([["all", "All boards"], ["mainboard", "Mainboard"], ["sme", "SME"]] as const).map(([k, l]) => <button key={k} aria-pressed={kind === k} onClick={() => setKind(k)}>{l}</button>)}</div>
        <input className="cs-in" aria-label="Search IPOs" placeholder="Search company" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      {isError && <div className="formerr">The calendar could not be loaded. Please try again shortly.</div>}
      {!isLoading && !isError && !rows.length && <div className="card dw-empty"><span className="dw-ei"><Icon name="calendar" /></span><b>No issues listed yet</b><p>The calendar is updated by the FinLit team. Check back soon.</p></div>}
      <div className="ipo-list">
        {shown.map((r) => { const g = listingGain(r), mi = minInvest(r), st = STATUS[r.status]; return (
          <article key={r.id} className="card ipo-c" style={{ "--tc": st.colour } as React.CSSProperties}>
            <div className="ipo-h"><div><h3>{r.name}</h3><p>{r.sector || "—"} · {r.kind === "sme" ? "SME" : "Mainboard"}{r.symbol ? ` · ${r.symbol}` : ""}</p></div><span className="ipo-st"><i />{st.label}</span></div>
            <dl className="ipo-d">
              <div><dt>Opens</dt><dd>{short(r.openDate)}</dd></div><div><dt>Closes</dt><dd>{short(r.closeDate)}</dd></div><div><dt>Lists</dt><dd>{short(r.listingDate)}</dd></div>
              <div><dt>Price band</dt><dd>{r.priceLow != null && r.priceHigh != null ? `${money(r.priceLow)} – ${money(r.priceHigh)}` : money(r.priceHigh)}</dd></div>
              <div><dt>Lot size</dt><dd>{r.lotSize ?? "—"}{r.lotSize ? " shares" : ""}</dd></div><div><dt>Minimum to apply</dt><dd>{mi != null ? "₹" + nf(mi, 0) : "—"}</dd></div>
              <div><dt>Issue size</dt><dd>{r.issueSizeCr != null ? `₹${nf(r.issueSizeCr, 0)} Cr` : "—"}</dd></div>
              {r.status === "listed" && <div><dt>Listing gain</dt><dd className={g == null ? "" : g >= 0 ? "up" : "down"}>{g == null ? "—" : (g >= 0 ? "▲ +" : "▼ " + MINUS) + nf(Math.abs(g), 1) + "%"}</dd></div>}
            </dl>
            {(r.note || r.link) && <p className="ipo-n">{r.note}{r.link && <> <a href={r.link} target="_blank" rel="noopener noreferrer">Offer document ↗</a></>}</p>}
          </article>); })}
      </div>
      {rows.length > 0 && !shown.length && <p className="muted" style={{ padding: 24, textAlign: "center" }}>No issues match these filters.</p>}
    </div>
  );
}
