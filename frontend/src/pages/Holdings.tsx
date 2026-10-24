import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { HScroll } from "../components/HScroll";
import { AlertButton } from "../components/AlertComposer";
import { Icon } from "../lib/icons";
import { Gate } from "../components/Gate";
import { Donut, RankBars } from "../charts/Atlas";
import { useDocTitle } from "../lib/title";
import { useUI } from "../lib/ui";
import { limitsFor } from "../lib/auth";
import { DEMO } from "../lib/demo";
import { prefetchStock, useSearchIndex } from "../lib/api";
import { BAND_LABEL, useUniverse, type Row } from "../lib/screener";
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
import { MINUS, cr, csvText, nf } from "../lib/format";

/** My portfolio as a scorecard: give it the names of the shares you hold (typed, pasted or a CSV file) and it shows each one's
 *  FinLit score and pillars, and the portfolio's average score, band mix and sector spread. No quantities or prices are asked for. */

const K = ["var(--k1)", "var(--k2)", "var(--k3)", "var(--k7)", "var(--k5)", "var(--k4)", "var(--k6)", "var(--k8)"];
const BAND_C: Record<string, string> = { strong: "var(--v-strong)", healthy: "var(--k1)", mixed: "var(--k4)", watch: "var(--v-weak)" };
const PILLARS: [keyof Row, string][] = [["pillar_quality", "Quality"], ["pillar_growth", "Growth"], ["pillar_profitability", "Profit."], ["pillar_balance", "Balance"], ["pillar_technical", "Technical"]];
const lvl = (v: number | null | undefined) => (v == null ? "na" : v >= 78 ? "hi" : v >= 45 ? "mid" : "lo");


type HLine = { symbol: string; name?: string | null; row?: Row | null };
type SortKey = "overall" | "symbol" | "price" | "change_pct" | "market_cap" | `p${number}`;
const heat = (v: number | null | undefined) => (v == null ? undefined : ({ "--hc": `hsl(${Math.round(Math.max(0, Math.min(100, v)) * 1.25)} 62% 46%)` } as React.CSSProperties));

/** The holdings as a heat table: sortable columns, band filter chips, a score bar per share, pillar tiles tinted from red to green by value,
 *  and a market-cap bar scaled to your biggest holding. */
function HoldingsTable({ lines, cap, onRemove }: { lines: HLine[]; cap: number; onRemove: (sym: string) => void }) {
  const [key, setKey] = useState<SortKey>("overall");
  const [dir, setDir] = useState<1 | -1>(-1);
  const [band, setBand] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const counts = useMemo(() => { const m = new Map<string, number>(); lines.forEach((l) => { const b = l.row?.band || "none"; m.set(b, (m.get(b) || 0) + 1); }); return m; }, [lines]);
  const maxCap = useMemo(() => Math.max(1, ...lines.map((l) => l.row?.market_cap ?? 0)), [lines]);
  const val = (l: HLine): number | string | null => key === "symbol" ? l.symbol : key.startsWith("p") && key !== "price" ? ((l.row?.[PILLARS[Number(key.slice(1))][0]] as number | null | undefined) ?? null) : ((l.row?.[key as keyof Row] as number | null | undefined) ?? null);
  const shown = useMemo(() => lines.filter((l) => (!band || (l.row?.band || "none") === band) && (!q.trim() || (l.symbol + " " + (l.name || "") + " " + (l.row?.sector || "")).toLowerCase().includes(q.trim().toLowerCase())))
    .sort((a, b) => { const x = val(a), y = val(b); if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1; return (typeof x === "string" ? x.localeCompare(y as string) : (x as number) - (y as number)) * dir; }),
  // eslint-disable-next-line react-hooks/exhaustive-deps
  [lines, band, q, key, dir]);
  const head = (k: SortKey, label: string) => <th scope="col" aria-sort={key === k ? (dir === 1 ? "ascending" : "descending") : "none"}>
    <button type="button" className={"hsort" + (key === k ? " on" : "")} onClick={() => { if (key === k) setDir((d) => (d === 1 ? -1 : 1)); else { setKey(k); setDir(k === "symbol" ? 1 : -1); } }}>{label}<i aria-hidden="true">{key === k ? (dir === 1 ? "▲" : "▼") : "↕"}</i></button></th>;
  return (
    <section className="card hold-card"><div className="card-h"><h3><span className="ci"><Icon name="table" /></span>Your shares</h3><span className="s">{shown.length === lines.length ? lines.length : `${shown.length} of ${lines.length}`} · limit {cap}</span></div>
      <div className="hold-bar">
        <div className="hold-chips" role="group" aria-label="Filter by FinLit band">
          <button type="button" className={"hchip" + (band == null ? " on" : "")} aria-pressed={band == null} onClick={() => setBand(null)}>All <b>{lines.length}</b></button>
          {(["strong", "healthy", "mixed", "watch", "none"] as const).filter((b) => counts.get(b)).map((b) =>
            <button key={b} type="button" className={"hchip" + (band === b ? " on" : "")} aria-pressed={band === b} style={{ "--bc": b === "none" ? "var(--faint)" : BAND_C[b] } as React.CSSProperties} onClick={() => setBand(band === b ? null : b)}>
              <i />{b === "none" ? "Not scored" : BAND_LABEL[b]} <b>{counts.get(b)}</b></button>)}
        </div>
        <input className="hold-q" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a share or sector" aria-label="Find a share or sector in your portfolio" />
      </div>
      <HScroll label="table"><table className="qtt hold hold-heat"><thead><tr>{head("symbol", "Share")}<th scope="col">Sector</th>{head("price", "Price")}{head("change_pct", "Today")}{head("market_cap", "Market cap")}{head("overall", "FinLit score")}{PILLARS.map(([, l], i) => head(`p${i}` as SortKey, l))}<th /></tr></thead>
        <tbody>{shown.map((l) => { const sig = l.row ? signals(l.row)[0] : null; const ch = l.row?.change_pct; const o = l.row?.overall; return (
          <tr key={l.symbol}><td><Link to={`/stocks/${l.symbol}`}><b>{l.symbol}</b></Link><small className="muted">{l.name}</small>{sig && <small className="down" title={sig}> ⚑ {sig}</small>}</td>
            <td>{l.row?.sector ? <span className="hsec">{l.row.sector}</span> : "—"}</td><td className="hprice">{l.row?.price != null ? "₹" + nf(l.row.price, 2) : "—"}</td>
            <td>{ch == null ? "—" : <span className={"hchg " + (ch > 0 ? "up" : ch < 0 ? "down" : "")}>{ch > 0 ? "▲" : ch < 0 ? "▼" : "•"} {nf(Math.abs(ch), 2)}%</span>}</td>
            <td className="hcap"><span className="hcb" style={{ "--w": ((l.row?.market_cap ?? 0) / maxCap).toFixed(3) } as React.CSSProperties}><i /></span>{cr(l.row?.market_cap)}</td>
            <td>{o != null ? <span className={"hscore " + l.row!.band} style={heat(o)}><span className="hsb"><i style={{ width: o + "%" }} /></span><b>{o}</b><em>{BAND_LABEL[l.row!.band!]}</em></span> : <span className="faint">Preparing…</span>}</td>
            {PILLARS.map(([k, label]) => { const v = l.row?.[k] as number | null | undefined; return <td key={label}><span className={"hp " + lvl(v)} style={heat(v)} title={v == null ? undefined : `${label}: ${v} out of 100`}>{v == null ? MINUS : v}</span></td>; })}
            <td className="ra"><AlertButton symbol={l.symbol} className="btn" /> <button className="btn" aria-label={`Remove ${l.symbol}`} onClick={() => onRemove(l.symbol)}>✕</button></td></tr>); })}
          {!shown.length && <tr><td colSpan={12} className="faint" style={{ textAlign: "center", padding: 24 }}>No share matches this filter.</td></tr>}</tbody></table></HScroll>
    </section>
  );
}

/* ---------------------------------------------------------------- page */

export function HoldingsPage() {
  useDocTitle("My portfolio", "Add the shares you hold, by name or from a CSV, and see each one's FinLit score, the portfolio's average score, band mix and sector spread.");
  const { plan, toast } = useUI();
  const qc = useQueryClient();
  const st = usePortfolio();
  const uni = useUniverse(), idx = useSearchIndex(true);
  const by = useMemo(() => new Map((uni.data?.rows || []).map((r) => [r.symbol, r])), [uni.data]);
  const index = idx.data?.rows || [];
  const cap = limitsFor(plan).holdings;
  const [text, setText] = useState(""), [one, setOne] = useState(""), [missing, setMissing] = useState<string[]>([]);
  const file = useRef<HTMLInputElement>(null), [busy, setBusy] = useState(false), [pdf, setPdf] = useState<File | null>(null);
  const matcher = useMemo(() => makeMatcher(index), [index]);

  const symbols = useMemo(() => [...new Set(st.holdings.map((h) => h.symbol))], [st.holdings]);
  const lines = useMemo(() => symbols.map((s) => ({ symbol: s, row: by.get(s), id: st.holdings.find((h) => h.symbol === s)!.id, name: by.get(s)?.name || index.find((r) => r[0] === s)?.[1] || "" })), [symbols, by, st.holdings, index]);
  // Shares not loaded yet are prepared in the background (once), and their score appears when ready.
  const waiting = lines.filter((l) => l.row?.overall == null).map((l) => l.symbol);
  useEffect(() => {
    if (DEMO || !waiting.length) return;
    // Each unprepared company is a build on the server: ask for them one by one (the server limits how many one visitor may start at once)
    const starts = waiting.slice(0, 12).map((s, i) => window.setTimeout(() => prefetchStock(qc, s), i * 1500));
    const t = setInterval(() => qc.invalidateQueries({ queryKey: ["universe"] }), 20_000);
    return () => { starts.forEach((x) => window.clearTimeout(x)); clearInterval(t); };
  }, [waiting.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  const m = useMemo(() => {
    const scored = lines.filter((l) => l.row?.overall != null), n = lines.length || 1;
    const avg = scored.length ? scored.reduce((a, l) => a + (l.row!.overall as number), 0) / scored.length : null;
    const pill = PILLARS.map(([k, label]) => { const v = scored.map((l) => l.row![k] as number | null).filter((x): x is number => x != null); return { label, v: v.length ? v.reduce((a, b) => a + b, 0) / v.length : null }; });
    const sector = new Map<string, number>(); lines.forEach((l) => sector.set(l.row?.sector || "Not yet loaded", (sector.get(l.row?.sector || "Not yet loaded") || 0) + 100 / n));
    const band = new Map<string, number>(); lines.forEach((l) => band.set(l.row?.band || "none", (band.get(l.row?.band || "none") || 0) + 100 / n));
    const cap = new Map<string, string[]>(); lines.forEach((l) => { const id = capBucket(l.row?.market_cap)?.id ?? "unknown"; cap.set(id, [...(cap.get(id) || []), l.symbol]); });
    return { avg, pill, scored: scored.length, sector: [...sector.entries()].sort((a, b) => b[1] - a[1]), band, cap };
  }, [lines]);

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
  const exportCsv = () => saveFile("FinLit-portfolio.csv", ["Symbol,Company,Sector,Price,FinLit score,Band,Quality,Growth,Profitability,Balance sheet,Technical",
    ...lines.map((l) => [l.symbol, `"${csvText(l.name || "").replace(/"/g, '""')}"`, `"${csvText(l.row?.sector || "").replace(/"/g, '""')}"`, l.row?.price ?? "", l.row?.overall ?? "", l.row?.band ? BAND_LABEL[l.row.band] : "", ...PILLARS.map(([k]) => l.row?.[k] ?? "")].join(","))].join("\n"), "text/csv;charset=utf-8");
  const CAP_COLORS = ["var(--k1)", "var(--k7)", "var(--k3)", "var(--k4)", "var(--k2)", "var(--k8)"];
  const capParts = CAP_BUCKETS.map((b, i) => ({ label: b.label, value: m.cap.get(b.id)?.length || 0, color: CAP_COLORS[i] })).filter((p) => p.value > 0);
  const capUnknown = m.cap.get("unknown")?.length || 0;
  const donut = m.sector.slice(0, 7).map(([label, value], i) => ({ label, value, color: K[i % K.length] }));
  const empty = !lines.length;

  return (
    <div className="wrap ipo">
      <header className="dash-h"><div><div className="eyebrow">My lists</div><h1>My portfolio</h1><p className="muted">Add the shares you hold and see how strong they are: each company's FinLit score and pillars, and the portfolio as a whole. Only names are needed; nothing is sent to a broker.</p></div>
        <div className="row"><button className="btn" onClick={exportCsv} disabled={empty}>Export CSV</button></div></header>
      <Gate tier="silver" title="Score your portfolio" points={["FinLit score and pillars for every share you hold", "Average score, band mix and sector spread", "Import Excel, CSV or PDF statements"]}>
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

        {empty ? <div className="card dw-empty"><span className="dw-ei"><Icon name="wallet" /></span><b>No shares yet</b><p>Add the shares you hold above. {DEMO ? "" : <>You can also <Link to="/watchlist">start from your watchlist</Link>.</>}</p></div> : <>
          <div className="pf-k">
            <div className="card ipo-t" style={{ "--tc": "var(--k7)" } as React.CSSProperties}><span>Portfolio FinLit score</span><b className={"ssp-t " + lvl(m.avg)}>{m.avg == null ? "—" : nf(m.avg, 0)}</b><small>average of {m.scored} scored {m.scored === 1 ? "share" : "shares"}</small></div>
            <div className="card ipo-t" style={{ "--tc": "var(--k1)" } as React.CSSProperties}><span>Shares</span><b>{lines.length}</b><small>{waiting.length ? `${waiting.length} being prepared` : `of ${cap} on your plan`}</small></div>
            <div className="card ipo-t" style={{ "--tc": "var(--v-strong)" } as React.CSSProperties}><span>Strong or Healthy</span><b>{nf((m.band.get("strong") || 0) + (m.band.get("healthy") || 0), 0)}%</b><small>of your shares</small></div>
            <div className="card ipo-t" style={{ "--tc": "var(--v-weak)" } as React.CSSProperties}><span>On Watch</span><b>{nf(m.band.get("watch") || 0, 0)}%</b><small>worth a closer look</small></div>
          </div>
          <div className="pf-g">
            <section className="card"><div className="card-h"><h3><span className="ci"><Icon name="quality" /></span>Average by pillar</h3><span className="s">0 to 100</span></div>
              <RankBars rows={m.pill.filter((p) => p.v != null).map((p) => ({ label: p.label, value: p.v as number }))} fmt={(x) => nf(x, 0)} /></section>
            <section className="card"><div className="card-h"><h3><span className="ci"><Icon name="quality" /></span>By FinLit band</h3><span className="s">Share of your shares</span></div>
              <div className="breadth big" role="img" aria-label="Portfolio by FinLit band">{(["strong", "healthy", "mixed", "watch", "none"] as const).filter((b) => m.band.get(b)).map((b) => <i key={b} style={{ flex: m.band.get(b), background: b === "none" ? "var(--s3)" : BAND_C[b] }} />)}</div>
              <ul className="bandk">{(["strong", "healthy", "mixed", "watch", "none"] as const).map((b) => <li key={b}><i style={{ background: b === "none" ? "var(--s3)" : BAND_C[b] }} /><span>{b === "none" ? "Not scored yet" : BAND_LABEL[b]}</span><b>{nf(m.band.get(b) || 0, 0)}%</b></li>)}</ul></section>
            <section className="card"><div className="card-h"><h3><span className="ci"><Icon name="pie" /></span>By sector</h3><span className="s">Share of your shares</span></div><Donut parts={donut} center={String(m.sector.length)} sub={m.sector.length === 1 ? "SECTOR" : "SECTORS"} /></section>
            <section className="card pf-cap"><div className="card-h"><h3><span className="ci"><Icon name="pie" /></span>By market cap</h3><span className="s">Size of the companies you hold</span></div>
              {capParts.length ? <Donut parts={capParts} center={String(lines.length - capUnknown)} sub={lines.length - capUnknown === 1 ? "COMPANY" : "COMPANIES"} /> : <p className="muted">Market values are still loading for these companies.</p>}
              <table className="pf-cap-t"><caption className="sr-only">Your shares by company size</caption><thead><tr><th scope="col">Size</th><th scope="col">Market cap (₹ crore)</th><th scope="col">Shares</th></tr></thead>
                <tbody>{CAP_BUCKETS.map((b, i) => { const syms = m.cap.get(b.id) || []; return (
                  <tr key={b.id} className={syms.length ? "" : "none"}><th scope="row"><i style={{ background: CAP_COLORS[i] }} aria-hidden="true" />{b.label}</th><td>{b.range}</td>
                    <td title={syms.join(", ")}><b>{syms.length}</b>{syms.length > 0 && <small>{syms.slice(0, 3).join(", ")}{syms.length > 3 ? ` +${syms.length - 3}` : ""}</small>}</td></tr>); })}
                  {capUnknown > 0 && <tr className="unk"><th scope="row"><i aria-hidden="true" />Not known yet</th><td>value still loading</td><td title={(m.cap.get("unknown") || []).join(", ")}><b>{capUnknown}</b></td></tr>}</tbody></table>
              <p className="faint pf-cap-n">Each share counts once: quantities and prices in your file are not used, so this shows how many of your companies sit in each size band, not how much money does. Bands are FinLit's own money bands, not an official list.</p></section>
          </div>
          <HoldingsTable lines={lines} cap={cap} onRemove={(sym) => { st.holdings.filter((h) => h.symbol === sym).forEach((h) => portfolio.remove(h.id)); toast(`${sym} removed.`); }} />
          <p className="faint" style={{ fontSize: 12.5, margin: "-6px 4px 0" }}>Scores come from each company's latest statements and prices. A share shows "Preparing…" for a moment the first time it is added. Information only, not investment advice.</p>
          <PortfolioInsights lines={lines} />
          <PortfolioLab lines={lines} universe={uni.data?.rows || []} /></>}
      </Gate>
    </div>
  );
}
