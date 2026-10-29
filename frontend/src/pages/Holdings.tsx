import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { AlertButton } from "../components/AlertComposer";
import { Icon } from "../lib/icons";
import { Gate } from "../components/Gate";
import { Donut, RankBars } from "../charts/Atlas";
import { useDocTitle } from "../lib/title";
import { useUI } from "../lib/ui";
import { limitsFor, useAuth } from "../lib/auth";
import { DEMO } from "../lib/demo";
import { useSearchIndex } from "../lib/api";
import { useUniverse } from "../lib/screener";
import { portfolio, usePortfolio } from "../lib/portfolio";
import { signals } from "./Watchlist";
import { saveFile } from "../stock/derive";
import { PortfolioInsights } from "../components/PortfolioInsights";
import { PortfolioLab } from "../components/PortfolioLab";
import { CAP_BUCKETS, capBucket } from "../lib/capBuckets";
import { ACCEPT, namesFromFile } from "../lib/holdingsFile";
import { PdfImport } from "../components/PdfImport";
import { isPdf } from "../lib/holdingsPdf";
import { makeMatcher, matchNames, namesFrom } from "../lib/holdingsMatch";
import { nf } from "../lib/format";
import { PortfolioTable, SummaryTiles, TabStrip } from "../components/PortfolioTabs";
import { MODEL_BANNER, csvName, isReady, modelFor, parsePeriod, parseTab, summarize, toCsv, useOverview, withTab, type Line, type Period, type Tab } from "../lib/portfolioOverview";

/** My portfolio as a scorecard: give it the names of the shares you hold (typed, pasted or a CSV file) and it shows three tabs over them: Overview (price, size and
 *  the plan's score model: FinLit for Silver, FinLit Prism for Gold), Ratios and Financials, from one bulk read of the stored reports. No quantities or prices are asked for. */

const K = ["var(--k1)", "var(--k2)", "var(--k3)", "var(--k7)", "var(--k5)", "var(--k4)", "var(--k6)", "var(--k8)"];
const BAND_ROWS = [["hi", "Green", "70 or more", "var(--band-hi)"], ["mid", "Orange", "50 to 69", "var(--band-mid)"], ["lo", "Red", "under 50", "var(--band-lo)"], ["na", "Not scored yet", "", "var(--s3)"]] as const;

/* ---------------------------------------------------------------- page */

export function HoldingsPage() {
  useDocTitle("My portfolio", "Add the shares you hold, by name or from a CSV, and see each one's FinLit score, the portfolio's average score, band mix and sector spread.");
  const { plan, toast } = useUI();
  const { isAdmin } = useAuth();
  const qc = useQueryClient();
  const model = modelFor(plan, isAdmin);          // Silver: the basic FinLit score. Gold: FinLit Prism only. Basic: the page is gated.
  const [params, setParams] = useSearchParams();
  const tab = parseTab(params.get("tab")), period = parsePeriod(params.get("period"));
  const go = (t: Tab, pd: Period = period) => setParams(withTab(params.toString(), t, pd), { replace: true });
  const st = usePortfolio();
  const uni = useUniverse(), idx = useSearchIndex(true);
  const by = useMemo(() => new Map((uni.data?.rows || []).map((r) => [r.symbol, r])), [uni.data]);
  const index = idx.data?.rows || [];
  const cap = limitsFor(plan).holdings;
  const [text, setText] = useState(""), [one, setOne] = useState(""), [missing, setMissing] = useState<string[]>([]);
  const file = useRef<HTMLInputElement>(null), [busy, setBusy] = useState(false), [pdf, setPdf] = useState<File | null>(null);
  const matcher = useMemo(() => makeMatcher(index), [index]);

  const symbols = useMemo(() => [...new Set(st.holdings.map((h) => h.symbol))], [st.holdings]);
  // One bulk read feeds all three tabs. A company with no stored report is queued for building by that read itself and shows "Preparing…" until it is ready.
  const ov = useOverview(symbols, !!model && !DEMO);
  const byOv = useMemo(() => new Map((ov.data?.holdings || []).map((h) => [h.symbol, h])), [ov.data]);
  const lines = useMemo(() => symbols.map((s) => ({ symbol: s, row: by.get(s), ov: byOv.get(s), id: st.holdings.find((h) => h.symbol === s)!.id, name: by.get(s)?.name || index.find((r) => r[0] === s)?.[1] || "" })), [symbols, by, byOv, st.holdings, index]);
  const flags = useMemo(() => Object.fromEntries(lines.flatMap((l) => { const f = l.row && model === "finlit" ? signals(l.row)[0] : null; return f ? [[l.symbol, f]] : []; })), [lines, model]);
  useEffect(() => { if (!DEMO && symbols.length && uni.data && lines.some((l) => !l.row)) { const t = setInterval(() => qc.invalidateQueries({ queryKey: ["universe"] }), 20_000); return () => clearInterval(t); } }, [symbols.length, uni.data, lines, qc]);   // the lab and insights read the universe: refresh while some share is new to it

  const m = useMemo(() => {
    const sum = model ? summarize(lines as Line[], model) : null, n = lines.length || 1;
    const sector = new Map<string, number>(); lines.forEach((l) => { const k = (isReady(l.ov) && l.ov.sector) || l.row?.sector || "Not yet loaded"; sector.set(k, (sector.get(k) || 0) + 100 / n); });
    const cap = new Map<string, string[]>(); lines.forEach((l) => { const id = capBucket((isReady(l.ov) ? l.ov.marketCapCr : null) ?? l.row?.market_cap)?.id ?? "unknown"; cap.set(id, [...(cap.get(id) || []), l.symbol]); });
    return { sum, sector: [...sector.entries()].sort((a, b) => b[1] - a[1]), cap };
  }, [lines, model]);

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
  const exportCsv = () => model && saveFile(csvName(tab, period), toCsv(lines as Line[], tab, model, period), "text/csv;charset=utf-8");
  const CAP_COLORS = ["var(--k1)", "var(--k7)", "var(--k3)", "var(--k4)", "var(--k2)", "var(--k8)"];
  const capParts = CAP_BUCKETS.map((b, i) => ({ label: b.label, value: m.cap.get(b.id)?.length || 0, color: CAP_COLORS[i], note: (m.cap.get(b.id) || []).slice(0, 6).join(", ") })).filter((p) => p.value > 0);
  const capUnknown = m.cap.get("unknown")?.length || 0;
  const donut = m.sector.slice(0, 7).map(([label, value], i) => ({ label, value, color: K[i % K.length] }));
  const empty = !lines.length;

  return (
    <div className="wrap ipo">
      <header className="dash-h"><div><div className="eyebrow">My lists</div><h1>My portfolio</h1><p className="muted">Add the shares you hold and see how strong they are: each company's score, its ratios and its latest financials, and the portfolio as a whole. Only names are needed; nothing is sent to a broker.</p></div></header>
      <Gate tier="silver" title="Score your portfolio" points={["FinLit score and pillars for every share you hold (Gold: FinLit Prism)", "Ratios and latest financials in one table", "Average score, band mix and sector spread", "Import Excel, CSV or PDF statements"]}>
        {model && <aside className="pf-model" aria-label="Which score model this page uses"><span className="ci"><Icon name="quality" /></span>
          <p>{MODEL_BANNER[model]}{model === "finlit" && <> <Link to="/plans">See the Gold plan</Link>.</>}</p></aside>}
        <section className="card acct-c pf-in">
          <h2>Add your shares</h2>
          <p className="muted">Type a name or ticker, paste a list, or choose the file you downloaded from your broker (Excel .xlsx or .xls, .csv, or a PDF statement). Only the share names are taken: quantities, prices and dates in the file are ignored, and the sheet's other columns do not matter. Names such as <code>Reliance Industries</code>, <code>HDFC Bank Ltd</code>, <code>TCS-EQ</code> or <code>500325</code> all work.</p>
          <div className="pf-add">
            <form className="pf-one" onSubmit={(e) => { e.preventDefault(); add([one.trim()].filter(Boolean)); setOne(""); }}>
              <input list="pf-names" value={one} onChange={(e) => setOne(e.target.value)} placeholder="e.g. RELIANCE or Infosys" aria-label="Share name or ticker" autoComplete="off" maxLength={80} />
              <datalist id="pf-names">{index.slice(0, 500).map((r) => <option key={r[0]} value={r[0]}>{r[1]}</option>)}</datalist>
              <button className="btn primary">Add</button>
            </form>
            <div className="pf-bulk">
              <textarea className="imp" rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder={"RELIANCE\nHDFC Bank\nInfosys Ltd\nTCS"} aria-label="Share names to add, one per line" />
              <div className="row"><button className="btn primary" onClick={() => { add(namesFrom(text, matcher)); setText(""); }} disabled={!text.trim()}>Add these</button>
                <button className="btn" onClick={() => file.current?.click()} disabled={busy}><Icon name="table" />{busy ? "Reading…" : "Choose Excel, CSV or PDF…"}</button>
                <input ref={file} type="file" accept={ACCEPT + ",.pdf,application/pdf"} hidden onChange={async (e) => { const f = e.target.files?.[0]; e.target.value = ""; if (!f) return; if (isPdf(f)) { setPdf(f); return; } setBusy(true);
                  try { add(await namesFromFile(f, matcher), f.name); } catch (err) { toast(err instanceof Error && err.message.startsWith("That file") ? err.message : "That file could not be read. Save it as .xlsx or .csv, or paste the share names instead."); } finally { setBusy(false); } }} /></div>
            </div>
          </div>
          {pdf && <PdfImport file={pdf} index={index} held={symbols} room={Math.max(0, cap - symbols.length)} onClose={() => setPdf(null)}
            onAdd={(syms) => { portfolio.addMany(syms.map((sym) => ({ symbol: sym, qty: 1, price: 0 }))); toast(`Added ${syms.length} ${syms.length === 1 ? "share" : "shares"} from the PDF.`); }} />}
          {missing.length > 0 && <p className="pf-miss" role="status"><b>Not recognised:</b> {missing.slice(0, 20).join(", ")}{missing.length > 20 ? ` and ${missing.length - 20} more` : ""}. Check the spelling or use the NSE ticker.</p>}
        </section>

        {empty ? <div className="card dw-empty"><span className="dw-ei"><Icon name="wallet" /></span><b>No shares yet</b><p>Add the shares you hold above. {DEMO ? "" : <>You can also <Link to="/watchlist">start from your watchlist</Link>.</>}</p></div> : model && <>
          <TabStrip tab={tab} onTab={(t) => go(t)} />
          <div id="pf-panel" role="tabpanel" aria-labelledby={`pf-tab-${tab}`} className="pf-panel">
          {tab === "overview" && <>
            <SummaryTiles lines={lines as Line[]} model={model} limit={cap} />
            <div className="pf-g">
              <section className="card"><div className="card-h"><h3><span className="ci"><Icon name="quality" /></span>{model === "prism" ? "Average by Prism part" : "Average by pillar"}</h3><span className="s">0 to 100</span></div>
                {m.sum && m.sum.parts.length ? <RankBars rows={m.sum.parts.map((p) => ({ label: p.label, value: p.value }))} fmt={(x) => nf(x, 0)} /> : <p className="muted">Averages appear when the first scores are ready.</p>}</section>
              <section className="card"><div className="card-h"><h3><span className="ci"><Icon name="quality" /></span>By score colour</h3><span className="s">Share of your shares</span></div>
                <div className="breadth big" role="img" aria-label="Portfolio by score colour">{BAND_ROWS.filter(([k]) => m.sum?.bands[k]).map(([k, , , c]) => <i key={k} style={{ flex: m.sum!.bands[k], background: c }} />)}</div>
                <ul className="bandk">{BAND_ROWS.map(([k, label, rule, c]) => <li key={k}><i style={{ background: c }} /><span>{label}{rule ? <small className="muted"> {rule}</small> : null}</span><b>{m.sum?.bands[k] || 0} ({nf(((m.sum?.bands[k] || 0) / (lines.length || 1)) * 100, 0)}%)</b></li>)}</ul></section>
              <section className="card"><div className="card-h"><h3><span className="ci"><Icon name="pie" /></span>By sector</h3><span className="s">Share of your shares</span></div><Donut parts={donut} center={String(m.sector.length)} sub={m.sector.length === 1 ? "SECTOR" : "SECTORS"} /></section>
              <section className="card pf-cap"><div className="card-h"><h3><span className="ci"><Icon name="pie" /></span>By market cap</h3><span className="s">Size of the companies you hold</span></div>
                {capParts.length ? <Donut parts={capParts} center={String(lines.length - capUnknown)} sub={lines.length - capUnknown === 1 ? "COMPANY" : "COMPANIES"} /> : <p className="muted">Market values are still loading for these companies.</p>}
                <table className="pf-cap-t"><caption className="sr-only">Your shares by company size</caption><thead><tr><th scope="col">Size</th><th scope="col">Market cap (₹ crore)</th><th scope="col">Shares</th></tr></thead>
                  <tbody>{CAP_BUCKETS.map((b, i) => { const syms = m.cap.get(b.id) || []; return (
                    <tr key={b.id} className={syms.length ? "" : "none"}><th scope="row"><i style={{ background: CAP_COLORS[i] }} aria-hidden="true" />{b.label}</th><td>{b.range}</td>
                      <td title={syms.join(", ")}><b>{syms.length}</b>{syms.length > 0 && <small>{syms.slice(0, 3).join(", ")}{syms.length > 3 ? ` +${syms.length - 3}` : ""}</small>}</td></tr>); })}
                    {capUnknown > 0 && <tr className="unk"><th scope="row"><i aria-hidden="true" />Not known yet</th><td>value still loading</td><td title={(m.cap.get("unknown") || []).join(", ")}><b>{capUnknown}</b></td></tr>}</tbody></table>
                <p className="faint pf-cap-n">Each share counts once: quantities and prices in your file are not used, so this shows how many of your companies sit in each size band, not how much money does. Bands are FinLit's own money bands, not an official list.</p></section>
            </div></>}
          <PortfolioTable lines={lines as Line[]} model={model} tab={tab} period={period} limit={cap} state={ov.isError ? "error" : ov.isPending && !DEMO ? "loading" : "ready"}
            errorText={DEMO ? "Scores are not available in the demo preview." : ov.error?.body?.detail} onPeriod={(pd) => go("financials", pd)} onExport={exportCsv} flags={flags}
            actions={(sym) => <><AlertButton symbol={sym} className="btn" /> <button className="btn" aria-label={`Remove ${sym}`} onClick={() => { st.holdings.filter((h) => h.symbol === sym).forEach((h) => portfolio.remove(h.id)); toast(`${sym} removed.`); }}>✕</button></>} />
          </div>
          <p className="faint" style={{ fontSize: 12.5, margin: "-6px 4px 0" }}>Scores come from each company's latest statements and prices. A share shows "Preparing…" for a moment the first time it is added. Information only, not investment advice.</p>
          {model === "finlit" && <><PortfolioInsights lines={lines} />
          <PortfolioLab lines={lines} universe={uni.data?.rows || []} /></>}</>}
      </Gate>
    </div>
  );
}
