// Commodity prices (public, no sign-in): the MCX futures price and, where a price feed is connected, the international USD price for gold, silver,
// crude oil, natural gas, copper and aluminium. Every price arrives from the server as text already rounded to the digits shown;
// this page formats and lays out, it never computes a price (the unit converter is the one exception and uses exact integer arithmetic).
// Information only, never advice: no calls to act, no outlook.
import { PageHeader } from "../components/PageHeader";
import { useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import { ErrorBoundary } from "../components/ErrorBoundary";
import {
  UNITS, convert, dayMonthYear, direction, group, inr, istStamp, istTime, signedPct, useCommodities, usd,
  type CommodityIntl, type CommodityItem, type CommodityMcx, type Commodities, type UnitId,
} from "../lib/commodities";
import "../styles/commodities.css";

const TABS = [["all", "All"], ["precious", "Precious metals"], ["energy", "Energy"], ["industrial", "Industrial metals"]] as const;
type Tab = (typeof TABS)[number][0];

const DISCLAIMER = "Prices are for information only and are not investment advice or an invitation to deal in any commodity. MCX prices are futures prices with the contract month shown; they are not what a jeweller or bank will charge. Import parity is an indicative calculation from the international price, the exchange rate and customs duty, not a quote. Figures can be delayed or wrong; check with your broker or jeweller before you transact.";

function Change({ pct, unitAbs }: { pct: string | null | undefined; unitAbs?: string }) {
  if (pct == null) return null;
  const d = direction(pct);
  return <span className={"cm-chg " + d} title={unitAbs}>{signedPct(pct)}</span>;
}

// ------------------------------------------------------------------------------------------------------------- the three blocks of a card
function McxBlock({ m, label }: { m: CommodityMcx; label: string }) {
  const unit = m.price?.unit.replace(/^₹\s*/, "") ?? "";
  return (
    <div className={"cm-blk cm-mcx st-" + m.state} data-state={m.state}>
      <div className="cm-lbl"><span>{label}</span>{m.contract && <span className="cm-contract" title={m.expiry ? `Contract expires ${dayMonthYear(m.expiry)}` : undefined}>{m.contract}</span>}</div>
      {m.price ? (
        <>
          <div className="cm-row"><span className="cm-big">{inr(m.price.value)}</span><span className="cm-unit">{unit}</span>
            {m.change && <Change pct={m.change.pct} unitAbs={`${m.change.abs} ${m.change.absUnit} against the previous close`} />}</div>
          {m.extra.length > 0 && <dl className="cm-extra">{m.extra.map((e) => <div key={e.label}><dt>{e.label}</dt><dd>{inr(e.value)}</dd></div>)}</dl>}
        </>
      ) : <p className="cm-dash"><span aria-hidden="true">—</span> {m.note ?? m.label}</p>}
      <p className="cm-foot"><span className={"cm-dot st-" + m.state} aria-hidden="true" />
        <span>{m.label}{m.asOf && m.state !== "off" && m.state !== "none" ? ` · ${m.state === "closed" ? `last trade ${istStamp(m.asOf)}` : `last trade ${istTime(m.asOf)}`} IST` : ""}</span></p>
      {m.price && m.note && <p className="cm-note">{m.note}</p>}
    </div>
  );
}

function IntlBlock({ lines, name }: { lines: CommodityIntl[]; name: string }) {
  if (!lines.some((l) => l.usd != null)) return null;    // no international price: nothing is shown (not even a "not connected" line)
  const off = false;
  return (
    <div className="cm-blk cm-intl">
      <div className="cm-lbl"><span>International price</span>{lines[0]?.vendor && <span className="cm-src">via {lines[0].vendor}</span>}</div>
      {off ? <p className="cm-dash"><span aria-hidden="true">—</span> International price not connected</p> : lines.map((l) => (
        <div key={l.key} className={"cm-iline st-" + l.state}>
          {lines.length > 1 && <span className="cm-il">{l.label}</span>}
          {l.usd != null ? (
            <span className="cm-row"><span className="cm-mid">{usd(l.usd)}</span><span className="cm-unit">{l.unit.replace(/^\$\s*/, "")}</span><Change pct={l.changePct} /></span>
          ) : <span className="cm-dash"><span aria-hidden="true">—</span> {l.note ?? "Waiting for the first international price"}</span>}
          {l.usd != null && l.note && <span className="cm-note">{l.note}{l.asOf && l.state === "closed" ? ` As of ${istStamp(l.asOf)} IST.` : ""}</span>}
        </div>))}
      <span className="sr-only">{name} international price in US dollars</span>
    </div>
  );
}

function Card({ c }: { c: CommodityItem }) {
  const grp = c.group === "precious" ? "Precious metal" : c.group === "energy" ? "Energy" : "Industrial metal";
  return (
    <article className={"card cm-card g-" + c.group} aria-labelledby={"cm-" + c.code}>
      <header><h2 id={"cm-" + c.code}>{c.name}</h2><span className="cm-grp">{grp}</span></header>
      {c.mcx && <McxBlock m={c.mcx} label="MCX futures price (via Dhan)" />}
      <IntlBlock lines={c.intl} name={c.name} />
    </article>
  );
}

// ------------------------------------------------------------------------------------------------------------- converter and explainer
function Converter() {
  const [v, setV] = useState("1");
  const [from, setFrom] = useState<UnitId>("tola");
  const [to, setTo] = useState<UnitId>("g");
  const out = convert(v, from, to);
  return (
    <details className="cm-acc card"><summary><h2>Weight converter</h2><span className="faint">grams, tola, 10 g, kg, troy ounce</span></summary>
      <div className="cm-conv">
        <label>Amount<input inputMode="decimal" value={v} onChange={(e) => setV(e.target.value)} maxLength={24} aria-invalid={out == null} autoComplete="off" spellCheck={false} /></label>
        <label>From<select value={from} onChange={(e) => setFrom(e.target.value as UnitId)}>{UNITS.map((u) => <option key={u.id} value={u.id}>{u.label}</option>)}</select></label>
        <label>To<select value={to} onChange={(e) => setTo(e.target.value as UnitId)}>{UNITS.map((u) => <option key={u.id} value={u.id}>{u.label}</option>)}</select></label>
      </div>
      <p className="cm-result" aria-live="polite">{out == null ? "Enter a number such as 10 or 11.5." : <><b>{group(out, true)}</b> {UNITS.find((u) => u.id === to)!.label.replace(/ \(.*/, "").toLowerCase()}</>}</p>
      <p className="faint">Exact arithmetic on the international grain (0.06479891 g): a tola is 180 grains and a troy ounce 480 grains. Some Indian sources round the tola to 11.664 g.</p>
    </details>
  );
}

function Explainer() {
  return (
    <details className="cm-acc card"><summary><h2>How this is worked out</h2><span className="faint">sources, formulas and the choices made</span></summary>
      <div className="cm-expl">
        <h3>The MCX price</h3>
        <p>It is the price of an MCX futures contract, not a spot price, and the contract month is on every card. Gold is quoted by the exchange in rupees per 10 grams, so the per-gram figure is the quote divided by 10; silver is quoted per kilogram, so per gram is the quote divided by 1,000. The nearest contract that has not expired is shown, and the next one is used once it trades more. When the contract changes, the day change is hidden for that day. The source is Dhan; the MCX logo and exchange name are not used for anything but this label.</p>
        <h3>The international price</h3>
        <p>US dollars per troy ounce for gold, silver and per barrel for crude oil, per mmBtu for natural gas and per tonne for copper and aluminium, from a licensed price feed. The day change is against the last price of the previous international trading day (which ends at 5 pm New York time); it is left out until a full previous day has been recorded.</p>
        <h3>Choices made in these figures</h3>
        <ul>
          <li>22K is worked out as 22/24 of the 24K price (the usual shop convention). The hallmark standard of 916 parts per thousand would give a figure about 0.07% lower.</li>
          <li>The 22K and 18K lines come from the MCX price.</li>
        </ul>
        <h3>Why none of these is your jeweller's price</h3>
        <p>MCX figures include import duty but not GST. A jeweller adds 3% GST, making charges (commonly 8% to 25%), wastage and a local premium, sells 22K or 18K rather than 24K, and may quote different rates in different cities. Benchmark rates from the bullion association also leave out GST and making charges.</p>
      </div>
    </details>
  );
}

// ------------------------------------------------------------------------------------------------------------- page
function Status({ d }: { d: Commodities }) {
  const mcxAsOf = d.items.map((i) => i.mcx?.asOf).filter((x): x is string => !!x).sort().pop();
  const intlAsOf = d.items.flatMap((i) => i.intl.map((l) => l.asOf)).filter((x): x is string => !!x).sort().pop();
  const m = d.market.mcx;
  return (
    <div className="cm-status" role="status">
      <span className="cm-pill"><span className={"cm-dot " + (m.open ? "st-live" : "st-closed")} aria-hidden="true" />
        {m.open ? `MCX open until ${m.closes} IST` : "MCX closed"}{!m.hoursConfirmed && m.open ? " (hours to be confirmed)" : ""}{mcxAsOf ? ` · last trade ${istTime(mcxAsOf)}` : ""}</span>
      <span className="cm-pill"><span className={"cm-dot " + (d.market.global.open ? "st-live" : "st-closed")} aria-hidden="true" />
        {d.market.global.open ? "Global market open" : "Global market closed"}{intlAsOf ? ` · price at ${istTime(intlAsOf)}` : ""}</span>
      {d.fx.usdinr && <span className="cm-pill">USD/INR {d.fx.usdinr}{d.fx.asOf ? ` · ${istTime(d.fx.asOf)}` : ""}</span>}
      {d.items.some((i) => i.code === "gold") && d.ratio.goldSilver && <span className="cm-pill">Gold/silver ratio {d.ratio.goldSilver}</span>}
    </div>
  );
}

function Notices({ d }: { d: Commodities }) {
  const out: string[] = [];
  if (!d.sources.mcx.connected) out.push("MCX prices are not connected yet.");
  if (!d.sources.intl.connected) out.push("International prices are not connected yet, so only MCX prices are shown. The gold/silver ratio needs the international price.");
  if (d.status === "waiting" && (d.sources.mcx.connected || d.sources.intl.connected)) out.push("Waiting for the first prices to arrive. This usually takes a minute after the service starts.");
  return out.length ? <div className="cm-notices" role="note">{out.map((t) => <p key={t}><Icon name="info" />{t}</p>)}</div> : null;
}

export function CommoditiesPage() {
  useDocTitle("Commodity prices", "Gold, silver, crude oil, natural gas, copper and aluminium: MCX futures price and international price in US dollars. Free, no sign-in.");
  const q = useCommodities();
  const [sp, setSp] = useSearchParams();
  const tab: Tab = (TABS.find(([id]) => id === sp.get("tab"))?.[0]) ?? "all";
  const setTab = (t: Tab) => setSp(t === "all" ? {} : { tab: t }, { replace: true });
  const items = useMemo(() => (q.data?.items ?? []).filter((i) => i.code !== "platinum" && (tab === "all" || i.group === tab)), [q.data, tab]);
  return (
    <>
      <PageHeader wrap plan="free" title="Commodity prices" art="macro" links={["/macro", "/fii-dii", "/premium/markets"]}
        description={<>MCX market price and, where available, the <b>international (USD) price</b> for gold, silver, crude and metals.</>}
        stats={[{ icon: "layers", value: q.data ? q.data.items.filter((i) => i.code !== "platinum").length : null, label: "Commodities" }]} />
      <div className="wrap cm">
        <p className="cm-disc" role="note"><Icon name="info" /><span>{DISCLAIMER}</span></p>
        {q.data && <Status d={q.data} />}
        {q.data && <Notices d={q.data} />}
        <div className="cm-tabs" role="group" aria-label="Commodity group">
          <div className="cm-seg">{TABS.map(([id, label]) => <button key={id} type="button" aria-pressed={tab === id} onClick={() => setTab(id)}>{label}</button>)}</div>
        </div>
        {q.isLoading && <div className="cm-grid" aria-busy="true" aria-label="Loading prices">{[0, 1, 2].map((i) => <div key={i} className="card cm-card"><div className="skeleton" style={{ height: 22, width: "40%" }} /><div className="skeleton" style={{ height: 38, width: "70%", margin: "16px 0" }} /><div className="skeleton" style={{ height: 60 }} /></div>)}</div>}
        {q.isError && !q.data && <div className="card cm-err" role="alert"><p>Commodity prices could not be loaded right now.</p><button className="btn" onClick={() => q.refetch()}>Try again</button></div>}
        {q.data && <div className="cm-grid">{items.map((c) => <ErrorBoundary key={c.code} message={`${c.name} is not available right now.`}><Card c={c} /></ErrorBoundary>)}</div>}
        {q.data && items.length === 0 && <p className="faint">Nothing to show in this group.</p>}
        <Converter />
        <Explainer />
        <p className="faint cm-src-note">Sources: MCX futures prices via Dhan{q.data?.sources.intl.metals ? `; international prices and USD/INR via ${q.data.sources.intl.metals}${q.data.sources.intl.energy && q.data.sources.intl.energy !== q.data.sources.intl.metals ? ` and ${q.data.sources.intl.energy}` : ""}` : ""}. Customs duty from the Union Government's notifications. Updated automatically.</p>
      </div>
    </>
  );
}
