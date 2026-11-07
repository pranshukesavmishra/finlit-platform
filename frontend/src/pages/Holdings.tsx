import { PageHeader } from "../components/PageHeader";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Gate } from "../components/Gate";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import { useUI } from "../lib/ui";
import { limitsFor, useAuth } from "../lib/auth";
import { DEMO } from "../lib/demo";
import { useSearchIndex } from "../lib/api";
import { useUniverse } from "../lib/screener";
import { portfolio, usePortfolio } from "../lib/portfolio";
import { saveFile } from "../stock/derive";
import { PdfImport } from "../components/PdfImport";
import { ACCEPT, namesFromFile } from "../lib/holdingsFile";
import { isPdf } from "../lib/holdingsPdf";
import { makeMatcher, matchNames, namesFrom } from "../lib/holdingsMatch";
import { MODEL_BANNER, csvName, modelFor, parsePeriod, parseTab, toCsv, useOverview, withTab, type Line, type OverviewHolding, type Period, type Tab } from "../lib/portfolioOverview";
import { usePortfolioPage } from "../portfolio/usePortfolioPage";
import { Summary } from "../portfolio/Summary";
import { ScoreMade, WhatThisMeans } from "../portfolio/Readings";
import { CountTable, HeatTable, MixCards, Treemap, WhereReadings } from "../portfolio/Where";
import { Together } from "../portfolio/Together";
import { Nifty, RiskShare } from "../portfolio/Risk";
import { Style } from "../portfolio/Style";
import { SharesTable, partDefs } from "../portfolio/SharesTable";
import { sectorColors, sectorOrder, plural } from "../portfolio/derive";
import { ADD_NOTE, HEAD_DESC, MODE_LABEL, MODE_SHORT, NAV, SIZES_NOTE } from "../portfolio/words";
import type { Mode } from "../portfolio/types";
import "../portfolio/pf.css";

/** Equity portfolio: give it the names of the shares you own (typed, pasted or from a broker file) and it describes the list: how strong each share is, where the list sits by
 *  sector and size, what moves together, where the risk comes from and how the list has moved against the NIFTY 50. Names only: quantities, prices and dates are never asked for.
 *  Every figure and every sentence comes from POST /api/portfolio/page (the handover pack's engine) and POST /api/portfolio/overview (live price and the plan's scores). */

export function HoldingsPage() {
  useDocTitle("Equity portfolio", "Add the shares you own, by name or from a broker file, and see how strong each one is, how spread out the list is, what moves together and where the risk comes from.");
  const { plan, toast } = useUI();
  const { isAdmin } = useAuth();
  const qc = useQueryClient();
  const model = modelFor(plan, isAdmin);          // Silver: the basic FinLit IQ. Gold: FinLit Prism only. Basic: the page is gated.
  const [params, setParams] = useSearchParams();
  const tab = parseTab(params.get("tab")), period = parsePeriod(params.get("period"));
  const go = (t: Tab, pd: Period = period) => setParams(withTab(params.toString(), t, pd), { replace: true });
  const st = usePortfolio();
  const uni = useUniverse(), idx = useSearchIndex(true);
  const by = useMemo(() => new Map((uni.data?.rows || []).map((r) => [r.symbol, r])), [uni.data]);
  const index = idx.data?.rows || [];
  const cap = limitsFor(plan).holdings;
  const [one, setOne] = useState(""), [text, setText] = useState(""), [pasting, setPasting] = useState(false), [missing, setMissing] = useState<string[]>([]);
  const file = useRef<HTMLInputElement>(null), [busy, setBusy] = useState(false), [pdf, setPdf] = useState<File | null>(null);
  const matcher = useMemo(() => makeMatcher(index), [index]);
  const [mode, setMode] = useState<Mode>("eq");
  const [together, setTogether] = useState<boolean | null>(null);
  const [nav, setNav] = useState<string>(NAV[0][0]);

  const symbols = useMemo(() => [...new Set(st.holdings.map((h) => h.symbol))], [st.holdings]);
  const ov = useOverview(symbols, !!model && !DEMO);
  const pg = usePortfolioPage(symbols, !!model && !DEMO);
  const byOv = useMemo(() => new Map((ov.data?.holdings || []).map((h) => [h.symbol, h])), [ov.data]);
  const lines: Line[] = useMemo(() => symbols.map((s) => ({ symbol: s, ov: byOv.get(s), name: by.get(s)?.name || index.find((r) => r[0] === s)?.[1] || "" })), [symbols, by, byOv, index]);
  useEffect(() => { if (!DEMO && symbols.length && uni.data && lines.some((l) => !l.ov)) { const t = setInterval(() => qc.invalidateQueries({ queryKey: ["universe"] }), 20_000); return () => clearInterval(t); } }, [symbols.length, uni.data, lines, qc]);

  const data = pg.data, page = data?.page ?? null, meta = data?.meta ?? {};
  const colors = useMemo(() => (page ? sectorColors(sectorOrder(page, "eq")) : {}), [page]);
  const ovMap = byOv as Map<string, OverviewHolding>;
  const ids = data?.symbols ?? symbols;
  const state: "loading" | "ready" | "error" | "none" = DEMO ? "none" : pg.isError ? "error" : pg.isPending && symbols.length ? "loading" : "ready";
  const open = together ?? page?.together_open_by_default ?? false;

  const add = (names: string[], from?: string) => {
    if (!names.length) { toast(from ? `No share names found in ${from}. It should have a column with the share names (Symbol, Stock, Instrument or Company).` : "No share names found. Put one name or ticker per line, or paste the Name column from your broker."); return; }
    if (!index.length) { toast("The company list is still loading. Try again in a moment."); return; }
    const { found, missing: miss } = matchNames(names, index);
    const fresh = [...new Map(found.filter((f) => !symbols.includes(f.symbol)).map((f) => [f.symbol, f])).values()];
    const room = Math.max(0, cap - symbols.length), take = fresh.slice(0, room);
    if (take.length) portfolio.addMany(take.map((f) => ({ symbol: f.symbol, qty: 1, price: 0 })));
    setMissing(miss);
    toast([take.length ? `Added ${take.length} ${take.length === 1 ? "share" : "shares"}` : "Nothing new to add", miss.length ? `${miss.length} not recognised (listed below)` : "", fresh.length > room ? `your plan holds up to ${cap}` : ""].filter(Boolean).join(" · ") + ".");
  };
  const exportCsv = () => model && saveFile(csvName(tab, period), toCsv(lines, tab, model, period), "text/csv;charset=utf-8");
  const goTo = (id: string) => { setNav(id); document.getElementById("pf-" + id)?.scrollIntoView({ behavior: "smooth", block: "start" }); };
  const parts = model ? partDefs(model) : [];
  const partAvg = parts.map((d) => { const v = lines.flatMap((l) => (l.ov?.status === "ready" ? [d.get(l.ov)] : [])).filter((x): x is number => x != null); return { label: d.label, value: v.length ? v.reduce((a, b) => a + b, 0) / v.length : null }; });
  const scoreLines = model ? lines.map((l) => ({ v: l.ov?.status === "ready" ? (model === "prism" ? l.ov.prism?.final : l.ov.finlit?.overall) ?? null : null })) : [];
  const empty = !lines.length;
  const metas = ids.map((s) => meta[s]).filter(Boolean);
  const common = page && model ? { page, meta, symbols: ids, mode, colors, model, ov: ovMap } : null;

  return (
    <div className="wrap ipo pfx">
      <PageHeader plan="silver" title="Equity portfolio" art="portfolio" links={["/mf-portfolio", "/watchlist", "/alerts"]} description={HEAD_DESC} />
      <Gate tier="silver" title="Score your portfolio" points={["FinLit IQ and pillars for every share you own (Gold: FinLit Prism)", "How spread out the list is, and what moves together", "Share of risk and the NIFTY 50 comparison", "Import Excel, CSV or PDF statements"]}>
        <div className="pfx-flow">
        {model && <aside className="pf-model" aria-label="Which score model this page uses"><span className="ci"><Icon name="quality" /></span>
          <p>{MODEL_BANNER[model]}{model === "finlit" && <> <Link to="/plans">See the Gold plan</Link>.</>}</p></aside>}
        <section className="pfx-card pfx-addbar" aria-label="Add shares">
          <form className="pfx-add" onSubmit={(e) => { e.preventDefault(); add([one.trim()].filter(Boolean)); setOne(""); }}>
            <label className="pfx-input"><span className="sr-only">Add a share by name or ticker</span><Icon name="search" />
              <input list="pf-names" value={one} onChange={(e) => setOne(e.target.value)} placeholder="Add a share: name or ticker, e.g. RELIANCE" autoComplete="off" maxLength={80} /></label>
            <datalist id="pf-names">{index.slice(0, 500).map((r) => <option key={r[0]} value={r[0]}>{r[1]}</option>)}</datalist>
            <button className="pfx-solid">Add</button>
            <button type="button" className="pfx-btn" aria-expanded={pasting} onClick={() => setPasting((v) => !v)}>Paste a list</button>
            <button type="button" className="pfx-btn" onClick={() => file.current?.click()} disabled={busy}>{busy ? "Reading…" : "Upload broker file"}</button>
            <input ref={file} type="file" accept={ACCEPT + ",.pdf,application/pdf"} hidden onChange={async (e) => { const f = e.target.files?.[0]; e.target.value = ""; if (!f) return; if (isPdf(f)) { setPdf(f); return; } setBusy(true);
              try { add(await namesFromFile(f, matcher), f.name); } catch (err) { toast(err instanceof Error && err.message.startsWith("That file") ? err.message : "That file could not be read. Save it as .xlsx or .csv, or paste the share names instead."); } finally { setBusy(false); } }} />
            <span className="pfx-cap">{symbols.length} of {cap} shares on your plan</span>
          </form>
          <p className="pfx-note">{ADD_NOTE}</p>
          {pasting && <div className="pfx-paste"><textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder={"RELIANCE\nHDFC Bank\nInfosys Ltd\nTCS"} aria-label="Share names to add, one per line" />
            <button className="pfx-solid" onClick={() => { add(namesFrom(text, matcher)); setText(""); }} disabled={!text.trim()}>Add these</button></div>}
          {pdf && <PdfImport file={pdf} index={index} held={symbols} room={Math.max(0, cap - symbols.length)} onClose={() => setPdf(null)}
            onAdd={(syms) => { portfolio.addMany(syms.map((sym) => ({ symbol: sym, qty: 1, price: 0 }))); toast(`Added ${syms.length} ${syms.length === 1 ? "share" : "shares"} from the PDF.`); }} />}
          {missing.length > 0 && <p className="pf-miss" role="status"><b>Not recognised:</b> {missing.slice(0, 20).join(", ")}{missing.length > 20 ? ` and ${missing.length - 20} more` : ""}. Check the spelling or use the NSE ticker.</p>}
        </section>

        {empty ? <div className="card dw-empty"><span className="dw-ei"><Icon name="wallet" /></span><b>No shares yet</b><p>Add the shares you own above. {DEMO ? "" : <>You can also <Link to="/watchlist">start from your watchlist</Link>.</>}</p></div> : model && <>
          <Summary page={page} metas={metas} lines={lines} model={model} n={lines.length} state={state === "ready" && !page ? "none" : state} />
          {data && data.unknown.length > 0 && <p className="pfx-warn" role="status">Not in FinLit's company list, so left out of the figures: {data.unknown.join(", ")}.</p>}
          {data && data.noPrices.length > 0 && <p className="pfx-note" role="status">No stored prices yet for {data.noPrices.join(", ")}: {plural(data.noPrices.length, "share")} left out of the co-movement figures.</p>}
          {DEMO && <p className="pfx-note" role="status">The diversification figures are not available in the demo preview.</p>}
          {state === "error" && <p className="pfx-warn" role="alert">{pg.error?.body?.detail || "The figures for this list could not be loaded. Try again in a moment."}</p>}
          {page && common && <>
            <div className="pfx-bar-row">
              <nav aria-label="On this page" className="pfx-nav">{NAV.filter(([id]) => id !== "style" || data?.styleTilt).map(([id, label]) => <button key={id} type="button" className={"pfx-pillbtn" + (nav === id ? " on" : "")} aria-current={nav === id ? "true" : undefined} onClick={() => goTo(id)}>{label}</button>)}</nav>
              <div className="pfx-mode" role="group" aria-label="How amounts are counted"><span>Count as</span>{(["eq", "mc"] as const).map((m) => <button key={m} type="button" aria-pressed={mode === m} className={mode === m ? "on" : ""} onClick={() => setMode(m)}><span className="pfx-long">{MODE_LABEL[m]}</span><span className="pfx-compact">{MODE_SHORT[m]}</span></button>)}</div>
            </div>
            <div className="pfx-row"><WhatThisMeans page={page} mode={mode} onOpenTogether={() => setTogether(true)} /><ScoreMade page={page} /></div>
            <div className="pfx-row" id="pf-where">
              <section className="pfx-card pfx-grow" aria-labelledby="pfx-wh"><div className="pfx-h"><h2 id="pfx-wh">{page.layout === "long" ? "Where your list sits" : "Where your list sits: sector and size"}</h2>
                <p className="pfx-note">{page.layout === "long" ? "Each block is a sector and each tile a share. Bigger means more of the list; the tile colour is its score." : "Each chip is one share. Darker cells contain more of the list."}</p></div>
                {page.layout === "long" ? <Treemap {...common} /> : <HeatTable {...common} />}
                {page.layout === "long" && <p className="pfx-legend"><span><i className="b-hi lg" />Score 70+</span><span><i className="b-mid lg" />50–69</span><span><i className="b-lo lg" />Under 50</span><span className="pfx-note">Hover a tile for the company name and its share of the list.</span></p>}
                <WhereReadings page={page} mode={mode} />
                {page.layout === "short" && <p className="pfx-fine">{SIZES_NOTE}</p>}</section>
              {page.layout === "long" ? <CountTable page={page} meta={meta} symbols={ids} mode={mode} colors={colors} /> : <MixCards lines={scoreLines} model={model} parts={partAvg} />}
            </div>
            <Together page={page} meta={meta} mode={mode} colors={colors} open={open} onToggle={() => setTogether(!open)}>{page.layout === "long" && <div className="pfx-row"><ScoreMade page={page} /></div>}</Together>
            <div className="pfx-row"><RiskShare page={page} mode={mode} colors={colors} /><Nifty page={page} mode={mode} /></div>
            <Style tilt={data?.styleTilt} />
          </>}
          <SharesTable lines={lines} meta={meta} page={page} mode={mode} colors={colors} model={model} tab={tab} period={period} limit={cap} state={ov.isError ? "error" : ov.isPending && !DEMO ? "loading" : "ready"}
            errorText={DEMO ? "Scores are not available in the demo preview." : ov.error?.body?.detail} onTab={(t) => go(t)} onPeriod={(pd) => go("financials", pd)} onExport={exportCsv}
            actions={(sym) => <button className="pfx-x" aria-label={`Remove ${sym}`} title={`Remove ${sym}`} onClick={() => { st.holdings.filter((h) => h.symbol === sym).forEach((h) => portfolio.remove(h.id)); toast(`${sym} removed.`); }}>×</button>} />
        </>}
        </div>
      </Gate>
    </div>
  );
}
