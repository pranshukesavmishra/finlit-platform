// Commodity prices (public, no sign-in): the MCX futures price, the international USD price and an indicative import parity for gold, silver,
// platinum, crude oil, natural gas, copper and aluminium. Every price arrives from the server as text already rounded to the digits shown;
// this page formats and lays out, it never computes a price (the unit converter is the one exception and uses exact integer arithmetic).
// Information only, never advice: no calls to act, no outlook.
import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import { Info } from "../components/Info";
import { ErrorBoundary } from "../components/ErrorBoundary";
import {
  UNITS, convert, dayMonthYear, direction, group, inr, istStamp, istTime, signedPct, useCommodities, usd,
  type CommodityIntl, type CommodityItem, type CommodityMcx, type CommodityParity, type Commodities, type UnitId,
} from "../lib/commodities";
import "../styles/commodities.css";

const TABS = [["all", "All"], ["precious", "Precious metals"], ["energy", "Energy"], ["industrial", "Industrial metals"]] as const;
type Tab = (typeof TABS)[number][0];

const help = (key: string, label: string, what: string, extra: { formula?: string; read?: string; note?: string } = {}) => ({ key, label, what, ...extra });

const DISCLAIMER = "Prices are for information only and are not investment advice or an invitation to deal in any commodity. MCX prices are futures prices with the contract month shown; they are not what a jeweller or bank will charge. Import parity is an indicative calculation from the international price, the exchange rate and customs duty, not a quote. Figures can be delayed or wrong; check with your broker or jeweller before you transact.";

function useWide() {
  const q = "(min-width: 640px)";
  const [w, setW] = useState(() => (typeof matchMedia === "function" ? matchMedia(q).matches : true));
  useEffect(() => { if (typeof matchMedia !== "function") return; const m = matchMedia(q); const f = () => setW(m.matches); m.addEventListener("change", f); return () => m.removeEventListener("change", f); }, []);
  return w;
}

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
  const off = lines.length > 0 && lines.every((l) => l.state === "off");
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

function ParityBlock({ p, open, onToggle }: { p: CommodityParity; open: boolean; onToggle: (v: boolean) => void }) {
  return (
    <details className="cm-par" open={open} onToggle={(e) => onToggle((e.currentTarget as HTMLDetailsElement).open)}>
      <summary><span>India import parity</span><span className="cm-tag">indicative</span>
        <Info g={help("parity", "Import parity", "What the metal would cost per gram if bought abroad at the international price, converted to rupees and with Indian customs duty added. It is worked out, not quoted, and leaves out GST, making charges and any local premium.",
          { formula: "USD per troy oz ÷ 31.1034768 × USD/INR × (1 + BCD + AIDC)", note: "Customs charge duty on a government tariff value rather than the market price, so the real landed cost can differ a little." })} /></summary>
      {p.state === "ok" && p.duty ? (
        <div className="cm-parbody">
          <div className="cm-row"><span className="cm-big">{inr(p.perGram)}</span><span className="cm-unit">per gram, before GST</span></div>
          <div className="cm-chips" aria-label="Customs duty used"><span className="cm-chip">BCD {p.duty.bcd}%</span><span className="cm-chip">AIDC {p.duty.aidc}%</span><span className="cm-chip alt">GST {p.duty.gst}% separate</span></div>
          <dl className="cm-extra">
            <div><dt>With {p.duty.gst}% GST, per gram</dt><dd>{inr(p.withGst)}</dd></div>
            <div><dt>Before GST, per 10 g</dt><dd>{inr(p.per10g)}</dd></div>
            <div><dt>Before GST, per kg</dt><dd>{inr(p.perKg)}</dd></div>
            {p.premiumPct != null && (
              <div><dt>MCX against parity <Info g={help("prem", "MCX against parity", p.premiumBasis ?? "The MCX price compared with the import parity price.", { formula: "(MCX price ÷ parity price − 1) × 100", note: "A gap is not a signal of anything by itself: MCX is a futures price for one contract month, and parity is a calculation." })} /></dt>
                <dd><Change pct={p.premiumPct} /></dd></div>)}
          </dl>
          <p className="cm-note">Duty rates in force from {dayMonthYear(p.duty.effectiveFrom)}; checked {dayMonthYear(p.duty.checkedOn)}. USD/INR {p.usdinr}.</p>
        </div>
      ) : <p className="cm-dash cm-parbody"><span aria-hidden="true">—</span> {p.reason ?? "Not available right now."}</p>}
    </details>
  );
}

function Card({ c, tab }: { c: CommodityItem; tab: Tab }) {
  const wide = useWide();
  const [openP, setOpenP] = useState<boolean | null>(null);
  const open = openP ?? (wide || tab !== "all");
  const grp = c.group === "precious" ? "Precious metal" : c.group === "energy" ? "Energy" : "Industrial metal";
  return (
    <article className={"card cm-card g-" + c.group} aria-labelledby={"cm-" + c.code}>
      <header><h2 id={"cm-" + c.code}>{c.name}</h2><span className="cm-grp">{grp}</span></header>
      {c.mcx && <McxBlock m={c.mcx} label="MCX futures price (via Dhan)" />}
      <IntlBlock lines={c.intl} name={c.name} />
      {c.parity && <ParityBlock p={c.parity} open={open} onToggle={setOpenP} />}
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

function Explainer({ data }: { data?: Commodities }) {
  const d = data?.items.find((i) => i.parity?.state === "ok")?.parity?.duty;
  return (
    <details className="cm-acc card"><summary><h2>How this is worked out</h2><span className="faint">sources, formulas and the choices made</span></summary>
      <div className="cm-expl">
        <h3>The MCX price</h3>
        <p>It is the price of an MCX futures contract, not a spot price, and the contract month is on every card. Gold is quoted by the exchange in rupees per 10 grams, so the per-gram figure is the quote divided by 10; silver is quoted per kilogram, so per gram is the quote divided by 1,000. The nearest contract that has not expired is shown, and the next one is used once it trades more. When the contract changes, the day change is hidden for that day. The source is Dhan; the MCX logo and exchange name are not used for anything but this label.</p>
        <h3>The international price</h3>
        <p>US dollars per troy ounce for gold, silver and platinum, per barrel for crude oil, per mmBtu for natural gas and per tonne for copper and aluminium, from a licensed price feed. The day change is against the last price of the previous international trading day (which ends at 5 pm New York time); it is left out until a full previous day has been recorded.</p>
        <h3>Import parity</h3>
        <p>What a gram would cost to bring in at the international price: USD per troy ounce ÷ 31.1034768 grams × the USD/INR rate × (1 + basic customs duty + agriculture infrastructure and development cess).{d ? ` Today that is 1 + ${d.bcd}% + ${d.aidc}% = ${d.total}% on top of the rupee price, in force from ${dayMonthYear(d.effectiveFrom)}.` : ""} GST of 3% is shown as a separate line because MCX prices and the benchmark rates in the trade leave it out. Customs actually charge duty on a government tariff value that is revised about every fortnight, so the landed cost on a real shipment can differ from this simple figure. Rates are kept in a table with the date they came into force and are checked by a person; if the check is more than 120 days old, parity is hidden rather than shown on an old rate. Platinum parity is hidden until its duty rate is confirmed. Crude oil, natural gas and base metals have no parity: their duty and levy rules change often.</p>
        <h3>Choices made in these figures</h3>
        <ul>
          <li>22K is worked out as 22/24 of the 24K price (the usual shop convention). The hallmark standard of 916 parts per thousand would give a figure about 0.07% lower.</li>
          <li>MCX gold is a 995-purity bar and the international price is for fine (999) gold, so the "MCX against parity" line scales the MCX price by 999/995 before comparing. Silver is 999 on both sides.</li>
          <li>The 22K and 18K lines come from the MCX price, not from import parity.</li>
        </ul>
        <h3>Why none of these is your jeweller's price</h3>
        <p>MCX and parity figures include import duty but not GST. A jeweller adds 3% GST, making charges (commonly 8% to 25%), wastage and a local premium, sells 22K or 18K rather than 24K, and may quote different rates in different cities. Benchmark rates from the bullion association also leave out GST and making charges.</p>
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
  if (!d.sources.intl.connected) out.push("International prices are not connected yet, so only MCX prices are shown. Import parity and the gold/silver ratio need the international price and the USD/INR rate.");
  else if (d.fx.state === "none" || d.fx.state === "unavailable") out.push("The USD/INR rate is not available right now, so import parity is hidden.");
  if (d.status === "waiting" && (d.sources.mcx.connected || d.sources.intl.connected)) out.push("Waiting for the first prices to arrive. This usually takes a minute after the service starts.");
  return out.length ? <div className="cm-notices" role="note">{out.map((t) => <p key={t}><Icon name="info" />{t}</p>)}</div> : null;
}

export function CommoditiesPage() {
  useDocTitle("Commodity prices", "Gold, silver, platinum, crude oil, natural gas, copper and aluminium: MCX futures price, international price in US dollars and indicative import parity. Free, no sign-in.");
  const q = useCommodities();
  const [sp, setSp] = useSearchParams();
  const tab: Tab = (TABS.find(([id]) => id === sp.get("tab"))?.[0]) ?? "all";
  const setTab = (t: Tab) => setSp(t === "all" ? {} : { tab: t }, { replace: true });
  const items = useMemo(() => (q.data?.items ?? []).filter((i) => tab === "all" || i.group === tab), [q.data, tab]);
  return (
    <>
      <section className="pagehead"><div className="wrap"><div className="eyebrow">Free tool · no sign-in</div><h1>Commodity Prices</h1>
        <p className="cm-sub">MCX market price · International (USD) · Import parity</p></div></section>
      <div className="wrap cm">
        <p className="cm-disc" role="note"><Icon name="info" /><span>{DISCLAIMER}</span></p>
        {q.data && <Status d={q.data} />}
        {q.data && <Notices d={q.data} />}
        <div className="cm-tabs" role="group" aria-label="Commodity group">
          <div className="cm-seg">{TABS.map(([id, label]) => <button key={id} type="button" aria-pressed={tab === id} onClick={() => setTab(id)}>{label}</button>)}</div>
        </div>
        {q.isLoading && <div className="cm-grid" aria-busy="true" aria-label="Loading prices">{[0, 1, 2].map((i) => <div key={i} className="card cm-card"><div className="skeleton" style={{ height: 22, width: "40%" }} /><div className="skeleton" style={{ height: 38, width: "70%", margin: "16px 0" }} /><div className="skeleton" style={{ height: 60 }} /></div>)}</div>}
        {q.isError && !q.data && <div className="card cm-err" role="alert"><p>Commodity prices could not be loaded right now.</p><button className="btn" onClick={() => q.refetch()}>Try again</button></div>}
        {q.data && <div className="cm-grid">{items.map((c) => <ErrorBoundary key={c.code} message={`${c.name} is not available right now.`}><Card c={c} tab={tab} /></ErrorBoundary>)}</div>}
        {q.data && items.length === 0 && <p className="faint">Nothing to show in this group.</p>}
        <Converter />
        <Explainer data={q.data} />
        <p className="faint cm-src-note">Sources: MCX futures prices via Dhan{q.data?.sources.intl.metals ? `; international prices and USD/INR via ${q.data.sources.intl.metals}${q.data.sources.intl.energy && q.data.sources.intl.energy !== q.data.sources.intl.metals ? ` and ${q.data.sources.intl.energy}` : ""}` : ""}. Customs duty from the Union Government's notifications. Updated automatically.</p>
      </div>
    </>
  );
}
