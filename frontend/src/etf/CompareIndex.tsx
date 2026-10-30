// /etfs/compare-index-funds: ETFs and direct-plan index funds that follow the same index, side by side. Pick an index, then the ETFs and the index funds
// that follow it (up to four products), and press Compare. The choice lives in the address (?index=&etf=&fund=), so a comparison is a link.
// Information only: the page describes what happened, it never says what to buy, sell or hold, and it never names a winner.
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import { nf } from "../lib/format";
import {
  DISCLAIMER, MAX_PRODUCTS, TILES, day, downloadCsv, parsePage, readyToCompare, rtShort, sectionRows, toParams, useEviCompare, useEviOptions,
  type Compare, type EtfOpt, type FundOpt, type PageState, type PlanMode, type RangeKey, type SectionId,
} from "../lib/etfVsIndex";
import { ErrorState, Skeleton } from "./common";
import { COLORS, DASHES, Calculator, Cost, Performance, RiskBlock, Summary, TrackingBlock } from "./CompareIndexSections";
import "../styles/etfvs.css";

type Opt = { id: string; title: string; sub: string; tag: string };
const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? "" : "s"}`;

/** A button that opens a searchable list of the products of one index. Chosen ones show as chips. Enter in the search box adds the first match. */
function Picker({ label, placeholder, items, chosen, onChange, room, disabledWhy }: {
  label: string; placeholder: string; items: Opt[]; chosen: string[]; onChange: (ids: string[]) => void; room: number; disabledWhy?: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const id = useId();
  const box = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [open]);
  const shown = items.filter((i) => !q.trim() || `${i.title} ${i.sub} ${i.id}`.toLowerCase().includes(q.trim().toLowerCase()));
  const add = (x: string) => { if (chosen.includes(x)) onChange(chosen.filter((c) => c !== x)); else if (room > 0) onChange([...chosen, x]); };
  const byId = new Map(items.map((i) => [i.id, i]));
  return (
    <div className="evi-field" ref={box} onKeyDown={(e) => { if (e.key === "Escape" && open) { setOpen(false); (e.currentTarget.querySelector(".evi-sel") as HTMLElement | null)?.focus(); } }}>
      <span className="evi-label" id={id + "l"}>{label}</span>
      <button type="button" className="evi-sel" aria-haspopup="listbox" aria-expanded={open} aria-labelledby={id + "l " + id + "b"} disabled={!!disabledWhy} title={disabledWhy}
        onClick={() => { setOpen((o) => !o); setTimeout(() => input.current?.focus(), 0); }}>
        <span id={id + "b"} className={chosen.length ? "" : "ph"}>{disabledWhy ? disabledWhy : chosen.length ? `${chosen.length} selected${room <= 0 ? " (the most this page can show)" : ""}` : placeholder}</span><Icon name="arrow" className="evi-chev" />
      </button>
      {open && (
        <div className="evi-pop" role="group" aria-label={`Choose: ${label}`}>
          <label className="etf-search"><Icon name="search" /><span className="sr-only">Search {label}</span>
            <input ref={input} type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name or fund house" autoComplete="off" spellCheck={false} maxLength={60}
              onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); if (shown[0]) add(shown[0].id); } }} /></label>
          <ul className="evi-list" aria-label={`${label}: ${plural(shown.length, "match")}`}>
            {shown.map((i) => {
              const on = chosen.includes(i.id), full = !on && room <= 0;
              return (
                <li key={i.id}><button type="button" role="checkbox" aria-checked={on} disabled={full} onClick={() => add(i.id)} className={on ? "on" : ""}>
                  <span className="evi-box" aria-hidden="true">{on ? "✓" : ""}</span><span className="evi-it"><b>{i.title}</b><small>{i.sub}</small></span><span className="evi-tag2">{i.tag}</span></button></li>);
            })}
            {shown.length === 0 && <li className="evi-none faint">{items.length ? "No match." : "None in our data for this index."}</li>}
          </ul>
          <button type="button" className="btn sm" onClick={() => { setOpen(false); (box.current?.querySelector(".evi-sel") as HTMLElement | null)?.focus(); }}>Done</button>
        </div>)}
      {chosen.length > 0 && (
        <ul className="etf-chips evi-chips" aria-label={`Chosen: ${label}`}>{chosen.map((c) => (
          <li key={c}><span>{byId.get(c)?.title ?? c}</span><button type="button" aria-label={`Remove ${byId.get(c)?.title ?? c}`} onClick={() => onChange(chosen.filter((x) => x !== c))}>×</button></li>))}</ul>)}
    </div>
  );
}

function Section({ id, title, icon, open, onToggle, csv, children }: { id: SectionId; title: string; icon: string; open: boolean; onToggle: () => void; csv?: () => void; children: React.ReactNode }) {
  return (
    <section className="card etf-sec evi-sec" id={`evi-${id}`} aria-labelledby={`evi-h-${id}`}>
      <div className="card-h">
        <h2 id={`evi-h-${id}`} className="evi-h2"><button type="button" className="evi-sh" aria-expanded={open} aria-controls={`evi-b-${id}`} onClick={onToggle}>
          <span className="ci"><Icon name={icon} /></span>{title}<span className={"evi-caret" + (open ? " open" : "")} aria-hidden="true">▾</span></button></h2>
        {open && csv && <button type="button" className="btn sm" onClick={csv}><Icon name="download" />Download CSV</button>}
      </div>
      <div id={`evi-b-${id}`} hidden={!open}>{open && children}</div>
    </section>
  );
}

export function EtfVsIndexPage() {
  useDocTitle("ETF vs index fund", "Pick an index, then the ETFs and direct-plan index funds that follow it, and compare returns, costs, tracking, risk and a SIP calculation from stored prices and NAVs. Information only.");
  const [sp, setSp] = useSearchParams();
  const page = useMemo(() => parsePage(sp), [sp]);
  const [draft, setDraft] = useState<PageState>(page);
  const key = sp.toString();
  useEffect(() => { setDraft(page); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [key]);
  const opts = useEviOptions(draft.plan);
  const committed = sp.has("etf") && sp.has("fund") && readyToCompare(page);
  const res = useEviCompare(page, committed);
  const [open, setOpen] = useState<Record<SectionId, boolean>>({ performance: true, cost: true, tracking: true, risk: true, calculator: true, summary: true });
  const results = useRef<HTMLDivElement>(null);
  const top = useRef<HTMLDivElement>(null);

  const data = opts.data;
  const idx = data?.indices.find((i) => i.key === draft.index);
  const etfs = useMemo(() => (data?.etfs ?? []).filter((e) => e.index === draft.index), [data, draft.index]);
  const funds = useMemo(() => (data?.funds ?? []).filter((f) => f.index === draft.index), [data, draft.index]);
  const etfItems: Opt[] = etfs.map((e: EtfOpt) => ({ id: e.symbol, title: e.name, sub: `${e.symbol}${e.fundHouse ? " · " + e.fundHouse : ""}`, tag: rtShort(e.returnType) }));
  const fundItems: Opt[] = funds.map((f: FundOpt) => ({ id: String(f.code), title: f.name.replace(/\s*-\s*(Direct|Regular) Plan\s*-\s*Growth( Option)?/i, "").replace(/\s*-\s*Growth( Option)?$/i, ""), sub: `${f.amc} · ${f.plan} plan`, tag: rtShort(f.returnType) }));
  const have = (xs: Opt[], c: string[]) => c.filter((x) => xs.some((i) => i.id === x));
  // drop chosen products that this index/plan does not list (after the lists load)
  useEffect(() => {
    if (!data) return;
    const e = have(etfItems, draft.etf), f = have(fundItems, draft.fund.map(String)).map(Number);
    if (e.length !== draft.etf.length || f.length !== draft.fund.length) setDraft((d) => ({ ...d, etf: e, fund: f }));
    /* eslint-disable-next-line react-hooks/exhaustive-deps */
  }, [data, draft.index, draft.plan]);

  const used = draft.etf.length + draft.fund.length;
  const can = draft.etf.length >= 1 && draft.fund.length >= 1 && used <= MAX_PRODUCTS;
  const compare = () => {
    if (!can) return;
    setSp(toParams({ ...page, index: draft.index, etf: draft.etf, fund: draft.fund, plan: draft.plan }));
    setTimeout(() => results.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
  };
  const setIndex = (k: string) => setDraft((d) => ({ ...d, index: k, etf: [], fund: [] }));
  const setPlan = (p: PlanMode) => setDraft((d) => ({ ...d, plan: p }));
  const patch = (p: Partial<PageState>) => setSp(toParams({ ...page, ...p }), { replace: true });

  const jump = (id: SectionId) => {
    setOpen((o) => ({ ...o, [id]: true }));
    setTimeout(() => { const el = document.getElementById(`evi-${id}`); el?.scrollIntoView({ behavior: "smooth", block: "start" }); (document.getElementById(`evi-h-${id}`)?.querySelector("button") as HTMLElement | null)?.focus({ preventScroll: true }); }, 30);
  };
  const toggleAll = (v: boolean) => setOpen({ performance: v, cost: v, tracking: v, risk: v, calculator: v, summary: v });

  // calculator inputs: edited freely, applied with the button (each application is a new link)
  const [calc, setCalc] = useState({ sip: String(page.sip), lump: String(page.lump), start: page.start });
  useEffect(() => { setCalc({ sip: String(page.sip), lump: String(page.lump), start: page.start }); }, [page.sip, page.lump, page.start]);
  const sipN = Number(calc.sip), lumpN = Number(calc.lump);
  const calcBad = !(sipN >= 100 && sipN <= 10_000_000) ? "The monthly SIP must be between ₹100 and ₹1,00,00,000." : !(lumpN >= 1000 && lumpN <= 1_000_000_000) ? "The lump sum must be between ₹1,000 and ₹100 crore." : null;
  const calcDirty = sipN !== page.sip || lumpN !== page.lump || calc.start !== page.start;
  const applyCalc = () => { if (!calcBad) patch({ sip: sipN, lump: lumpN, start: calc.start }); };

  const d: Compare | undefined = res.data;
  const csv = (id: SectionId) => d ? () => downloadCsv(`finlit-${d.index.key}-${id}.csv`, sectionRows(d, id, page.risk || "all")) : undefined;
  const err = res.error as { status?: number; message?: string } | null;

  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap">
        <div className="eyebrow">ETF vs index fund</div><h1>One index, two kinds of fund.</h1>
        <p>Pick an index, then the ETFs and the direct-plan index funds that follow it. See how they compared on returns, costs, tracking and risk, using the prices and NAVs we store. Information only.</p>
        <nav className="evi-crumb" aria-label="Breadcrumb"><Link to="/etfs">← All ETFs</Link></nav></div></section>

      <div className="wrap etf-page evi-page">
        <div className="card evi-select" ref={top}>
          <div className="evi-sel-h">
            <span className="evi-badge-ic" aria-hidden="true"><Icon name="compare" /></span>
            <div><h2>ETF vs Index Fund <span className="evi-badge">Compare</span></h2>
              <p className="faint">Find out which investment vehicle tracks the same index more efficiently. Measured on stored prices, not on a promise.</p></div>
          </div>
          {opts.isError ? <ErrorState what="The list of indices" onRetry={() => opts.refetch()} /> : !data ? <Skeleton rows={3} /> : (
            <form className="evi-form" onSubmit={(e) => { e.preventDefault(); compare(); }}>
              <div className="evi-field">
                <label className="evi-label" htmlFor="evi-index">Select benchmark</label>
                <select id="evi-index" className="evi-sel evi-native" value={draft.index} onChange={(e) => setIndex(e.target.value)}>
                  {!data.indices.some((i) => i.key === draft.index) && <option value={draft.index}>{draft.index}</option>}
                  {data.indices.map((i) => <option key={i.key} value={i.key} disabled={!i.ready}>{i.label.toUpperCase()} · {plural(i.etfCount, "ETF")} · {plural(i.fundCount, "index fund")}{i.ready ? "" : " (needs both kinds)"}</option>)}
                </select>
              </div>
              <Picker label="Select ETF" placeholder="Choose ETF" items={etfItems} chosen={draft.etf} room={MAX_PRODUCTS - used}
                onChange={(ids) => setDraft((x) => ({ ...x, etf: ids }))} disabledWhy={etfs.length ? undefined : "No ETF in our data follows this index"} />
              <Picker label="Select Index Fund" placeholder="Choose Index Fund" items={fundItems} chosen={draft.fund.map(String)} room={MAX_PRODUCTS - used}
                onChange={(ids) => setDraft((x) => ({ ...x, fund: ids.map(Number) }))} disabledWhy={funds.length ? undefined : `No ${draft.plan === "Direct" ? "direct-plan " : ""}index fund in our data follows this index`} />
              <label className="evi-check"><input type="checkbox" checked={draft.plan === "All"} onChange={(e) => setPlan(e.target.checked ? "All" : "Direct")} />
                <span>Include regular plans<small>Direct plans only by default: a regular plan carries a distributor commission, so against an ETF the comparison would mislead.</small></span></label>
              <button type="submit" className="evi-go" disabled={!can}>Compare products</button>
              <p className="evi-hint faint" aria-live="polite">{can ? `${plural(draft.etf.length, "ETF")} and ${plural(draft.fund.length, "index fund")} chosen.` : used >= MAX_PRODUCTS ? "Four products is the most this page can show." : "Choose at least one ETF and one index fund (four products at most)."}</p>
              {idx && <p className="evi-hint faint">{idx.label}: {plural(etfs.length, "ETF")} and {plural(funds.length, "index fund")} listed. Each product is placed by the benchmark its fund house states, or by the index in its registered name. Variants such as “equal weight” are kept apart. {data.unmatchedFunds ? `${plural(data.unmatchedFunds, "index fund")} in our data follow an index not on this list or do not name one.` : ""}</p>}
            </form>)}
        </div>

        <div ref={results} className="evi-results" aria-live="polite">
          {!committed ? (
            <div className="etf-state"><h2>Comparison dashboard</h2><p>Choose an index, at least one ETF and one index fund, then press <b>Compare products</b>. Six sections appear here: performance, cost, tracking, risk, an investment calculator and a summary by category.</p></div>
          ) : res.isError && !d ? (
            err?.status && err.status < 500 ? <div className="etf-state" role="alert"><h2>This comparison is not possible</h2><p>{err.message}</p></div> : <ErrorState what="The comparison" onRetry={() => res.refetch()} />
          ) : !d ? <Skeleton rows={6} /> : (
            <>
              <div className="evi-sticky" role="group" aria-label="Your comparison">
                <b>{d.index.label}</b>
                <ul>{d.products.map((p, i) => <li key={p.id}><svg width="22" height="8" aria-hidden="true"><line x1="1" x2="21" y1="4" y2="4" stroke={COLORS[i]} strokeWidth="3" strokeDasharray={DASHES[i]} /></svg>{p.label}</li>)}</ul>
                <span className="faint">as of {day(d.asOf)}</span>
                <button type="button" className="evi-edit" onClick={() => top.current?.scrollIntoView({ behavior: "smooth", block: "start" })}>Change selection</button>
              </div>
              <div className="card evi-dash">
                <div className="card-h"><h2 className="evi-h2">Comparison dashboard</h2>
                  <div className="evi-allbtns"><button type="button" className="btn sm" onClick={() => toggleAll(true)}>Open all</button><button type="button" className="btn sm" onClick={() => toggleAll(false)}>Close all</button></div></div>
                <ul className="evi-tiles">{TILES.map((t) => (
                  <li key={t.id}><a href={`#evi-${t.id}`} className="evi-tile" onClick={(e) => { e.preventDefault(); jump(t.id); }}>
                    <span className="evi-tic" aria-hidden="true"><Icon name={t.icon} /></span><span><b>{t.title}</b><small>{t.sub}</small></span><span className="evi-go2" aria-hidden="true">→</span></a></li>))}</ul>
                <ul className="evi-prods">{d.products.map((p, i) => (
                  <li key={p.id}><svg width="26" height="8" aria-hidden="true"><line x1="1" x2="25" y1="4" y2="4" stroke={COLORS[i]} strokeWidth="3" strokeDasharray={DASHES[i]} /></svg>
                    <div><b>{p.label}</b><small>{p.kind === "etf" ? "ETF" : "Index fund"} · measured on {p.basis === "nav" ? "NAV" : "closing price"} ({p.source}) · {day(p.first)} to {day(p.last)}</small></div></li>))}</ul>
              </div>
              {d.common.why && <div className="etf-state small" role="status"><p>{d.common.why}</p></div>}
              {d.notes.length > 0 && <ul className="evi-notes" aria-label="Notes on how the products are measured">{d.notes.map((n) => <li key={n}><Icon name="info" />{n}</li>)}</ul>}
              <Section id="performance" title="Performance" icon="growth" open={open.performance} onToggle={() => setOpen((o) => ({ ...o, performance: !o.performance }))} csv={d.returns ? csv("performance") : undefined}>
                <Performance d={d} page={page} setRange={(r: RangeKey) => patch({ range: r })} /></Section>
              <Section id="cost" title="Cost analysis" icon="rupee" open={open.cost} onToggle={() => setOpen((o) => ({ ...o, cost: !o.cost }))} csv={csv("cost")}><Cost d={d} /></Section>
              <Section id="tracking" title="Tracking quality" icon="gauge" open={open.tracking} onToggle={() => setOpen((o) => ({ ...o, tracking: !o.tracking }))} csv={d.tracking ? csv("tracking") : undefined}><TrackingBlock d={d} /></Section>
              <Section id="risk" title="Risk analysis" icon="activity" open={open.risk} onToggle={() => setOpen((o) => ({ ...o, risk: !o.risk }))} csv={d.risk ? csv("risk") : undefined}>
                <RiskBlock d={d} page={page} setRisk={(k) => patch({ risk: k })} /></Section>
              <Section id="calculator" title="Investment calculator" icon="wallet" open={open.calculator} onToggle={() => setOpen((o) => ({ ...o, calculator: !o.calculator }))} csv={d.lump ? csv("calculator") : undefined}>
                <Calculator d={d} draft={calc} setDraft={setCalc} apply={applyCalc} dirty={calcDirty && !calcBad} />{calcBad && <p className="evi-err" role="alert">{calcBad}</p>}</Section>
              <Section id="summary" title="Summary by category" icon="check" open={open.summary} onToggle={() => setOpen((o) => ({ ...o, summary: !o.summary }))} csv={d.summary ? csv("summary") : undefined}><Summary d={d} /></Section>
              <aside className="etf-note evi-foot" aria-label="About this data">
                <p><b>{DISCLAIMER}</b></p>
                <p>Products are measured on the dates they all have a price or NAV for, from {day(d.common.from)} to {day(d.common.to)}. ETFs: NSE closing prices through our market-data providers (or the AMFI NAV where we store its history); index funds: AMFI NAV; the index line: a price index, dividends not included. Expense ratio, exit load and benchmark: AMFI and fund-house disclosures, each with its date. Figures marked — are not available; the reason is shown beside them.</p>
                <p>The summary describes which product was ahead on a measure over past dates. It is not advice, a rating or a forecast. Brokerage, taxes and the bid-ask spread of an ETF are not included. See the <Link to="/glossary">glossary</Link> for the words used and <Link to="/etfs/compare">compare ETFs</Link> for ETF against ETF.</p>
                <p className="faint">{nf(d.common.days, 0)} common dates · generated {new Date(d.generatedAt).toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit", timeZone: "Asia/Kolkata" })} IST</p>
              </aside>
            </>)}
        </div>
      </div>
    </>
  );
}

