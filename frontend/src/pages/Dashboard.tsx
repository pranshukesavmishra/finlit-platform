// The dashboard: a greeting row (date, market state, followed stocks, Setup chip, Customise), then the blocks in the member's order. Every block can be moved, hidden or resized in Customise;
// on a phone the blocks sit under three tabs (My stocks, Market, News) and the last tab is remembered. Descriptive only, information only.
import { useEffect, useMemo, useState } from "react";
import { Navigate, useSearchParams } from "react-router";
import { useAuth } from "../lib/auth";
import { RANK, useUI } from "../lib/ui";
import { DASH_TABS, WIDGETS, prefs, usePrefs, type DashTab } from "../lib/prefs";
import { useUniverse, type Row } from "../lib/screener";
import { useWatchlist, watch } from "../lib/watchlist";
import { useMyCompanies } from "../lib/mycompanies";
import { useIndices } from "../lib/indices";
import { DEMO } from "../lib/demo";
import { useDocTitle } from "../lib/title";
import { firstName, greetingWord, istHour, longDay, readTab, writeTab } from "../lib/dashboard";
import { Card, useIsPhone } from "../components/dashboard/parts";
import { MyStocks, type Followed } from "../components/dashboard/MyStocks";
import { MarketToday } from "../components/dashboard/MarketToday";
import { Snapshot, Sectors } from "../components/dashboard/Snapshot";
import { Flows } from "../components/dashboard/Flows";
import { Stress } from "../components/dashboard/Stress";
import { IndexHeatmap } from "../components/dashboard/Heatmap";
import { AlertsScreens, Filings, Ipos, Learn, ResultsToday } from "../components/dashboard/NewsBlocks";
import { Buckets, CommoditiesW, DcfW, Locked, Movers, Results, SecondLook } from "../components/dashboard/Legacy";
import { SetupChip, useSetup } from "../components/dashboard/Setup";
import { Customise } from "../components/dashboard/Customise";
import "../styles/dashboard.css";

export function Dashboard() {
  useDocTitle("Dashboard", "Your FinLit dashboard: your stocks today, the market, results and filings, arranged your way.");
  const { user, ready } = useAuth();
  const { plan } = useUI();
  const p = usePrefs();
  const wl = useWatchlist();
  const mine = useMyCompanies();
  const uni = useUniverse();
  const idx = useIndices();
  const phone = useIsPhone();
  const [params, setParams] = useSearchParams();
  const [edit, setEdit] = useState(params.get("edit") === "1");
  const [tab, setTab] = useState<DashTab>(() => readTab(user?.id));
  const rows: Row[] = uni.data?.rows ?? [];
  const bySym = useMemo(() => new Map(rows.map((r) => [r.symbol, r])), [rows]);
  const followed = useMemo<Followed[]>(() => {
    const out: Followed[] = [], seen = new Set<string>();
    for (const c of mine.companies.filter((c) => c.followed)) if (!seen.has(c.symbol)) { seen.add(c.symbol); out.push({ symbol: c.symbol, name: c.name ?? bySym.get(c.symbol)?.name ?? null }); }
    for (const s of wl.lists.flatMap((l) => l.symbols)) if (!seen.has(s)) { seen.add(s); out.push({ symbol: s, name: bySym.get(s)?.name ?? null }); }
    return out;
  }, [mine.companies, wl, bySym]);
  const items = followed.map((f) => bySym.get(f.symbol)).filter((r): r is Row => !!r);
  const sectors = useMemo(() => new Map(rows.map((r) => [r.symbol, r.sector])), [rows]);
  const names = useMemo(() => new Map(rows.map((r) => [r.symbol, r.name])), [rows]);
  const symbols = useMemo(() => followed.map((f) => f.symbol), [followed]);
  const setup = useSetup(followed.length, p.palette, plan);
  // In the demo there is no server: the first nine largest companies stand in for a watchlist.
  useEffect(() => { if (DEMO && !wl.seeded && rows.length) watch.seed([...rows].sort((a, b) => (b.market_cap || 0) - (a.market_cap || 0)).slice(0, 9).map((r) => r.symbol)); }, [rows, wl.seeded]);
  if (!ready) return <div className="wrap state" role="status"><div className="skeleton" style={{ height: 14, width: 200, margin: "40px auto" }} /></div>;
  if (!user) return <Navigate to="/login?next=%2Fdashboard" replace />;

  const meta = Object.fromEntries(WIDGETS.map((w) => [w.id, w]));
  const loadingFollowed = !followed.length && mine.isLoading;
  const loadingRows = uni.isLoading;
  const shown = p.dashboard.filter((w) => w.on && (!phone || meta[w.id].tab === tab));
  const body = (id: string) => {
    const w = meta[id];
    if (RANK[plan] < RANK[w.min]) return <Card id={id} title={w.label}><Locked tier={w.min} label={w.label} /></Card>;
    const legacy = (el: React.ReactNode) => <Card id={id} title={w.label}>{el}</Card>;
    switch (id) {
      case "mystocks": return <MyStocks followed={followed} loading={loadingFollowed} />;
      case "market": return <MarketToday />;
      case "snapshot": return <Snapshot rows={rows} loading={loadingRows} />;
      case "sectors": return <Sectors rows={rows} loading={loadingRows} />;
      case "flows": return <Flows />;
      case "stress": return <Stress followed={followed} loading={loadingFollowed} sectors={sectors} />;
      case "heatmap": return <IndexHeatmap rows={rows} loading={loadingRows} />;
      case "resultstoday": return <ResultsToday symbols={symbols} />;
      case "filings": return <Filings symbols={symbols} />;
      case "ipos": return <Ipos />;
      case "alerts": return <AlertsScreens />;
      case "learn": return <Learn />;
      case "results": return legacy(<Results symbols={symbols.length ? symbols : ["RELIANCE"]} names={names} />);
      case "movers": return legacy(<Movers items={items} />);
      case "second": return legacy(<SecondLook items={items} meta={wl.meta} />);
      case "buckets": return legacy(<Buckets items={items} />);
      case "dcf": return legacy(<DcfW />);
      case "commodities": return legacy(<CommoditiesW />);
      default: return null;
    }
  };
  const pickTab = (t: DashTab) => { setTab(t); writeTab(user.id, t); };
  const name = firstName(user.name, user.email);
  const state = idx.data ? (idx.data.marketOpen ? "Market open" : "Market closed") : null;
  const sub = [longDay(), state, followed.length ? `You follow ${followed.length} stock${followed.length === 1 ? "" : "s"}` : loadingFollowed ? null : "You follow no stocks yet"].filter(Boolean).join(" · ");
  return (
    <div className="wrap dsh" data-tab={tab}>
      <header className="dsh-head">
        <div><div className="dsh-kicker">Dashboard</div><h1>{greetingWord(istHour())}{name ? `, ${name}` : ""}</h1><p className="dsh-meta">{sub}</p></div>
        <div className="dsh-actions"><SetupChip steps={setup.steps} n={setup.n} />
          <button type="button" className="dsh-btn" aria-pressed={edit} onClick={() => { setEdit(!edit); if (params.has("edit")) setParams({}, { replace: true }); }}>{edit ? "Done" : "Customise"}</button></div>
      </header>
      <div className="dsh-tabs" role="tablist" aria-label="Dashboard sections">{DASH_TABS.map((t) => <button key={t.id} type="button" role="tab" id={`dsh-tab-${t.id}`} aria-selected={tab === t.id} aria-controls="dsh-grid" onClick={() => pickTab(t.id)}>{t.label}</button>)}</div>
      {edit && <Customise layout={p.dashboard} plan={plan} onChange={(dashboard) => prefs.set({ dashboard })} onReset={() => prefs.set({ dashboard: [] })} onDone={() => setEdit(false)} />}
      <div className="dsh-grid" id="dsh-grid" role={phone ? "tabpanel" : undefined} aria-labelledby={phone ? `dsh-tab-${tab}` : undefined}>
        {shown.map((w) => <div key={w.id} className={"dsh-cell " + w.size} data-block={w.id}>{body(w.id)}</div>)}
        {!shown.length && <Card id="empty" title="Nothing to show here"><p className="dsh-note">{phone ? "Every block on this tab is switched off." : "Every block is switched off."} <button type="button" className="dsh-link" onClick={() => setEdit(true)}>Open Customise</button> to turn some on.</p></Card>}
      </div>
      <p className="dsh-fine">Describes the company's financial health from its filings and prices; not a recommendation. Information only, not investment advice.</p>
    </div>
  );
}
