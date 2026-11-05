// Blocks 8 to 12: Results today, Filings and news, IPOs open now, Alerts and saved screens, Term of the day.
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { useFeed, who } from "../../lib/feed";
import { useIpos } from "../../lib/ipo";
import { useAlerts } from "../../lib/alerts";
import { useSavedScreens } from "../../lib/screens";
import { encodeState, toBody, useScreen, type PState } from "../../lib/proscreen";
import { dedupeFilings, filingLine, filingTag, istToday, resultLines, shortDay, titleCase } from "../../lib/dashboard";
import { nf } from "../../lib/format";
import { Card, Rows, ScopeSeg, useScope } from "./parts";

export function ResultsToday({ symbols }: { symbols: string[] }) {
  const [scope, setScope] = useScope("resultstoday", symbols.length > 0);
  const q = useFeed("result", { symbols: scope === "mine" ? symbols : [], limit: 100, upcoming: true });
  const today = istToday(), end = new Date(Date.parse(today + "T00:00:00Z") + 7 * 864e5).toISOString().slice(0, 10);
  const lines = resultLines((q.data || []).filter((i) => i.date >= today && i.date <= end)).slice(0, 6);
  return (
    <Card id="resultstoday" title="Results today" sub="Filed or due today, and the next few days" right={<ScopeSeg label="Results" scope={scope} onChange={setScope} hasStocks={symbols.length > 0} />}>
      {q.isLoading ? <Rows n={4} h={46} /> : q.isError ? <p className="dsh-note">Results are not available right now.</p> : !lines.length ? <p className="dsh-note">{scope === "mine" ? "No results due for your stocks this week." : "No company has filed or announced a results date for this week yet."}</p> :
        <div className="dsh-lines">{lines.map((l) => <Link key={l.key} to={l.symbol ? `/stocks/${l.symbol}` : "/results"} className="dsh-line2"><span><b>{who(l)}</b><span>{l.text}</span></span><em>{shortDay(l.date, today)}</em></Link>)}</div>}
      <Link className="dsh-link foot" to="/results">Results calendar →</Link>
    </Card>
  );
}

export function Filings({ symbols }: { symbols: string[] }) {
  const [scope, setScope] = useScope("filings", symbols.length > 0);
  const q = useFeed("news", { symbols: scope === "mine" ? symbols : [], limit: 40 });
  const today = istToday(), items = dedupeFilings(q.data || []).slice(0, 5);
  return (
    <Card id="filings" title="Filings and news" sub="Exchange filings, newest first" right={<ScopeSeg label="Filings" scope={scope} onChange={setScope} hasStocks={symbols.length > 0} />}>
      {q.isLoading ? <Rows n={5} h={46} /> : q.isError ? <p className="dsh-note">Filings are not available right now.</p> : !items.length ? <p className="dsh-note">{scope === "mine" ? "No new filings for your stocks." : "No new exchange filings yet."}</p> :
        <div className="dsh-lines">{items.map((x) => <Link key={x.id} to="/news" className="dsh-line2 f"><span className="hd"><b>{who(x) || "Market"}</b><i className="dsh-tag">{filingTag(x)}</i><em>{shortDay(x.date, today)}</em></span><span className="tx">{filingLine(x)}</span></Link>)}</div>}
      <Link className="dsh-link foot" to="/news">All news and filings →</Link>
    </Card>
  );
}

export function Ipos() {
  const q = useIpos(), today = istToday();
  const all = (q.data || []).filter((i) => i.status === "open" || i.status === "upcoming").sort((a, b) => (a.status === b.status ? a.openDate.localeCompare(b.openDate) : a.status === "open" ? -1 : 1));
  const open = all.filter((i) => i.status === "open"), list = (open.length ? open : all).slice(0, 4);
  const detail = (i: (typeof all)[number]) => {
    const band = i.priceHigh ? (i.priceLow && i.priceLow < i.priceHigh ? `Price band ₹${nf(i.priceLow, 0)} to ₹${nf(i.priceHigh, 0)}` : `Price band up to ₹${nf(i.priceHigh, 0)}`) : "";
    const when = i.status === "open" ? (i.closeDate ? `closes ${shortDay(i.closeDate, today)}` : "") : `opens ${shortDay(i.openDate, today)}`;
    return [band, when].filter(Boolean).join(" · ") || "Details soon";
  };
  return (
    <Card id="ipos" title="IPOs open now">
      {q.isLoading ? <Rows n={2} h={44} /> : q.isError ? <p className="dsh-note">IPO details are not available right now.</p> : !list.length ? <p className="dsh-note">No IPO is open or announced right now.</p> :
        <div className="dsh-lines">{list.map((i) => <Link key={i.id} to="/ipo" className="dsh-ipo"><b>{titleCase(i.name)}</b><span>{detail(i)}</span></Link>)}</div>}
      <Link className="dsh-link foot" to="/ipo">IPO calendar →</Link>
    </Card>
  );
}

function ScreenCount({ state }: { state: PState & { sort?: string; dir?: "asc" | "desc" } }) {
  const q = useScreen(toBody(state, { key: state.sort || "market_cap", dir: state.dir || "desc" } as never, [], "", 0, 1), true);
  return <span>{q.data ? `${nf(q.data.total, 0)} match` : q.isError ? "—" : "…"}</span>;
}
export function AlertsScreens() {
  const { alerts } = useAlerts(), saved = useSavedScreens();
  const live = alerts.filter((a) => a.status !== "done" || a.lastFiredAt).sort((a, b) => Number(!!b.met) - Number(!!a.met)).slice(0, 4);
  return (
    <Card id="alerts" title="Alerts and saved screens">
      {!live.length && !saved.length ? <><p className="dsh-p">No alerts or saved screens yet. Get told when a price, score or filing crosses your line.</p>
        <div className="dsh-btns"><Link className="dsh-btn dark" to="/alerts">Create an alert</Link><Link className="dsh-btn" to="/screener">Open screener</Link></div></> : <>
        {live.length > 0 && <><div className="dsh-lh first">Alerts</div><div className="dsh-lines">{live.map((a) => <Link key={a.id} to="/alerts" className="dsh-ipo"><b>{a.symbol} <i className={"dsh-tag" + (a.met ? " on" : "")}>{a.met ? "Triggered" : a.status === "paused" ? "Paused" : "Active"}</i></b><span>{a.label}</span></Link>)}</div></>}
        {saved.length > 0 && <><div className="dsh-lh">Saved screens</div><div className="dsh-lines">{saved.slice(0, 4).map((s) => {
          const st = s.state as unknown as PState & { sort?: string; dir?: "asc" | "desc" }, pro = !!st && typeof st === "object" && !!st.ranges;
          return <Link key={s.name} to={pro ? `/screener?s=${encodeState(st, st.sort || "market_cap", st.dir || "desc")}` : "/screener"} className="dsh-ipo"><b>{s.name}</b><span>{pro ? <ScreenCount state={st} /> : "Open"}</span></Link>; })}</div></>}
        <Link className="dsh-link foot" to="/alerts">Manage alerts →</Link></>}
    </Card>
  );
}

export function Learn() {
  const [t, setT] = useState<{ term: string; topic: string; meaning: string; id: string } | null>(null);
  useEffect(() => { import("../../lib/glossary").then((g) => setT(g.termOfTheDay())); }, []);
  return (
    <section className="dsh-card dsh-term" aria-labelledby="dsh-learn">
      {!t ? <Rows n={3} h={28} /> : <><div className="dsh-kicker">Term of the day · {t.topic}</div><h2 id="dsh-learn">{t.term}</h2><p className="dsh-p">{t.meaning}</p><Link className="dsh-link" to={"/glossary#" + t.id}>Open the glossary →</Link></>}
    </section>
  );
}
