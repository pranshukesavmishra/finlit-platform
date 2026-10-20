import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { apiGet, type Financials } from "../lib/api";
import { useAuth } from "../lib/auth";
import { RANK, TIER, useUI, type Plan } from "../lib/ui";
import { PALETTES, PALETTE_IDS } from "../lib/palettes";
import { WIDGETS, prefs, usePrefs, type WidgetPref } from "../lib/prefs";
import { BAND_LABEL, useUniverse, type Row } from "../lib/screener";
import { useSavedScreens } from "../lib/screens";
import { useWatchlist, watch } from "../lib/watchlist";
import { DEMO } from "../lib/demo";
import { signals } from "./Watchlist";
import { MiniBars } from "../charts/MiniBars";
import { Icon } from "../lib/icons";
import { MINUS, cr, nf } from "../lib/format";
import { useDocTitle } from "../lib/title";
import terms from "../content/glossary.json";
import { dayLabel, useFeed, who } from "../lib/feed";
import { encodeState, toBody, useScreen, type PState } from "../lib/proscreen";
import { useIpos } from "../lib/ipo";
import { useAlerts } from "../lib/alerts";
import { ChartHelp } from "../components/ChartHelp";

const greeting = () => { const h = new Date().getHours(); return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"; };
const sgn = (v: number | null | undefined, d = 1) => (v == null ? "—" : (v > 0 ? "+" : v < 0 ? MINUS : "") + nf(v, d) + "%");
const tone = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "up" : "down");

function Empty({ icon, title, text, to, cta }: { icon: string; title: string; text: string; to: string; cta: string }) {
  return <div className="dw-empty"><span className="dw-ei"><Icon name={icon} /></span><b>{title}</b><p>{text}</p><Link className="btn" to={to}>{cta}</Link></div>;
}

/* ---------------- widgets ---------------- */
function Snapshot({ rows }: { rows: Row[] }) {
  const m = useMemo(() => {
    // suspended or delisted companies have no price and a -100% "change"; leave them out of breadth and movers
    const live = rows.filter((r) => r.change_pct != null && (r.price ?? 0) > 0);
    const adv = live.filter((r) => (r.change_pct as number) > 0).length, dec = live.filter((r) => (r.change_pct as number) < 0).length;
    const by = new Map<string, number[]>();
    live.forEach((r) => by.set(r.sector || "Other", [...(by.get(r.sector || "Other") || []), r.change_pct as number]));
    const sectors = [...by.entries()].map(([s, v]) => ({ s, v: v.reduce((a, b) => a + b, 0) / v.length, n: v.length })).sort((a, b) => b.n - a.n).slice(0, 12);
    const sorted = live.filter((r) => (r.market_cap ?? 0) >= 100).sort((a, b) => (b.change_pct as number) - (a.change_pct as number));
    return { n: live.length, adv, dec, sectors, up: sorted.slice(0, 4), down: sorted.slice(-4).reverse() };
  }, [rows]);
  if (!m.n) return <p className="muted">Market data is on its way.</p>;
  const max = Math.max(...m.sectors.map((x) => Math.abs(x.v)), 0.5);
  return (
    <div className="dw-snap">
      <div>
        <div className="label">Market breadth · {m.n} companies</div>
        <div className="breadth" role="img" aria-label={`${m.adv} rising, ${m.dec} falling`}><i className="up" style={{ flex: m.adv || 0.01 }} /><i className="flat" style={{ flex: Math.max(m.n - m.adv - m.dec, 0.01) }} /><i className="down" style={{ flex: m.dec || 0.01 }} /></div>
        <div className="breadth-k"><span className="up">{m.adv} rising</span><span className="down">{m.dec} falling</span></div>
        <div className="movers2"><div><div className="label">Top gainers</div>{m.up.map((r) => <Link key={r.symbol} to={`/stocks/${r.symbol}`}><b>{r.symbol}</b><span className="up">{sgn(r.change_pct)}</span></Link>)}</div>
          <div><div className="label">Top decliners</div>{m.down.map((r) => <Link key={r.symbol} to={`/stocks/${r.symbol}`}><b>{r.symbol}</b><span className="down">{sgn(r.change_pct)}</span></Link>)}</div></div>
      </div>
      <div>
        <div className="label">Sectors today</div>
        <div className="heat">{m.sectors.map((x) => <div key={x.s} className={"hc " + tone(x.v)} style={{ "--k": Math.min(1, Math.abs(x.v) / max) } as React.CSSProperties} title={`${x.s}: ${sgn(x.v)}`}><b>{x.s}</b><span>{sgn(x.v)}</span></div>)}</div>
      </div>
    </div>
  );
}

const HELP: Record<string, string> = { snapshot: "dash-snapshot", results: "dash-results", movers: "dash-movers", second: "dash-second", buckets: "dash-buckets" };

function Movers({ items }: { items: Row[] }) {
  const top = [...items].filter((r) => r.change_pct != null).sort((a, b) => Math.abs(b.change_pct as number) - Math.abs(a.change_pct as number)).slice(0, 7);
  if (!items.length) return <Empty icon="wallet" title="No stocks yet" text="Add stocks to a watchlist to see how they moved today." to="/watchlist" cta="Open watchlist" />;
  const max = Math.max(...top.map((r) => Math.abs(r.change_pct as number)), 1);
  return (
    <ul className="dv">{top.map((r) => (
      <li key={r.symbol}><Link to={`/stocks/${r.symbol}`}><b>{r.symbol}</b><small>{r.name}</small></Link>
        <span className="dvbar" aria-hidden="true"><i className={tone(r.change_pct)} style={{ width: `${(Math.abs(r.change_pct as number) / max) * 50}%`, [(r.change_pct as number) >= 0 ? "left" : "right"]: "50%" }} /></span>
        <span className={"dvv " + tone(r.change_pct)}>{sgn(r.change_pct)}</span></li>))}</ul>
  );
}

function ResultCard({ symbol, name }: { symbol: string; name: string | null }) {
  const { data, isError } = useQuery({ queryKey: ["stock", symbol, "/financials"], queryFn: () => apiGet<Financials>(`/api/stocks/${symbol}/financials`), staleTime: 60_000, retry: false });
  const q = data?.quarterly.pl;
  if (isError || (data && (!q || q.periods.length < 2))) return null;
  if (!q) return <div className="rc"><div className="skeleton" style={{ height: 120 }} /></div>;
  const n = q.periods.length, last = n - 1, yoy = n >= 5 ? n - 5 : -1;
  const ch = (a?: number | null, b?: number | null) => (a == null || b == null || !b ? null : ((a - b) / Math.abs(b)) * 100);
  const rev = q.rows.revenue as (number | null)[], np = q.rows.net_profit as (number | null)[];
  const line = (label: string, v: (number | null)[]) => (
    <div className="rc-r"><span>{label}</span><b>{v[last] == null ? "—" : (v[last]! < 0 ? MINUS : "") + "₹" + cr(Math.abs(v[last] as number))} Cr</b>
      <span className={"qd " + tone(ch(v[last], yoy >= 0 ? v[yoy] : null))}>{sgn(ch(v[last], yoy >= 0 ? v[yoy] : null))} <small>YoY</small></span>
      <span className={"qd " + tone(ch(v[last], v[last - 1]))}>{sgn(ch(v[last], v[last - 1]))} <small>QoQ</small></span></div>
  );
  return (
    <Link className="rc" to={`/stocks/${symbol}#quarter`}>
      <div className="rc-h"><b>{symbol}</b><small>{name} · {q.periods[last]}</small></div>
      {line("Revenue", rev)}{line("Net profit", np)}
      <MiniBars labels={q.periods.slice(-6)} series={[{ key: "np", label: "Net profit", values: np.slice(-6), color: "var(--gold)" }]} fmt={(v) => cr(v)} height={86} w={260} highlight={5} />
    </Link>
  );
}
function Results({ symbols, names }: { symbols: string[]; names: Map<string, string | null> }) {
  if (!symbols.length) return <Empty icon="notes" title="Pick stocks to follow" text="Your watchlist's newest quarterly results appear here, compared with last quarter and last year." to="/watchlist" cta="Build a watchlist" />;
  return <div className="rcs">{symbols.slice(0, 4).map((s) => <ResultCard key={s} symbol={s} name={names.get(s) ?? null} />)}</div>;
}

function SecondLook({ items, meta }: { items: Row[]; meta: Record<string, { target?: number }> }) {
  const flagged = items.map((r) => ({ r, s: signals(r, meta[r.symbol]?.target) })).filter((x) => x.s.length).slice(0, 5);
  if (!items.length) return <Empty icon="quality" title="Nothing to review yet" text="Add stocks to your watchlist and FinLit flags the ones that need a second look." to="/watchlist" cta="Open watchlist" />;
  if (!flagged.length) return <p className="muted dw-ok"><Icon name="check" /> Nothing in your watchlist needs attention right now.</p>;
  return <ul className="sl">{flagged.map(({ r, s }) => <li key={r.symbol}><Link to={`/stocks/${r.symbol}`}><b>{r.symbol}</b>{r.band && <span className={"band-dot " + r.band}>{BAND_LABEL[r.band]}</span>}</Link><span>{s[0]}</span></li>)}</ul>;
}

/** How many companies a saved screen matches today, asked of the screener itself (the browser's company list does not carry the screener's 170 filters). */
function ScreenCount({ state }: { state: PState & { sort?: string; dir?: "asc" | "desc" } }) {
  const q = useScreen(toBody(state, { key: state.sort || "market_cap", dir: state.dir || "desc" } as never, [], "", 0, 1), true);
  return <span className="muted">{q.data ? `${nf(q.data.total, 0)} match` : q.isError ? "—" : "…"}</span>;
}

function Screens() {
  const saved = useSavedScreens();
  if (!saved.length) return <Empty icon="table" title="No saved screens" text="Save a set of filters in the screener and track how many companies match." to="/screener" cta="Open screener" />;
  return <ul className="sv">{saved.slice(0, 6).map((s) => {
    const st = s.state as unknown as PState & { sort?: string; dir?: "asc" | "desc" };
    const pro = !!st && typeof st === "object" && !!st.ranges;   // screens saved by the full screener; older ones from the simple screener are opened empty
    return <li key={s.name}><Link to={pro ? `/screener?s=${encodeState(st, st.sort || "market_cap", st.dir || "desc")}` : "/screener"}><b>{s.name}</b>{pro ? <ScreenCount state={st} /> : <span className="muted">Open</span>}</Link></li>;
  })}</ul>;
}

function Buckets({ items }: { items: Row[] }) {
  const order = ["strong", "healthy", "mixed", "watch"] as const;
  const colour: Record<string, string> = { strong: "var(--v-strong)", healthy: "var(--v-healthy)", mixed: "var(--v-mixed)", watch: "var(--v-weak)" };
  const counts = order.map((b) => ({ b, n: items.filter((r) => r.band === b).length }));
  const total = counts.reduce((a, c) => a + c.n, 0);
  if (!total) return <Empty icon="layers" title="No scored stocks" text="Add stocks to a watchlist to see them grouped by FinLit band." to="/watchlist" cta="Open watchlist" />;
  return (
    <div><div className="breadth big" role="img" aria-label="Watchlist by band">{counts.filter((c) => c.n).map((c) => <i key={c.b} style={{ flex: c.n, background: colour[c.b] }} />)}</div>
      <ul className="bandk">{counts.map((c) => <li key={c.b}><i style={{ background: colour[c.b] }} /><span>{BAND_LABEL[c.b]}</span><b>{c.n}</b></li>)}</ul></div>
  );
}

function Dates({ symbols }: { symbols: string[] }) {
  const { data } = useFeed("result", { symbols, limit: 100, upcoming: true });
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
  const next = (data || []).filter((i) => i.date >= today).sort((a, b) => a.date.localeCompare(b.date)).slice(0, 6);
  if (!next.length) return <Empty icon="calendar" title="No dates yet" text={symbols.length ? "None of your stocks has announced a results date yet." : "Result dates appear here as companies announce them."} to="/results" cta="Open results calendar" />;
  return <ul className="sl">{next.map((x) => <li key={x.id}><Link to={x.symbol ? `/stocks/${x.symbol}` : "/results"}><b>{who(x)}</b><span className="chip">{dayLabel(x.date)}</span></Link><span>{x.period || x.category}</span></li>)}</ul>;
}
function NewsW({ symbols }: { symbols: string[] }) {
  const { data } = useFeed("news", { symbols, limit: 6 });
  if (!(data || []).length) return <Empty icon="notes" title="No announcements yet" text={symbols.length ? "Nothing new for your stocks." : "Follow stocks to see their announcements here."} to="/news" cta="Open news" />;
  return <ul className="sl">{data!.map((x) => <li key={x.id}><Link to="/news"><b>{x.symbol || "Market"}</b><span className="muted">{dayLabel(x.date)}</span></Link><span>{x.title}</span></li>)}</ul>;
}
function IposW() {
  const { data } = useIpos();
  const live = (data || []).filter((i) => i.status === "open" || i.status === "upcoming").sort((a, b) => a.openDate.localeCompare(b.openDate)).slice(0, 5);
  if (!live.length) return <Empty icon="calendar" title="No open IPOs" text="Nothing is open or announced right now." to="/ipo" cta="Open IPO calendar" />;
  return <ul className="sl">{live.map((i) => <li key={i.id}><Link to="/ipo"><b>{i.name}</b><span className={"chip " + (i.status === "open" ? "up" : "")}>{i.status === "open" ? "Open now" : "Opens " + dayLabel(i.openDate)}</span></Link><span>{i.priceHigh ? `Price band up to ₹${i.priceHigh}` : ""}{i.lotSize ? ` · lot ${i.lotSize}` : ""}</span></li>)}</ul>;
}

function Learn() {
  const t = useMemo(() => { const all = terms as { t: string; d: string; c: string }[]; const day = Math.floor(Date.now() / 86_400_000); return all[day % all.length]; }, []);
  return <div className="learn"><span className="chip gold">{t.c}</span><h4>{t.t}</h4><p>{t.d}</p><Link to="/glossary">Open the glossary <Icon name="arrow" /></Link></div>;
}

/* ---------------- page ---------------- */
function Locked({ tier, label }: { tier: Plan; label: string }) {
  const { upgrade } = useUI();
  return <div className="dw-lock"><span className="dw-ei"><Icon name="lock" /></span><b>{label}</b><p>Part of the {TIER[tier].n} plan.</p><button className="btn" onClick={() => upgrade(tier, `${label} is part of ${TIER[tier].n}.`)}>Unlock with {TIER[tier].n}</button></div>;
}


/** First-visit checklist: shows what to try next and ticks itself off as the member does each thing. */
function GettingStarted({ followed, palette, plan }: { followed: number; palette: string; plan: string }) {
  const { alerts } = useAlerts();
  const [gone, setGone] = useState(() => { try { return localStorage.getItem("finlit-welcome-off") === "1"; } catch { return false; } });
  const [seen, setSeen] = useState(() => { try { return localStorage.getItem("finlit-welcome-report") === "1"; } catch { return false; } });
  const mark = () => { setSeen(true); try { localStorage.setItem("finlit-welcome-report", "1"); } catch { /* private mode */ } };
  const steps: { done: boolean; t: string; d: string; to: string; cta: string; onClick?: () => void }[] = [
    { done: true, t: "Create your account", d: "You are in. Your plan, lists and colours now follow you across devices.", to: "/account", cta: "Review account" },
    { done: seen, t: "Open a company report", d: "Every listed stock has one: statements, ratios, peers, ownership and price.", to: "/research", cta: "Find a company", onClick: mark },
    { done: followed > 0, t: "Follow a stock", d: plan === "basic" ? "Watchlists are part of Silver. Unlock them any time." : "Add stocks to a watchlist to see them here every day.", to: plan === "basic" ? "/plans" : "/watchlist", cta: plan === "basic" ? "See Silver" : "Open watchlist" },
    { done: alerts.length > 0, t: "Set your first alert", d: "Be told when a price, RSI, score, result or filing crosses your line.", to: "/alerts", cta: "Create an alert" },
    { done: palette !== "gold", t: "Make it yours", d: "Pick a colour palette and choose the dashboard widgets you want.", to: "/account/appearance", cta: "Open appearance" },
  ];
  const n = steps.filter((x) => x.done).length;
  if (gone || n === steps.length) return null;
  return (
    <section className="card gs" aria-label="Getting started">
      <div className="gs-h"><div><h2>Get started with FinLit</h2><p className="muted">{n} of {steps.length} done. A few minutes to get the most from your account.</p></div>
        <button className="alx-link" onClick={() => { setGone(true); try { localStorage.setItem("finlit-welcome-off", "1"); } catch { /* private mode */ } }}>Hide</button></div>
      <div className="gs-bar" role="progressbar" aria-valuemin={0} aria-valuemax={steps.length} aria-valuenow={n}><i style={{ width: `${(n / steps.length) * 100}%` }} /></div>
      <ol className="gs-l">{steps.map((x) => (
        <li key={x.t} className={x.done ? "is-done" : ""}><span className="gs-c" aria-hidden="true">{x.done ? <Icon name="check" /> : null}</span><div><b>{x.t}</b><span>{x.d}</span></div>{!x.done && <Link className="btn" to={x.to} onClick={x.onClick}>{x.cta}</Link>}</li>
      ))}</ol>
    </section>
  );
}

export function Dashboard() {
  useDocTitle("Dashboard", "Your FinLit dashboard: watchlist moves, latest results, saved screens and signals, arranged your way.");
  const { user, ready } = useAuth();
  const { plan } = useUI();
  const p = usePrefs();
  const wl = useWatchlist();
  const { data } = useUniverse();
  const [params, setParams] = useSearchParams();
  const [edit, setEdit] = useState(params.get("edit") === "1");
  const rows = data?.rows || [];
  const bySym = useMemo(() => new Map(rows.map((r) => [r.symbol, r])), [rows]);
  const names = useMemo(() => new Map(rows.map((r) => [r.symbol, r.name])), [rows]);
  const followed = useMemo(() => [...new Set(wl.lists.flatMap((l) => l.symbols))], [wl]);
  const items = followed.map((s) => bySym.get(s)).filter((r): r is Row => !!r);
  useEffect(() => { if (DEMO && !wl.seeded && rows.length) watch.seed([...rows].sort((a, b) => (b.market_cap || 0) - (a.market_cap || 0)).slice(0, 9).map((r) => r.symbol)); }, [rows, wl.seeded]);
  if (!ready) return <div className="wrap state" role="status"><div className="skeleton" style={{ height: 14, width: 200, margin: "40px auto" }} /></div>;
  if (!user) return <Navigate to="/login?next=%2Fdashboard" replace />;

  const move = (i: number, d: -1 | 1) => { const a = [...p.dashboard]; const j = i + d; if (j < 0 || j >= a.length) return; [a[i], a[j]] = [a[j], a[i]]; prefs.set({ dashboard: a }); };
  const patch = (id: string, v: Partial<WidgetPref>) => prefs.set({ dashboard: p.dashboard.map((w) => (w.id === id ? { ...w, ...v } : w)) });
  const shown = p.dashboard.filter((w) => w.on);
  const meta = WIDGETS.reduce<Record<string, (typeof WIDGETS)[number]>>((m, w) => ({ ...m, [w.id]: w }), {});
  const body = (id: string) => {
    const w = meta[id];
    if (RANK[plan] < RANK[w.min]) return <Locked tier={w.min} label={w.label} />;
    switch (id) {
      case "snapshot": return <Snapshot rows={rows} />;
      case "movers": return <Movers items={items} />;
      case "dates": return <Dates symbols={followed} />;
      case "news": return <NewsW symbols={followed} />;
      case "ipos": return <IposW />;
      case "results": return <Results symbols={followed.length ? followed : ["RELIANCE"]} names={names} />;
      case "second": return <SecondLook items={items} meta={wl.meta} />;
      case "screens": return <Screens />;
      case "buckets": return <Buckets items={items} />;
      default: return <Learn />;
    }
  };
  return (
    <div className="wrap dash">
      <header className="dash-h">
        <div><div className="eyebrow">Dashboard</div><h1>{greeting()}{user.name ? `, ${user.name.split(" ")[0]}` : ""}</h1>
          <p className="muted">{followed.length ? `Following ${followed.length} stock${followed.length === 1 ? "" : "s"}.` : "Start by adding stocks to a watchlist."} <span className={"tier " + plan}>{TIER[plan].n}</span></p></div>
        <div className="dash-a">
          <div className="pal-dots" role="radiogroup" aria-label="Colour palette">{PALETTE_IDS.map((id) => <button key={id} role="radio" aria-checked={p.palette === id} title={PALETTES[id].label} aria-label={PALETTES[id].label} className={p.palette === id ? "on" : ""} onClick={() => prefs.set({ palette: id })} style={{ background: `linear-gradient(135deg, ${PALETTES[id].swatch[0]} 50%, ${PALETTES[id].swatch[2]} 50%)` }} />)}</div>
          <button className={"btn" + (edit ? " on" : "")} aria-pressed={edit} onClick={() => { setEdit(!edit); if (params.has("edit")) setParams({}, { replace: true }); }}><Icon name="spark" />{edit ? "Done" : "Customise"}</button>
        </div>
      </header>
      <GettingStarted followed={followed.length} palette={p.palette} plan={plan} />
      {edit && (
        <section className="card dash-edit" aria-label="Customise your dashboard">
          <h2>Make it yours</h2>
          <p className="muted">Switch widgets on or off, make them half or full width, and move them up or down. Changes save as you go and follow your account.</p>
          <ul>{p.dashboard.map((w, i) => { const m = meta[w.id]; return (
            <li key={w.id}>
              <label className="sw"><input type="checkbox" checked={w.on} onChange={(e) => patch(w.id, { on: e.target.checked })} /><span aria-hidden="true" /><b>{m.label}</b></label>
              <small>{m.blurb}{RANK[plan] < RANK[m.min] ? ` · ${TIER[m.min].n}` : ""}</small>
              <span className="seg" role="group" aria-label={`${m.label} width`}>{(["half", "full"] as const).map((s) => <button key={s} aria-pressed={w.size === s} onClick={() => patch(w.id, { size: s })}>{s === "half" ? "Half" : "Full"}</button>)}</span>
              <span className="mv"><button aria-label={`Move ${m.label} up`} disabled={i === 0} onClick={() => move(i, -1)}>↑</button><button aria-label={`Move ${m.label} down`} disabled={i === p.dashboard.length - 1} onClick={() => move(i, 1)}>↓</button></span>
            </li>); })}</ul>
          <div className="row"><Link className="btn" to="/account/appearance">More appearance options</Link><button className="btn" onClick={() => prefs.set({ dashboard: [] })}>Reset layout</button></div>
        </section>
      )}
      <div className="dgrid">
        {shown.map((w) => (
          <section key={w.id} className={"card dw " + (w.size === "full" ? "full" : "half")} aria-labelledby={`w-${w.id}`}>
            <div className="card-h"><h3 id={`w-${w.id}`}><span className="ci"><Icon name={({ snapshot: "bars", movers: "growth", results: "notes", second: "quality", screens: "table", buckets: "layers", learn: "notes", dates: "calendar", news: "notes", ipos: "activity" } as Record<string, string>)[w.id]} /></span>{meta[w.id].label}{HELP[w.id] && <ChartHelp id={HELP[w.id]} />}</h3>
              {RANK[plan] < RANK[meta[w.id].min] && <span className={"tier " + meta[w.id].min}>{TIER[meta[w.id].min].n}</span>}</div>
            {body(w.id)}
          </section>))}
        {!shown.length && <Empty icon="spark" title="Your dashboard is empty" text="Turn some widgets on with Customise." to="/dashboard?edit=1" cta="Customise" />}
      </div>
      <p className="faint dash-f">Research for information only, not investment advice.</p>
    </div>
  );
}
