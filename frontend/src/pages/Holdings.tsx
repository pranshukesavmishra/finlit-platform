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
import { prefetchStock, useSearchIndex, type SearchRow } from "../lib/api";
import { BAND_LABEL, useUniverse, type Row } from "../lib/screener";
import { portfolio, usePortfolio } from "../lib/portfolio";
import { signals } from "./Watchlist";
import { saveFile } from "../stock/derive";
import { MINUS, cr, nf } from "../lib/format";

/** My portfolio as a scorecard: give it the names of the shares you hold (typed, pasted or a CSV file) and it shows each one's
 *  FinLit score and pillars, and the portfolio's average score, band mix and sector spread. No quantities or prices are asked for. */

const K = ["var(--k1)", "var(--k2)", "var(--k3)", "var(--k7)", "var(--k5)", "var(--k4)", "var(--k6)", "var(--k8)"];
const BAND_C: Record<string, string> = { strong: "var(--v-strong)", healthy: "var(--k1)", mixed: "var(--k4)", watch: "var(--v-weak)" };
const PILLARS: [keyof Row, string][] = [["pillar_quality", "Quality"], ["pillar_growth", "Growth"], ["pillar_profitability", "Profit."], ["pillar_balance", "Balance"], ["pillar_technical", "Technical"]];
const lvl = (v: number | null | undefined) => (v == null ? "na" : v >= 78 ? "hi" : v >= 45 ? "mid" : "lo");
const pct = (v: number | null | undefined, d = 2) => (v == null ? "—" : (v > 0 ? "+" : v < 0 ? MINUS : "") + nf(Math.abs(v), d) + "%");

/* ---------------------------------------------------------------- reading a list of share names */

const norm = (s: string) => s.toUpperCase().replace(/&/g, " AND ").replace(/\b(LIMITED|LTD|THE|CO|COMPANY|CORPORATION|CORP|INC)\b\.?/g, " ").replace(/[^A-Z0-9]+/g, " ").trim();
const HEADER = /^(symbol|ticker|scrip|stock|share|name|company|instrument|security|nse|bse)/i;

/** The names or tickers in pasted text or a CSV: the column headed symbol/stock/name/company if there is one, else the first column. */
export function namesFrom(text: string): string[] {
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
  if (!lines.length) return [];
  const split = (l: string) => l.split(/[,\t;|]/).map((x) => x.trim().replace(/^"|"$/g, "").trim());
  const head = split(lines[0]);
  const col = Math.max(0, head.findIndex((h) => HEADER.test(h)));
  const body = head.some((h) => HEADER.test(h)) ? lines.slice(1) : lines;
  return [...new Set(body.map((l) => split(l)[col] || "").filter((x) => x && !/^[\d.,\s₹-]+$/.test(x) || /^\d{6}$/.test(x)))];
}

/** Match each name to a listed company: exact ticker, NSE or BSE code first, then the company name (ignoring Ltd/Limited/&), then a
 *  name that starts the same way. The search list is biggest company first, so an ambiguous name picks the larger company. */
export function matchNames(names: string[], index: SearchRow[]): { found: { input: string; symbol: string; name: string }[]; missing: string[] } {
  const byCode = new Map<string, SearchRow>(), byName = new Map<string, SearchRow>();
  for (const r of index) {
    for (const c of [r[0], r[2], r[4]]) if (c && !byCode.has(c.toUpperCase())) byCode.set(c.toUpperCase(), r);
    const n = norm(r[1]); if (n && !byName.has(n)) byName.set(n, r);
  }
  const found: { input: string; symbol: string; name: string }[] = [], missing: string[] = [];
  for (const input of names) {
    const up = input.toUpperCase().replace(/\.(NS|BO)$/, "").replace(/^(NSE|BSE):/, "").trim(), n = norm(input);
    const hit = byCode.get(up) || byName.get(n) || (n.length >= 4 ? index.find((r) => norm(r[1]).startsWith(n + " ") || norm(r[1]) === n) : undefined);
    if (hit) found.push({ input, symbol: hit[0], name: hit[1] }); else missing.push(input);
  }
  return { found, missing };
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
  const file = useRef<HTMLInputElement>(null);

  const symbols = useMemo(() => [...new Set(st.holdings.map((h) => h.symbol))], [st.holdings]);
  const lines = useMemo(() => symbols.map((s) => ({ symbol: s, row: by.get(s), id: st.holdings.find((h) => h.symbol === s)!.id, name: by.get(s)?.name || index.find((r) => r[0] === s)?.[1] || "" })), [symbols, by, st.holdings, index]);
  // Shares not loaded yet are prepared in the background (once), and their score appears when ready.
  const waiting = lines.filter((l) => l.row?.overall == null).map((l) => l.symbol);
  useEffect(() => {
    if (DEMO || !waiting.length) return;
    waiting.slice(0, 25).forEach((s) => prefetchStock(qc, s));
    const t = setInterval(() => qc.invalidateQueries({ queryKey: ["universe"] }), 20_000);
    return () => clearInterval(t);
  }, [waiting.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  const m = useMemo(() => {
    const scored = lines.filter((l) => l.row?.overall != null), n = lines.length || 1;
    const avg = scored.length ? scored.reduce((a, l) => a + (l.row!.overall as number), 0) / scored.length : null;
    const pill = PILLARS.map(([k, label]) => { const v = scored.map((l) => l.row![k] as number | null).filter((x): x is number => x != null); return { label, v: v.length ? v.reduce((a, b) => a + b, 0) / v.length : null }; });
    const sector = new Map<string, number>(); lines.forEach((l) => sector.set(l.row?.sector || "Not yet loaded", (sector.get(l.row?.sector || "Not yet loaded") || 0) + 100 / n));
    const band = new Map<string, number>(); lines.forEach((l) => band.set(l.row?.band || "none", (band.get(l.row?.band || "none") || 0) + 100 / n));
    return { avg, pill, scored: scored.length, sector: [...sector.entries()].sort((a, b) => b[1] - a[1]), band };
  }, [lines]);

  const add = (names: string[]) => {
    if (!names.length) { toast("No share names found. Put one name or ticker per line, or a CSV with a Symbol or Name column."); return; }
    if (!index.length) { toast("The company list is still loading. Try again in a moment."); return; }
    const { found, missing: miss } = matchNames(names, index);
    const fresh = [...new Map(found.filter((f) => !symbols.includes(f.symbol)).map((f) => [f.symbol, f])).values()];
    const room = Math.max(0, cap - symbols.length), take = fresh.slice(0, room);
    if (take.length) portfolio.addMany(take.map((f) => ({ symbol: f.symbol, qty: 1, price: 0 })));
    setMissing(miss);
    toast([take.length ? `Added ${take.length} ${take.length === 1 ? "share" : "shares"}` : "Nothing new to add", miss.length ? `${miss.length} not recognised (listed below)` : "", fresh.length > room ? `your plan holds up to ${cap}` : ""].filter(Boolean).join(" · ") + ".");
  };
  const exportCsv = () => saveFile("FinLit-portfolio.csv", ["Symbol,Company,Sector,Price,FinLit score,Band,Quality,Growth,Profitability,Balance sheet,Technical",
    ...lines.map((l) => [l.symbol, `"${(l.name || "").replace(/"/g, '""')}"`, `"${l.row?.sector || ""}"`, l.row?.price ?? "", l.row?.overall ?? "", l.row?.band ? BAND_LABEL[l.row.band] : "", ...PILLARS.map(([k]) => l.row?.[k] ?? "")].join(","))].join("\n"), "text/csv;charset=utf-8");
  const donut = m.sector.slice(0, 7).map(([label, value], i) => ({ label, value, color: K[i % K.length] }));
  const empty = !lines.length;

  return (
    <div className="wrap ipo">
      <header className="dash-h"><div><div className="eyebrow">My lists</div><h1>My portfolio</h1><p className="muted">Add the shares you hold and see how strong they are: each company's FinLit score and pillars, and the portfolio as a whole. Only names are needed; nothing is sent to a broker.</p></div>
        <div className="row"><button className="btn" onClick={exportCsv} disabled={empty}>Export CSV</button></div></header>
      <Gate tier="silver" title="Score your portfolio" points={["FinLit score and pillars for every share you hold", "Average score, band mix and sector spread", "Import a CSV of share names"]}>
        <section className="card acct-c pf-in">
          <h2>Add your shares</h2>
          <p className="muted">Type a name or ticker, paste a list (one per line), or choose a CSV file. Company names work too, such as <code>Reliance Industries</code>, <code>HDFC Bank Ltd</code> or <code>500325</code>; any column headed Symbol, Stock or Name is read.</p>
          <div className="pf-add">
            <form className="pf-one" onSubmit={(e) => { e.preventDefault(); add([one.trim()].filter(Boolean)); setOne(""); }}>
              <input list="pf-names" value={one} onChange={(e) => setOne(e.target.value)} placeholder="e.g. RELIANCE or Infosys" aria-label="Share name or ticker" autoComplete="off" maxLength={80} />
              <datalist id="pf-names">{index.slice(0, 500).map((r) => <option key={r[0]} value={r[0]}>{r[1]}</option>)}</datalist>
              <button className="btn primary">Add</button>
            </form>
            <div className="pf-bulk">
              <textarea className="imp" rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder={"RELIANCE\nHDFC Bank\nInfosys Ltd\nTCS"} aria-label="Share names to add, one per line" />
              <div className="row"><button className="btn primary" onClick={() => { add(namesFrom(text)); setText(""); }} disabled={!text.trim()}>Add these</button>
                <button className="btn" onClick={() => file.current?.click()}><Icon name="table" />Choose CSV file…</button>
                <input ref={file} type="file" accept=".csv,.txt,text/csv,text/plain" hidden onChange={async (e) => { const f = e.target.files?.[0]; if (f && f.size < 500_000) add(namesFrom(await f.text())); e.target.value = ""; }} /></div>
            </div>
          </div>
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
          </div>
          <section className="card"><div className="card-h"><h3><span className="ci"><Icon name="table" /></span>Your shares</h3><span className="s">{lines.length} of {cap}</span></div>
            <HScroll label="table"><table className="qtt hold"><thead><tr><th>Share</th><th>Sector</th><th>Price</th><th>Today</th><th>Market cap</th><th>FinLit score</th>{PILLARS.map(([, l]) => <th key={l}>{l}</th>)}<th /></tr></thead>
              <tbody>{[...lines].sort((a, b) => (b.row?.overall ?? -1) - (a.row?.overall ?? -1)).map((l) => { const sig = l.row ? signals(l.row)[0] : null; return (
                <tr key={l.symbol}><td><Link to={`/stocks/${l.symbol}`}><b>{l.symbol}</b></Link><small className="muted">{l.name}</small>{sig && <small className="down" title={sig}> ⚑ {sig}</small>}</td>
                  <td>{l.row?.sector || "—"}</td><td>{l.row?.price != null ? "₹" + nf(l.row.price, 2) : "—"}</td>
                  <td className={(l.row?.change_pct ?? 0) > 0 ? "up" : (l.row?.change_pct ?? 0) < 0 ? "down" : ""}>{pct(l.row?.change_pct)}</td><td>{cr(l.row?.market_cap)}</td>
                  <td>{l.row?.overall != null ? <span className={"band-dot " + l.row.band}>{l.row.overall} · {BAND_LABEL[l.row.band!]}</span> : <span className="faint">Preparing…</span>}</td>
                  {PILLARS.map(([k, label]) => { const v = l.row?.[k] as number | null | undefined; return <td key={label}><span className={"ssp " + lvl(v)}>{v == null ? MINUS : v}</span></td>; })}
                  <td className="ra"><AlertButton symbol={l.symbol} className="btn" /> <button className="btn" aria-label={`Remove ${l.symbol}`} onClick={() => { st.holdings.filter((h) => h.symbol === l.symbol).forEach((h) => portfolio.remove(h.id)); toast(`${l.symbol} removed.`); }}>✕</button></td></tr>); })}</tbody></table></HScroll>
            <p className="faint" style={{ fontSize: 12.5, marginTop: 10 }}>Scores come from each company's latest statements and prices. A share shows "Preparing…" for a moment the first time it is added. Information only, not investment advice.</p>
          </section></>}
      </Gate>
    </div>
  );
}
