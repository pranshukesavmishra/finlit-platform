import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { Icon } from "../lib/icons";
import { useAuth } from "../lib/auth";
import { useUI } from "../lib/ui";
import { useDocTitle } from "../lib/title";
import { DEMO } from "../lib/demo";
import { useUniverse } from "../lib/screener";
import { AlertComposer, type Preset } from "../components/AlertComposer";
import { demoCheck, demoNudge, demoReset, timeAgo, useAlerts, useNotices, type AlertRow, type Channel } from "../lib/alerts";
import { LIVE_NOTE, METRICS, closeness, describe, fmtValue, isEvent } from "../lib/alertCatalog";

const QUICK: { t: string; d: string; icon: string; p: Preset }[] = [
  { t: "Price target", d: "Tell me when the price reaches a level", icon: "rupee", p: { metric: "price", op: "above" } },
  { t: "Big move in a day", d: "5% or more, up or down", icon: "activity", p: { metric: "move_abs", op: "above", value: 5 } },
  { t: "Volume spike", d: "3× the 20-day average", icon: "bars", p: { metric: "volume_x", op: "above", value: 3 } },
  { t: "Oversold (RSI below 30)", d: "Often a sign of heavy selling", icon: "gauge", p: { metric: "rsi14", op: "below", value: 30 } },
  { t: "Overbought (RSI above 70)", d: "Often a sign of a stretched rally", icon: "gauge", p: { metric: "rsi14", op: "above", value: 70 } },
  { t: "Near the 52-week high", d: "Within 2% of the yearly peak", icon: "growth", p: { metric: "from_high52", op: "below", value: 2 } },
  { t: "FinLit score upgrade", d: "Score reaches 70 or more", icon: "quality", p: { metric: "overall", op: "above", value: 70 } },
  { t: "Gets cheap", d: "P/E falls to 15 or lower", icon: "percent", p: { metric: "pe", op: "below", value: 15 } },
  { t: "Results announced", d: "A results date within 7 days", icon: "calendar", p: { metric: "result_soon", op: "event", value: 7 } },
  { t: "Dividend or buyback news", d: "A headline mentions “dividend”", icon: "notes", p: { metric: "news_keyword", op: "event", keyword: "dividend" } },
  { t: "Promoter holding falls", d: "Down 1 point or more in a quarter", icon: "users", p: { metric: "promoter_chg", op: "below", value: -1 } },
  { t: "Profit milestone", d: "Quarterly net profit above a level", icon: "coins", p: { metric: "q_net_profit", op: "above" } },
];
const CH: Record<Channel, [string, string]> = { app: ["bell", "In-app"], email: ["mail", "Email"], browser: ["activity", "Browser"] };
const STATE = { active: ["Active", "ok"], paused: ["Paused", "mute"], done: ["Triggered", "gold"] } as const;
type Tab = "mine" | "fired";
type Filter = "all" | "active" | "paused" | "done";

function AlertCard({ a, onPatch, onRemove }: { a: AlertRow; onPatch: (p: { status?: "active" | "paused"; value?: number }) => void; onRemove: () => void }) {
  const [edit, setEdit] = useState(false), [v, setV] = useState(String(a.value ?? "")), [sure, setSure] = useState(false);
  const pct = closeness(a), [label, tone] = STATE[a.status];
  const ev = isEvent(a.metric);
  return (
    <article className={"card alx-c is-" + a.status}>
      <div className="alx-ch">
        <Link className="alx-sym" to={`/stocks/${a.symbol}`}>{a.symbol}</Link>
        <span className={"alx-st " + tone}><i />{label}</span>
        <span className="alx-grow" />
        <span className="alx-chs" aria-label={"Notifies via " + a.channels.map((c) => CH[c][1]).join(", ")}>{a.channels.map((c) => <span key={c} title={CH[c][1]}><Icon name={CH[c][0]} /></span>)}</span>
      </div>
      <h3>{describe(a)}</h3>
      {!ev && (
        <div className="alx-prog" aria-label={pct != null ? `${pct}% of the way to the trigger` : undefined}>
          <div className="alx-bar"><i style={{ width: `${pct ?? 0}%` }} /></div>
          <div className="alx-pl"><span>{a.lastValue != null ? <>Now <b>{fmtValue(a.metric, a.lastValue)}</b></> : "Waiting for the first check"}</span><span>Target <b>{fmtValue(a.metric, a.value)}</b></span></div>
        </div>
      )}
      <p className="alx-meta">
        {a.repeat === "every" ? "Repeats" : "Once"} · {METRICS[a.metric]?.live ? "live" : "daily"} check{a.lastCheckedAt ? ` · checked ${timeAgo(a.lastCheckedAt)}` : ""}
        {a.firedCount > 0 && a.lastFiredAt ? ` · fired ${a.firedCount}× (last ${timeAgo(a.lastFiredAt)})` : ""}
      </p>
      {a.note && <p className="alx-note">“{a.note}”</p>}
      <div className="alx-act">
        {edit && !ev ? (
          <form onSubmit={(e) => { e.preventDefault(); const n = Number(v); if (isFinite(n) && v.trim() !== "") { onPatch({ value: n }); setEdit(false); } }} className="alx-edit">
            <input aria-label="New target value" inputMode="decimal" value={v} onChange={(e) => setV(e.target.value.replace(/[^0-9.\-]/g, ""))} autoFocus />
            <button className="btn primary" type="submit">Save</button><button className="btn" type="button" onClick={() => setEdit(false)}>Cancel</button>
          </form>
        ) : (
          <>
            {a.status === "active" && <button className="btn" onClick={() => onPatch({ status: "paused" })}><Icon name="pause" /><span>Pause</span></button>}
            {a.status === "paused" && <button className="btn" onClick={() => onPatch({ status: "active" })}><Icon name="play" /><span>Resume</span></button>}
            {a.status === "done" && <button className="btn" onClick={() => onPatch({ status: "active" })}><Icon name="play" /><span>Set again</span></button>}
            {!ev && <button className="btn" onClick={() => { setV(String(a.value ?? "")); setEdit(true); }}><span>Change target</span></button>}
            {sure ? <><button className="btn danger" onClick={onRemove}>Delete</button><button className="btn" onClick={() => setSure(false)}>Keep</button></> : <button className="btn" onClick={() => setSure(true)} aria-label={`Delete the ${a.symbol} alert`}><Icon name="trash" /></button>}
          </>
        )}
      </div>
    </article>
  );
}

export function AlertsPage() {
  useDocTitle("Alerts", "Get told when a price, signal, score, ratio, result or filing crosses the line you set: in the app, by email or in your browser.");
  const { user } = useAuth();
  const { plan, upgrade, toast } = useUI();
  const [params] = useSearchParams();
  const { data } = useUniverse(DEMO);   // the company list is only needed by the demo (no server to ask)
  const rows = data?.rows || [];
  const { alerts, limit, loading, error, patch, remove } = useAlerts(rows);
  const { items, unread, markRead, clear } = useNotices();
  const [preset, setPreset] = useState<Preset>(() => (params.get("symbol") ? { symbol: params.get("symbol")!.toUpperCase() } : {}));
  const [tab, setTab] = useState<Tab>("mine"), [f, setF] = useState<Filter>("all"), [q, setQ] = useState("");

  const counts = useMemo(() => ({ all: alerts.length, active: alerts.filter((a) => a.status === "active").length, paused: alerts.filter((a) => a.status === "paused").length, done: alerts.filter((a) => a.status === "done").length }), [alerts]);
  const week = items.filter((n) => Date.now() - new Date(n.createdAt).getTime() < 7 * 86_400_000).length;
  const shown = alerts.filter((a) => (f === "all" || a.status === f) && (!q.trim() || a.symbol.includes(q.trim().toUpperCase()) || a.label.toLowerCase().includes(q.trim().toLowerCase())));
  const used = counts.active + counts.paused;
  const fail = (e: unknown) => toast((e as { body?: { detail?: string } })?.body?.detail || "That did not work. Please try again.");

  if (!user && !DEMO) {
    return (
      <div className="wrap alx">
        <header className="dash-h"><div><div className="eyebrow">My lists</div><h1>Alerts</h1><p className="muted">Get told when a price, signal, score, ratio, result or filing crosses the line you set.</p></div></header>
        <section className="card dw-empty"><span className="dw-ei"><Icon name="bell" /></span><b>Sign in to set alerts</b><p>Alerts are free to create. Basic includes 3 at a time; Silver and Gold add every metric and many more alerts.</p><Link className="btn primary" to="/login?next=/alerts">Sign in or create an account</Link></section>
      </div>
    );
  }
  return (
    <div className="wrap alx">
      <header className="dash-h"><div><div className="eyebrow">My lists</div><h1>Alerts</h1><p className="muted">Pick a company and a condition. When it comes true you are told in the app, and by email or in your browser if you choose. For information only, not investment advice.</p></div></header>

      <div className="alx-k">
        <div className="card"><b>{counts.active}</b><span>Active alerts</span></div>
        <div className="card"><b>{week}</b><span>Fired in the last 7 days</span></div>
        <div className="card"><b className={unread ? "gold" : ""}>{unread}</b><span>Unread</span></div>
        <div className="card"><b>{used}<small> / {limit}</small></b><span>{plan[0].toUpperCase() + plan.slice(1)} plan</span>{plan !== "gold" && used >= limit - 1 && <button className="alx-link" onClick={() => upgrade(plan === "basic" ? "silver" : "gold", "More alerts")}>Get more</button>}</div>
      </div>

      <div className="alx-grid">
        <aside className="alx-side">
          <section className="card acc alx-new">
            <div className="card-h"><h3><span className="ci"><Icon name="bell" /></span>Create new alert</h3></div>
            <AlertComposer preset={preset} />
          </section>
        </aside>

        <div className="alx-main">
          <section className="alx-quick" aria-label="Quick alerts">
            <div className="alx-qh"><h2>Quick alerts</h2><span className="muted">Pick one to fill the form, then choose the stock</span></div>
            <div className="alx-qg">
              {QUICK.map((x) => {
                const lock = METRICS[x.p.metric!].tier === "silver" && plan === "basic";
                return <button key={x.t} className="alx-q" onClick={() => { setPreset({ ...x.p, symbol: preset.symbol }); document.getElementById("alx-stock")?.scrollIntoView({ behavior: "smooth", block: "center" }); }}>
                  <span className="alx-qi"><Icon name={x.icon} /></span><span><b>{x.t}</b><small>{x.d}</small></span>{lock && <em>Silver</em>}
                </button>;
              })}
            </div>
          </section>

          <section className="card alx-list">
            <div className="alx-tabs" role="tablist" aria-label="Alerts">
              <button role="tab" aria-selected={tab === "mine"} onClick={() => setTab("mine")}>My alerts <span>{alerts.length}</span></button>
              <button role="tab" aria-selected={tab === "fired"} onClick={() => setTab("fired")}>Triggered {unread > 0 && <span className="hot">{unread} new</span>}</button>
            </div>

            {tab === "mine" ? (
              <>
                <div className="alx-bar2">
                  <div className="seg" role="group" aria-label="Status">{([["all", "All"], ["active", "Active"], ["paused", "Paused"], ["done", "Triggered"]] as const).map(([k, l]) => <button key={k} aria-pressed={f === k} onClick={() => setF(k)}>{l} {counts[k] > 0 && <small>{counts[k]}</small>}</button>)}</div>
                  <input className="cs-in" aria-label="Search your alerts" placeholder="Search by stock or metric" value={q} onChange={(e) => setQ(e.target.value)} />
                </div>
                {error && <div className="formerr">Your alerts could not be loaded. Please try again shortly.</div>}
                {loading && <div className="skeleton" style={{ height: 120 }} />}
                {!loading && !error && alerts.length === 0 && <div className="dw-empty"><span className="dw-ei"><Icon name="bell" /></span><b>No alerts yet</b><p>Try a quick alert on the right, or build your own with the form. {LIVE_NOTE}</p></div>}
                <div className="alx-cards">
                  {shown.map((a) => <AlertCard key={a.id} a={a} onPatch={(p) => patch.mutate({ id: a.id, ...p }, { onError: fail })} onRemove={() => remove.mutate(a.id, { onError: fail })} />)}
                </div>
                {alerts.length > 0 && !shown.length && <p className="muted" style={{ padding: 24, textAlign: "center" }}>No alerts match these filters.</p>}
              </>
            ) : (
              <>
                <div className="alx-bar2"><span className="muted">{items.length ? `${items.length} recent` : "Nothing has fired yet"}</span><span className="alx-grow" />
                  {unread > 0 && <button className="btn" onClick={() => markRead()}>Mark all read</button>}{items.length > 0 && <button className="btn" onClick={() => clear()}>Clear all</button>}</div>
                {items.length === 0 && <div className="dw-empty"><span className="dw-ei"><Icon name="bell" /></span><b>All quiet</b><p>When an alert fires, it is kept here with the time and a link to the stock.</p></div>}
                <ul className="alx-hist">
                  {items.map((n) => (
                    <li key={n.id} className={n.read ? "" : "is-new"}>
                      <span className="alx-hd" aria-hidden="true" />
                      <div><b>{n.title}</b><p>{n.body}</p><small>{timeAgo(n.createdAt)}</small></div>
                      <div className="alx-hb">{n.link && <Link className="btn" to={n.link} onClick={() => markRead([n.id])}>View stock <Icon name="arrow" /></Link>}{!n.read && <button className="alx-link" onClick={() => markRead([n.id])}>Mark read</button>}</div>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </section>

          {DEMO && (
            <section className="card alx-demo">
              <div className="card-h"><h3><span className="ci"><Icon name="spark" /></span>Demo controls</h3><span className="s">Preview only</span></div>
              <p className="muted">On the live site a background job checks your alerts for you. Here you can trigger that check by hand to see what happens.</p>
              <div className="alx-act">
                <button className="btn primary" onClick={() => { demoNudge(rows); const n = demoCheck(rows); toast(n ? `${n} alert${n > 1 ? "s" : ""} fired. See the bell above.` : "Nothing crossed its target this time."); }}>Make my alerts fire</button>
                <button className="btn" onClick={() => { const n = demoCheck(rows); toast(n ? `${n} alert${n > 1 ? "s" : ""} fired.` : "Checked. Nothing crossed its target."); }}>Run a check</button>
                <button className="btn" onClick={() => { demoReset(); toast("Demo alerts cleared."); }}>Start over</button>
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
