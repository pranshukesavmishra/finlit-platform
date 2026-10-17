import { useEffect, useMemo, useRef, useState } from "react";
import { AlertButton } from "../components/AlertComposer";
import { Link } from "react-router";
import { Icon } from "../lib/icons";
import { Gate } from "../components/Gate";
import { Donut, RankBars } from "../charts/Atlas";
import { useDocTitle } from "../lib/title";
import { useUI } from "../lib/ui";
import { limitsFor } from "../lib/auth";
import { DEMO } from "../lib/demo";
import { BAND_LABEL, useUniverse, type Row } from "../lib/screener";
import { parseHoldings, portfolio, usePortfolio, type Holding } from "../lib/portfolio";
import { signals } from "./Watchlist";
import { saveFile } from "../stock/derive";
import { MINUS, nf } from "../lib/format";

const inr = (v: number, d = 0) => (v < 0 ? MINUS : "") + "₹" + nf(Math.abs(v), d);
const sgn = (v: number | null, d = 1) => (v == null ? "—" : (v > 0 ? "+" : v < 0 ? MINUS : "") + nf(Math.abs(v), d) + "%");
const tone = (v: number | null) => (v == null || v === 0 ? "" : v > 0 ? "up" : "down");
const K = ["var(--k1)", "var(--k2)", "var(--k3)", "var(--k7)", "var(--k5)", "var(--k4)", "var(--k6)", "var(--k8)"];
const BAND_C: Record<string, string> = { strong: "var(--v-strong)", healthy: "var(--k1)", mixed: "var(--k4)", watch: "var(--v-weak)" };

type Line = Holding & { row?: Row; value: number | null; cost: number; pnl: number | null; pnlPct: number | null; day: number | null; weight: number; cagr: number | null };

export function HoldingsPage() {
  useDocTitle("My portfolio", "Track what you own: current value, profit and loss, allocation by stock, sector and FinLit band, and a portfolio health read.");
  const { plan, toast } = useUI();
  const st = usePortfolio();
  const { data } = useUniverse();
  const rows = data?.rows || [];
  const by = useMemo(() => new Map(rows.map((r) => [r.symbol, r])), [rows]);
  const cap = limitsFor(plan).holdings;
  // Demo preview only: a few pretend holdings so the page can be shown without typing anything in.
  useEffect(() => { if (DEMO && !st.holdings.length && rows.length) { const pick = (s: string) => rows.find((r) => r.symbol === s); const seed = [["RELIANCE", 40, 1180, "2025-02-10"], ["SMP-BAN1", 60, 640, "2024-09-03"], ["SMP-SYS1", 25, 2100, "2025-06-18"], ["SMP-PHA1", 80, 410, "2024-11-21"], ["SMP-CON1", 30, 1300, "2025-01-09"], ["SMP-MOT1", 50, 880, "2025-08-04"]] as const; portfolio.addMany(seed.filter(([s]) => pick(s)).map(([symbol, qty, price, date]) => ({ symbol, qty, price, date }))); } }, [rows.length]); // eslint-disable-line react-hooks/exhaustive-deps
  const [form, setForm] = useState({ symbol: "", qty: "", price: "", date: "" });
  const [edit, setEdit] = useState<string | null>(null);
  const [paste, setPaste] = useState(false), [text, setText] = useState("");
  const file = useRef<HTMLInputElement>(null);

  const m = useMemo(() => {
    const base = st.holdings.map((h) => { const row = by.get(h.symbol), cost = h.qty * h.price, value = row?.price != null ? h.qty * row.price : null;
      const days = h.date ? (Date.now() - new Date(h.date + "T00:00:00").getTime()) / 86_400_000 : 0;
      return { ...h, row, cost, value, pnl: value != null ? value - cost : null, pnlPct: value != null && cost > 0 ? ((value - cost) / cost) * 100 : null,
        day: value != null && row?.change_pct != null ? value - value / (1 + row.change_pct / 100) : null, weight: 0,
        cagr: value != null && cost > 0 && days >= 60 ? (Math.pow(value / cost, 365 / days) - 1) * 100 : null } as Line; });
    const total = base.reduce((a, l) => a + (l.value ?? l.cost), 0) || 1;
    const lines = base.map((l) => ({ ...l, weight: ((l.value ?? l.cost) / total) * 100 })).sort((a, b) => b.weight - a.weight);
    const priced = lines.filter((l) => l.value != null);
    const invested = lines.reduce((a, l) => a + l.cost, 0), value = lines.reduce((a, l) => a + (l.value ?? l.cost), 0);
    const day = priced.reduce((a, l) => a + (l.day ?? 0), 0), costP = priced.reduce((a, l) => a + l.cost, 0), valP = priced.reduce((a, l) => a + (l.value as number), 0);
    const scored = lines.filter((l) => l.row?.overall != null), sw = scored.reduce((a, l) => a + l.weight, 0);
    const score = sw ? scored.reduce((a, l) => a + (l.row!.overall as number) * l.weight, 0) / sw : null;
    const sector = new Map<string, number>(); lines.forEach((l) => sector.set(l.row?.sector || "Other", (sector.get(l.row?.sector || "Other") || 0) + l.weight));
    const band = new Map<string, number>(); lines.forEach((l) => band.set(l.row?.band || "none", (band.get(l.row?.band || "none") || 0) + l.weight));
    return { lines, invested, value, pnl: valP - costP, pnlPct: costP ? ((valP - costP) / costP) * 100 : null, day, dayPct: valP - day ? (day / (valP - day)) * 100 : null, score, sector: [...sector.entries()].sort((a, b) => b[1] - a[1]), band, unpriced: lines.length - priced.length };
  }, [st.holdings, by]);

  const notes = useMemo(() => {
    const out: { tone: "warn" | "good"; text: string }[] = [];
    const top = m.lines[0]; if (top && top.weight > 25 && m.lines.length > 1) out.push({ tone: "warn", text: `${top.symbol} is ${nf(top.weight, 0)}% of your portfolio. A single stock above a quarter of the total makes the whole portfolio depend on it.` });
    const sec = m.sector[0]; if (sec && sec[1] > 40 && sec[0] !== "Other") out.push({ tone: "warn", text: `${nf(sec[1], 0)}% of your money is in ${sec[0]}. Spreading across more sectors lowers the risk of one bad year.` });
    const watch = m.band.get("watch") || 0; if (watch > 20) out.push({ tone: "warn", text: `${nf(watch, 0)}% is in stocks with a FinLit Watch band. Review them in the table below.` });
    if (m.lines.length >= 8 && m.sector.length >= 4 && !out.length) out.push({ tone: "good", text: `Well spread: ${m.lines.length} stocks across ${m.sector.length} sectors, and no single stock above a quarter of the total.` });
    if (m.score != null) out.push({ tone: m.score >= 62 ? "good" : "warn", text: `Value-weighted FinLit score is ${nf(m.score, 0)} (${m.score >= 78 ? "Strong" : m.score >= 62 ? "Healthy" : m.score >= 45 ? "Mixed" : "Watch"}).` });
    return out;
  }, [m]);

  const add = (e: React.FormEvent) => {
    e.preventDefault();
    const symbol = form.symbol.trim().toUpperCase(), qty = Number(form.qty), price = Number(form.price);
    if (!symbol || !(qty > 0) || !(price >= 0) || form.price === "") return toast("Enter the symbol, quantity and your average buy price.");
    if (!by.has(symbol) && !DEMO) return toast(`${symbol} is not in the stock list. Check the symbol.`);
    if (!edit && st.holdings.length >= cap) return toast(`Your plan holds up to ${cap} holdings.`);
    const h = { symbol, qty, price, ...(form.date ? { date: form.date } : {}) };
    if (edit) { portfolio.update(edit, h); setEdit(null); toast("Holding updated."); } else { portfolio.add(h); toast(`${symbol} added.`); }
    setForm({ symbol: "", qty: "", price: "", date: "" });
  };
  const importText = (t: string) => {
    const { rows: parsed, skipped } = parseHoldings(t);
    const room = Math.max(0, cap - st.holdings.length), take = parsed.slice(0, room);
    if (take.length) portfolio.addMany(take);
    toast(take.length ? `Imported ${take.length} holding${take.length === 1 ? "" : "s"}${skipped ? `, skipped ${skipped} unreadable line${skipped === 1 ? "" : "s"}` : ""}${parsed.length > room ? `. Your plan holds up to ${cap}.` : "."}` : "No readable lines. Use: symbol, quantity, average price.");
    setPaste(false); setText("");
  };
  const exportCsv = () => saveFile("FinLit-portfolio.csv", ["Symbol,Quantity,Average price,Date,Current price,Value,P&L,P&L %", ...m.lines.map((l) => [l.symbol, l.qty, l.price, l.date || "", l.row?.price ?? "", l.value?.toFixed(2) ?? "", l.pnl?.toFixed(2) ?? "", l.pnlPct?.toFixed(2) ?? ""].join(","))].join("\n"), "text/csv;charset=utf-8");

  const donut = (() => { const top = m.lines.slice(0, 7), rest = m.lines.slice(7).reduce((a, l) => a + l.weight, 0); return [...top.map((l, i) => ({ label: l.symbol, value: l.weight, color: K[i % K.length] })), ...(rest > 0 ? [{ label: "Others", value: rest, color: "var(--s3)" }] : [])]; })();
  const empty = !st.holdings.length;

  return (
    <div className="wrap ipo">
      <header className="dash-h"><div><div className="eyebrow">My lists</div><h1>My portfolio</h1><p className="muted">What you own, what it is worth, and how it is spread. Prices come from the latest FinLit data; nothing here is sent to a broker.</p></div>
        <div className="row"><button className="btn" onClick={() => setPaste(!paste)}><Icon name="table" />Import</button><button className="btn" onClick={exportCsv} disabled={empty}>Export CSV</button></div></header>
      <Gate tier="silver" title="Track your portfolio" points={["Value, profit and loss at a glance", "Allocation by stock, sector and FinLit band", "Concentration and health read"]}>
        {paste && <section className="card acct-c"><h2>Import holdings</h2><p className="muted">One per line: <code>symbol, quantity, average buy price, date (optional)</code>. Paste from a spreadsheet, or choose a CSV file.</p>
          <textarea className="imp" rows={5} value={text} onChange={(e) => setText(e.target.value)} placeholder={"RELIANCE, 10, 1250.50, 2025-03-14\nTCS, 5, 3900"} aria-label="Holdings to import" />
          <div className="row" style={{ marginTop: 10 }}><button className="btn primary" onClick={() => importText(text)} disabled={!text.trim()}>Import</button><button className="btn" onClick={() => file.current?.click()}>Choose CSV file…</button>
            <input ref={file} type="file" accept=".csv,.txt,text/csv,text/plain" hidden onChange={async (e) => { const f = e.target.files?.[0]; if (f && f.size < 200_000) importText(await f.text()); e.target.value = ""; }} /></div></section>}
        <form className="card hform" onSubmit={add}>
          <label>Symbol<input list="hold-syms" value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value })} placeholder="RELIANCE" autoComplete="off" maxLength={24} /><datalist id="hold-syms">{rows.slice(0, 600).map((r) => <option key={r.symbol} value={r.symbol}>{r.name}</option>)}</datalist></label>
          <label>Quantity<input type="number" min="0" step="any" inputMode="decimal" value={form.qty} onChange={(e) => setForm({ ...form, qty: e.target.value })} /></label>
          <label>Average buy price (₹)<input type="number" min="0" step="any" inputMode="decimal" value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} /></label>
          <label>Bought on <span className="faint">(optional)</span><input type="date" max={new Date().toISOString().slice(0, 10)} value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} /></label>
          <div className="hform-b"><button className="btn primary">{edit ? "Save changes" : "Add holding"}</button>{edit && <button type="button" className="btn" onClick={() => { setEdit(null); setForm({ symbol: "", qty: "", price: "", date: "" }); }}>Cancel</button>}</div>
        </form>
        {empty ? <div className="card dw-empty"><span className="dw-ei"><Icon name="wallet" /></span><b>No holdings yet</b><p>Add your first stock above, or import a list. {DEMO ? "" : <>You can also <Link to="/watchlist">start from your watchlist</Link>.</>}</p></div> : <>
          <div className="pf-k">
            <div className="card ipo-t" style={{ "--tc": "var(--k1)" } as React.CSSProperties}><span>Current value</span><b>{inr(m.value)}</b><small>Invested {inr(m.invested)}</small></div>
            <div className="card ipo-t" style={{ "--tc": m.pnl >= 0 ? "var(--gain)" : "var(--loss)" } as React.CSSProperties}><span>Total profit / loss</span><b className={tone(m.pnl)}>{(m.pnl >= 0 ? "+" : "") + inr(m.pnl)}</b><small className={tone(m.pnlPct)}>{sgn(m.pnlPct)}</small></div>
            <div className="card ipo-t" style={{ "--tc": m.day >= 0 ? "var(--gain)" : "var(--loss)" } as React.CSSProperties}><span>Today</span><b className={tone(m.day)}>{(m.day >= 0 ? "+" : "") + inr(m.day)}</b><small className={tone(m.dayPct)}>{sgn(m.dayPct, 2)}</small></div>
            <div className="card ipo-t" style={{ "--tc": "var(--k7)" } as React.CSSProperties}><span>Portfolio FinLit score</span><b>{m.score == null ? "—" : nf(m.score, 0)}</b><small>value-weighted across holdings</small></div>
          </div>
          {m.unpriced > 0 && <p className="muted" style={{ margin: "0 0 12px" }}>{m.unpriced} holding{m.unpriced === 1 ? " has" : "s have"} no price yet, so {m.unpriced === 1 ? "it is" : "they are"} valued at cost.</p>}
          {notes.length > 0 && <div className="card hnotes"><h3><Icon name="quality" />Portfolio health</h3><ul>{notes.map((n, i) => <li key={i} className={n.tone}>{n.text}</li>)}</ul></div>}
          <div className="pf-g">
            <section className="card"><div className="card-h"><h3><span className="ci"><Icon name="pie" /></span>By stock</h3><span className="s">Share of value</span></div><Donut parts={donut} center={String(m.lines.length)} sub={m.lines.length === 1 ? "HOLDING" : "HOLDINGS"} /></section>
            <section className="card"><div className="card-h"><h3><span className="ci"><Icon name="layers" /></span>By sector</h3><span className="s">Share of value</span></div><RankBars rows={m.sector.slice(0, 8).map(([label, value]) => ({ label, value }))} fmt={(x) => nf(x, 1) + "%"} /></section>
            <section className="card"><div className="card-h"><h3><span className="ci"><Icon name="quality" /></span>By FinLit band</h3><span className="s">Share of value</span></div>
              <div className="breadth big" role="img" aria-label="Portfolio by FinLit band">{(["strong", "healthy", "mixed", "watch", "none"] as const).filter((b) => m.band.get(b)).map((b) => <i key={b} style={{ flex: m.band.get(b), background: b === "none" ? "var(--s3)" : BAND_C[b] }} />)}</div>
              <ul className="bandk">{(["strong", "healthy", "mixed", "watch", "none"] as const).map((b) => <li key={b}><i style={{ background: b === "none" ? "var(--s3)" : BAND_C[b] }} /><span>{b === "none" ? "Not scored" : BAND_LABEL[b]}</span><b>{nf(m.band.get(b) || 0, 0)}%</b></li>)}</ul></section>
            <section className="card"><div className="card-h"><h3><span className="ci"><Icon name="growth" /></span>Profit and loss by stock</h3><span className="s">₹</span></div>
              <RankBars diverging rows={m.lines.filter((l) => l.pnl != null).sort((a, b) => (b.pnl as number) - (a.pnl as number)).slice(0, 10).map((l) => ({ label: l.symbol, value: l.pnl as number }))} fmt={(x) => (x > 0 ? "+" : "") + inr(x)} /></section>
          </div>
          <section className="card"><div className="card-h"><h3><span className="ci"><Icon name="table" /></span>Holdings</h3><span className="s">{m.lines.length} of {cap}</span></div>
            <div className="tw"><table className="qtt hold"><thead><tr><th>Stock</th><th>Qty</th><th>Avg price</th><th>Price</th><th>Value</th><th>Weight</th><th>P&amp;L</th><th>Today</th><th>FinLit</th><th /></tr></thead>
              <tbody>{m.lines.map((l) => { const sig = l.row ? signals(l.row)[0] : null; return (
                <tr key={l.id}><td><Link to={`/stocks/${l.symbol}`}><b>{l.symbol}</b></Link><small className="muted">{l.row?.name || ""}</small>{sig && <small className="down" title={sig}> ⚑ {sig}</small>}</td>
                  <td>{nf(l.qty, l.qty % 1 ? 2 : 0)}</td><td>{inr(l.price, 2)}</td><td>{l.row?.price != null ? inr(l.row.price, 2) : "—"}</td><td>{l.value != null ? inr(l.value) : "—"}</td>
                  <td><span className="wbar"><i style={{ width: `${Math.min(100, l.weight)}%` }} /></span>{nf(l.weight, 1)}%</td>
                  <td className={tone(l.pnl)}>{l.pnl != null ? `${l.pnl >= 0 ? "+" : ""}${inr(l.pnl)}` : "—"}<small>{sgn(l.pnlPct)}{l.cagr != null ? ` · ${sgn(l.cagr, 0)}/yr` : ""}</small></td>
                  <td className={tone(l.row?.change_pct ?? null)}>{sgn(l.row?.change_pct ?? null, 2)}</td>
                  <td>{l.row?.overall != null ? <span className={"band-dot " + l.row.band}>{l.row.overall}</span> : "—"}</td>
                  <td className="ra"><AlertButton symbol={l.symbol} className="btn" /> <button className="btn" aria-label={`Edit ${l.symbol}`} onClick={() => { setEdit(l.id); setForm({ symbol: l.symbol, qty: String(l.qty), price: String(l.price), date: l.date || "" }); window.scrollTo({ top: 0, behavior: "smooth" }); }}>Edit</button> <button className="btn" aria-label={`Remove ${l.symbol}`} onClick={() => { portfolio.remove(l.id); toast(`${l.symbol} removed.`); }}>✕</button></td></tr>); })}</tbody></table></div>
            <p className="faint" style={{ fontSize: 12.5, marginTop: 10 }}>Values use the latest price and your entered average cost; charges and taxes are not included. Per-year returns show for holdings bought at least two months ago. Information only, not investment advice.</p>
          </section></>}
      </Gate>
    </div>
  );
}
