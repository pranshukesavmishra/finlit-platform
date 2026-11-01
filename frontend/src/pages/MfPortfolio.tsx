import { PageHeader } from "../components/PageHeader";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { Gate } from "../components/Gate";
import { Donut } from "../charts/Atlas";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import { useUI } from "../lib/ui";
import { limitsFor } from "../lib/auth";
import { saveFile } from "../stock/derive";
import { bandOf, scoreText } from "../lib/mfScore";
import { bandVar } from "../lib/scoreBands";
import { statementFromFile, FIELD_LABEL, type Statement } from "../lib/mfStatement";
import {
  LEVEL_WORD, MF_INFO_ONLY, MF_SCORE_LINE, PARTS, STATUS_WORD, commitItems, crores, csvFileName, gainTone, initialDecisions, pct1, reviewCounts, rupees, searchFunds, sortHoldings, toCsv,
  useMfPortfolio, useMfWrites, type Decision, type Fund, type Holding, type Preview, type ReviewRow, type SortKey,
} from "../lib/mfPortfolio";
import { dateIN } from "../lib/format";
import "../styles/mf.css";
import "../styles/mfportfolio.css";

const K = ["var(--k1)", "var(--k2)", "var(--k3)", "var(--k7)", "var(--k5)", "var(--k4)", "var(--k6)", "var(--k8)", "var(--k1)"];
const errText = (e: unknown) => ((e as { body?: { detail?: string } })?.body?.detail) || (e instanceof Error ? e.message : "Something went wrong. Please try again.");
const Dash = ({ why }: { why?: string | null }) => <span className="pf-dash" title={why || undefined} aria-label={why ? `Not shown. ${why}` : "Not available"} tabIndex={why ? 0 : undefined}>–</span>;

/* --------------------------------------------------------------- fund search */
function FundSearch({ onPick, placeholder = "Search a fund by name…" }: { onPick: (f: Fund) => void; placeholder?: string }) {
  const [q, setQ] = useState(""), [items, setItems] = useState<Fund[]>([]), [busy, setBusy] = useState(false), [err, setErr] = useState("");
  useEffect(() => {
    if (q.trim().length < 3) { setItems([]); setErr(""); return; }
    setBusy(true);
    const t = setTimeout(() => searchFunds(q.trim()).then((r) => { setItems(r); setErr(""); }).catch(() => setErr("The fund search is not available right now.")).finally(() => setBusy(false)), 250);
    return () => clearTimeout(t);
  }, [q]);
  return (
    <div className="mp-search">
      <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder} aria-label="Search a mutual fund" maxLength={80} autoComplete="off" />
      {q.trim().length >= 3 && (
        <ul role="listbox" aria-label="Funds found" aria-busy={busy}>
          {err && <li className="none">{err}</li>}
          {!err && !busy && !items.length && <li className="none">No fund matches “{q}”.</li>}
          {items.map((f) => <li key={f.code} role="option" aria-selected="false"><button type="button" onClick={() => { onPick(f); setQ(""); setItems([]); }}><b>{f.name}</b><small>{f.amc} · {f.plan} · {f.option}{f.navDate ? ` · NAV ${dateIN(f.navDate)}` : ""}</small></button></li>)}
        </ul>)}
    </div>
  );
}

/* --------------------------------------------------------------- add one */
function AddFund({ disabled, onDone }: { disabled: boolean; onDone: (msg: string) => void }) {
  const w = useMfWrites();
  const [fund, setFund] = useState<Fund | null>(null), [units, setUnits] = useState(""), [mode, setMode] = useState<"avg" | "total" | "none">("total");
  const [cost, setCost] = useState(""), [date, setDate] = useState(""), [folio, setFolio] = useState(""), [err, setErr] = useState("");
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr("");
    if (!fund) { setErr("Choose a fund from the search first."); return; }
    try {
      const r = await w.add.mutateAsync({ code: fund.code, units, folio, ...(mode === "avg" && cost ? { avgCost: cost } : mode === "total" && cost ? { invested: cost } : {}), ...(date ? { boughtOn: date } : {}) });
      onDone(r.merged ? "Added as another purchase of the fund you already hold in that folio." : "Fund added."); setFund(null); setUnits(""); setCost(""); setDate(""); setFolio("");
    } catch (x) { setErr(errText(x)); }
  };
  return (
    <form className="mp-form" onSubmit={submit}>
      {fund ? <div className="mp-picked"><b>{fund.name}</b><small>{fund.amc} · {fund.plan} · {fund.option}</small><button type="button" className="btn" onClick={() => setFund(null)}>Change</button></div> : <FundSearch onPick={setFund} />}
      <div className="mp-grid">
        <label>Units held<input inputMode="decimal" value={units} onChange={(e) => setUnits(e.target.value)} placeholder="e.g. 245.678" required /></label>
        <label>Cost<select value={mode} onChange={(e) => setMode(e.target.value as typeof mode)}><option value="total">Amount invested (₹)</option><option value="avg">Average cost per unit (₹)</option><option value="none">Not known</option></select></label>
        <label>{mode === "avg" ? "Average cost" : "Amount"}<input inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} disabled={mode === "none"} placeholder={mode === "none" ? "—" : "e.g. 50000"} /></label>
        <label>Purchase date (optional)<input type="date" value={date} onChange={(e) => setDate(e.target.value)} max={new Date().toISOString().slice(0, 10)} /></label>
        <label>Folio (optional)<input value={folio} onChange={(e) => setFolio(e.target.value)} maxLength={40} placeholder="e.g. 1234567/89" /></label>
      </div>
      <p className="faint mp-note">A purchase date lets us work out XIRR. Without a cost, the gain is shown as a dash with the reason.</p>
      {err && <p className="mp-err" role="alert">{err}</p>}
      <button className="btn primary" disabled={disabled || w.add.isPending}>{w.add.isPending ? "Adding…" : "Add fund"}</button>
    </form>
  );
}

/* --------------------------------------------------------------- import review */
function Review({ st, pv, onClose, onDone }: { st: Statement; pv: Preview; onClose: () => void; onDone: (msg: string) => void }) {
  const w = useMfWrites();
  const [dec, setDec] = useState<Record<number, Decision>>(() => initialDecisions(pv.rows));
  const [skip, setSkip] = useState<Set<number>>(new Set()), [existing, setExisting] = useState<"skip" | "replace">("skip"), [err, setErr] = useState(""), [changing, setChanging] = useState<number | null>(null);
  const c = reviewCounts(pv.rows, dec, skip), room = pv.capacity.room;
  const items = commitItems(pv.rows, dec, skip);
  const hdr = Object.entries(st.headers).map(([k, v]) => `${v} → ${FIELD_LABEL[k as keyof typeof FIELD_LABEL]}`).join(" · ");
  const pick = (r: ReviewRow, code: number | null, fund: Fund | null) => setDec((d) => ({ ...d, [r.i]: { code, fund } }));
  const go = async () => {
    setErr("");
    try { const r = await w.commit.mutateAsync({ items, existing }); onDone(`Imported: ${r.added} added${r.replaced ? `, ${r.replaced} replaced` : ""}${r.skipped ? `, ${r.skipped} already held (skipped)` : ""}${r.duplicates ? `, ${r.duplicates} repeated line(s) counted once` : ""}.`); }
    catch (x) { setErr(errText(x)); }
  };
  return (
    <section className="card mp-review" aria-label="Import review">
      <div className="card-h"><h3>Review before importing</h3><span className="s">{pv.total} rows read</span></div>
      <p className="muted">Columns read: {hdr}. Nothing is imported until you confirm. Rows that are not matched to a fund, and company shares, are never imported.</p>
      <ul className="mp-counts">{(Object.keys(STATUS_WORD) as (keyof typeof STATUS_WORD)[]).filter((k) => pv.counts[k]).map((k) => <li key={k} className={"st-" + k}><b>{pv.counts[k]}</b> {STATUS_WORD[k].toLowerCase()}</li>)}</ul>
      <div className="mp-tablewrap"><table className="mp-rt">
        <thead><tr><th>Line</th><th>In your file</th><th>Status</th><th>Fund in FinLit</th><th>Notes</th><th>Import</th></tr></thead>
        <tbody>{pv.rows.map((r) => {
          const can = r.status === "matched" || r.status === "choose" || r.status === "not_found", d = dec[r.i];
          return (
            <tr key={r.i} className={"st-" + r.status}>
              <td data-label="Line">{r.row || r.i + 1}</td>
              <td data-label="In your file"><b>{r.name || r.isin || "(no name)"}</b><small>{r.units != null ? `${r.units} units` : ""}{r.invested != null ? ` · ${rupees(r.invested)}` : ""}{r.boughtOn ? ` · ${dateIN(r.boughtOn)}` : ""}{r.folio ? ` · folio ${r.folio}` : ""}</small></td>
              <td data-label="Status"><span className={"mp-chip st-" + r.status}>{STATUS_WORD[r.status]}</span></td>
              <td data-label="Fund in FinLit">
                {can && d?.fund && changing !== r.i && <div><b>{d.fund.name}</b><small>{d.fund.amc} · {d.fund.plan} · {d.fund.option}</small> <button className="mp-link" onClick={() => setChanging(r.i)}>Change</button></div>}
                {can && (!d?.fund || changing === r.i) && (<>
                  {r.candidates.length > 0 && <select aria-label={`Choose the fund for line ${r.row || r.i + 1}`} value={d?.code ?? ""} onChange={(e) => { const f = r.candidates.find((x) => x.code === Number(e.target.value)) || null; pick(r, f ? f.code : null, f); setChanging(null); }}>
                    <option value="">Choose a fund…</option>{r.candidates.map((f) => <option key={f.code} value={f.code}>{f.name} ({f.plan}, {f.option}{f.active ? "" : ", stopped"})</option>)}</select>}
                  <FundSearch placeholder={r.candidates.length ? "…or search another fund" : "Search for this fund…"} onPick={(f) => { pick(r, f.code, f); setChanging(null); }} />
                </>)}
                {!can && <span className="faint">—</span>}
              </td>
              <td data-label="Notes"><small>{r.reason}{r.existing && d?.code === r.fund?.code ? " Already in your portfolio." : ""}{r.warnings.map((x) => " " + x)}</small></td>
              <td data-label="Import">{can ? <input type="checkbox" aria-label={`Import line ${r.row || r.i + 1}`} checked={!skip.has(r.i) && d?.code != null} disabled={d?.code == null} onChange={(e) => setSkip((s) => { const n = new Set(s); if (e.target.checked) n.delete(r.i); else n.add(r.i); return n; })} /> : <span className="faint">No</span>}</td>
            </tr>);
        })}</tbody></table></div>
      {c.existing > 0 && <fieldset className="mp-ex"><legend>{c.existing} fund(s) are already in your portfolio</legend>
        <label><input type="radio" checked={existing === "skip"} onChange={() => setExisting("skip")} /> Keep what I have (skip them; nothing is counted twice)</label>
        <label><input type="radio" checked={existing === "replace"} onChange={() => setExisting("replace")} /> Replace their purchases with the file's</label></fieldset>}
      {c.needChoice > 0 && <p className="mp-warn" role="status">{c.needChoice} row(s) still need a fund chosen and will not be imported.</p>}
      {c.ready > room + c.existing && <p className="mp-warn" role="status">Your plan holds {pv.capacity.limit} funds ({pv.capacity.used} used); untick some rows.</p>}
      {err && <p className="mp-err" role="alert">{err}</p>}
      <div className="row"><button className="btn primary" onClick={go} disabled={!items.length || w.commit.isPending}>{w.commit.isPending ? "Importing…" : `Import ${items.length} ${items.length === 1 ? "row" : "rows"}`}</button><button className="btn" onClick={onClose}>Cancel</button></div>
    </section>
  );
}

function ImportFile({ onDone }: { onDone: (msg: string) => void }) {
  const w = useMfWrites(), ref = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false), [err, setErr] = useState(""), [rev, setRev] = useState<{ st: Statement; pv: Preview } | null>(null);
  const read = async (f: File) => {
    setBusy(true); setErr(""); setRev(null);
    try { const st = await statementFromFile(f); setRev({ st, pv: await w.preview.mutateAsync(st.rows) }); }
    catch (x) { setErr(errText(x)); } finally { setBusy(false); }
  };
  return (<>
    <div className="row mp-file"><button className="btn primary" onClick={() => ref.current?.click()} disabled={busy}><Icon name="table" />{busy ? "Reading…" : "Choose Excel or CSV…"}</button>
      <input ref={ref} type="file" hidden accept=".xlsx,.xls,.csv,.tsv,.txt,.html,.htm" onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) read(f); }} />
      <span className="faint">.xlsx, .xls or .csv, up to 5 MB and 2,000 rows. CAMS, KFintech and broker holdings exports work. Read in your browser; only the fund rows are sent.</span></div>
    {err && <p className="mp-err" role="alert">{err}</p>}
    {rev && <Review st={rev.st} pv={rev.pv} onClose={() => setRev(null)} onDone={(m) => { setRev(null); onDone(m); }} />}
  </>);
}

/* --------------------------------------------------------------- table */
const Score = ({ h, locked, onUnlock }: { h: Holding; locked: boolean; onUnlock: () => void }) => {
  if (locked) return <button className="mp-lock" onClick={onUnlock} title="The FinLit Mutual Fund Health Score is part of the Gold plan."><Icon name="lock" /><span>Gold</span></button>;
  const s = h.score;
  if (s.final == null) return <span className="faint mp-nos" title={s.reason || ""}>{s.status === "NOT RATED" ? "Not rated" : "No score"}<small>{s.reason}</small></span>;
  return (<div className="mp-score" title={`${s.label}${s.status === "PROVISIONAL" ? ", provisional" : ""}. ${MF_SCORE_LINE}`}>
    <b className={"mfs-pv b-" + bandOf(s.final)}>{scoreText(s.final)}</b><small>{s.label}{s.status === "PROVISIONAL" ? " · provisional" : ""}</small>
    <div className="mp-parts">{PARTS.map(([k, short, full]) => { const v = s.parts?.[k] ?? null; return <span key={k} title={`${full} ${v == null ? "n/a" : scoreText(v)}`} aria-label={`${full} ${v == null ? "not available" : scoreText(v)}`}><i style={{ height: `${v ?? 0}%`, background: bandVar(bandOf(v)) }} /><em>{short}</em><u>{v == null ? "–" : Math.round(v)}</u></span>; })}</div>
  </div>);
};

const COLS: { k: SortKey; label: string; cls?: string }[] = [
  { k: "current", label: "Current value" }, { k: "invested", label: "Invested" }, { k: "gain", label: "Gain" }, { k: "xirr", label: "XIRR" },
  { k: "r1y", label: "1Y" }, { k: "r3y", label: "3Y" }, { k: "r5y", label: "5Y" }, { k: "ter", label: "Expense ratio" }, { k: "aum", label: "Fund size" }, { k: "weight", label: "Weight" },
];

function EditRow({ h, onClose, onDone }: { h: Holding; onClose: () => void; onDone: (m: string) => void }) {
  const w = useMfWrites();
  const [folio, setFolio] = useState(h.folio), [err, setErr] = useState("");
  const [lots, setLots] = useState(h.lots.map((l) => ({ units: String(l.units), invested: l.invested == null ? "" : String(l.invested), boughtOn: l.boughtOn || "" })));
  const set = (i: number, k: string, v: string) => setLots((a) => a.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
  const save = async () => { setErr(""); try { await w.update.mutateAsync({ id: h.id, folio, lots: lots.map((l) => ({ units: l.units, ...(l.invested ? { invested: l.invested } : {}), ...(l.boughtOn ? { boughtOn: l.boughtOn } : {}) })) }); onDone("Saved."); } catch (x) { setErr(errText(x)); } };
  return (<div className="mp-edit"><b>Edit {h.name}</b>
    <label>Folio<input value={folio} onChange={(e) => setFolio(e.target.value)} maxLength={40} /></label>
    {lots.map((l, i) => <div className="mp-lot" key={i}><label>Units<input value={l.units} onChange={(e) => set(i, "units", e.target.value)} /></label><label>Amount invested (₹)<input value={l.invested} onChange={(e) => set(i, "invested", e.target.value)} placeholder="not known" /></label>
      <label>Purchase date<input type="date" value={l.boughtOn} onChange={(e) => set(i, "boughtOn", e.target.value)} /></label>{lots.length > 1 && <button className="btn" onClick={() => setLots((a) => a.filter((_, j) => j !== i))}>Remove purchase</button>}</div>)}
    {err && <p className="mp-err" role="alert">{err}</p>}
    <div className="row"><button className="btn" onClick={() => setLots((a) => [...a, { units: "", invested: "", boughtOn: "" }])}>Add a purchase</button><button className="btn primary" onClick={save} disabled={w.update.isPending}>Save</button><button className="btn" onClick={onClose}>Cancel</button></div></div>);
}

/* --------------------------------------------------------------- page */
export function MfPortfolioPage() {
  useDocTitle("MF portfolio", "Add the mutual funds you hold, by search or from an Excel or CSV statement, and see each fund's value, returns and FinLit Health Score.");
  const { plan, has, toast, upgrade } = useUI();
  const silver = has("silver");
  const q = useMfPortfolio(silver), w = useMfWrites();
  const [tab, setTab] = useState<"add" | "import">("add"), [key, setKey] = useState<SortKey>("current"), [dir, setDir] = useState<"asc" | "desc">("desc"), [editing, setEditing] = useState<string | null>(null);
  const d = q.data, locked = d ? d.scoreLocked : !has("gold");
  const rows = useMemo(() => (d ? sortHoldings(d.holdings, key, dir) : []), [d, key, dir]);
  const limit = d?.limit ?? limitsFor(plan).mf_holdings;
  const sort = (k: SortKey) => { if (k === key) setDir(dir === "asc" ? "desc" : "asc"); else { setKey(k); setDir(k === "name" ? "asc" : "desc"); } };
  const th = (k: SortKey, label: string, cls = "") => <th key={k} scope="col" className={cls} aria-sort={k === key ? (dir === "asc" ? "ascending" : "descending") : "none"}><button className="mp-sortb" onClick={() => sort(k)}>{label}{k === key ? (dir === "asc" ? " ▲" : " ▼") : ""}</button></th>;
  const unlock = () => upgrade("gold", "The FinLit Mutual Fund Health Score is part of Gold.");
  const s = d?.summary;

  return (
    <div className="wrap ipo mp">
      <PageHeader plan="silver" title="MF portfolio" art="funds" links={["/holdings", "/funds", "/fund-score-screener"]}
        description={<>The mutual funds you hold: <b>what they are worth at the latest NAV</b>, how they have returned and, on Gold, how healthy each fund is. Mutual funds only; company shares are left out.</>}
        stats={[{ icon: "layers", value: s && s.funds > 0 ? s.funds : null, label: "Funds held" }, { icon: "calendar", value: d?.dataDate, label: "NAV as of" }]} />
      <Gate tier="silver" title="Track your mutual funds" points={["Value at the latest NAV, gain and XIRR", "Import Excel or CSV statements (CAMS, KFintech, broker apps)", "Allocation by category and fund house", "Health Score and its four parts on Gold"]}>
        <aside className="pf-model" aria-label="About the score"><span className="ci"><Icon name="quality" /></span><p>{MF_SCORE_LINE} {MF_INFO_ONLY}{locked && <> The Health Score is part of the Gold plan; you still see values and returns. <Link to="/plans">See the Gold plan</Link>.</>}</p></aside>
        <section className="card acct-c pf-in">
          <div className="pf-tabs" role="tablist"><button role="tab" aria-selected={tab === "add"} className={tab === "add" ? "on" : ""} onClick={() => setTab("add")}>Add a fund</button><button role="tab" aria-selected={tab === "import"} className={tab === "import" ? "on" : ""} onClick={() => setTab("import")}>Import a file</button></div>
          {tab === "add" ? <AddFund disabled={false} onDone={toast} /> : <ImportFile onDone={toast} />}
        </section>

        {q.isPending && silver && <div className="card dw-empty" aria-busy="true"><b>Loading your funds…</b></div>}
        {q.isError && <div className="card dw-empty" role="alert"><b>Your funds could not be loaded</b><p>{errText(q.error)}</p><button className="btn" onClick={() => q.refetch()}>Try again</button></div>}
        {d && !d.count && <div className="card dw-empty"><span className="dw-ei"><Icon name="wallet" /></span><b>No mutual funds yet</b><p>Search a fund above and enter your units, or import a statement. {limit} funds fit in your plan.</p></div>}
        {d && s && d.count > 0 && <>
          <div className="mp-tiles">
            <div className="card"><small>Invested</small><b>{rupees(s.invested)}</b><span className="faint">{s.invested == null ? "No amount paid is known yet." : `${s.gainFunds} of ${s.funds} funds`}</span></div>
            <div className="card"><small>Current value</small><b>{rupees(s.current)}</b><span className="faint">{s.navTo ? `NAV ${s.navFrom === s.navTo ? dateIN(s.navTo) : dateIN(s.navFrom!) + " to " + dateIN(s.navTo)}` : "No NAV yet"}</span></div>
            <div className={"card " + gainTone(s.gain)}><small>Total gain</small><b>{s.gain == null ? "—" : (s.gain > 0 ? "+" : "") + rupees(s.gain)}</b><span>{pct1(s.gainPct, true)}</span></div>
            <div className="card"><small>XIRR</small><b>{s.xirr == null ? "–" : pct1(s.xirr)}</b><span className="faint">{s.xirr == null ? s.xirrWhy : `${s.xirrFunds} fund(s) with dated purchases`}</span></div>
            <div className="card"><small>Funds</small><b>{s.funds}</b><span className="faint">of {limit} in your plan</span></div>
            <div className="card"><small>Portfolio Health Score</small>{locked ? <button className="mp-lock" onClick={unlock}><Icon name="lock" /><span>Gold</span></button> : <b className={"mfs-pv b-" + bandOf(s.score.value)}>{s.score.value == null ? "–" : scoreText(s.score.value)}</b>}<span className="faint">{locked ? "Unlock with Gold" : s.score.value != null ? `${s.score.label}, weighted by value` : s.score.why}</span></div>
          </div>
          {s.notes.map((n) => <p key={n} className="faint mp-note" role="note">{n}</p>)}
          <div className="pf-g">
            <section className="card"><div className="card-h"><h3>By category</h3><span className="s">Share of current value</span></div><Donut parts={d.allocation.byCategory.map((p, i) => ({ label: p.label, value: p.value, color: K[i % K.length] }))} center={String(d.allocation.byCategory.length)} sub="CATEGORIES" /></section>
            <section className="card"><div className="card-h"><h3>By fund house</h3><span className="s">Share of current value</span></div><Donut parts={d.allocation.byAmc.map((p, i) => ({ label: p.label, value: p.value, color: K[i % K.length] }))} center={String(d.allocation.byAmc.length)} sub="FUND HOUSES" /></section>
          </div>
          <section className="card mp-conc"><div className="card-h"><h3>Concentration</h3>{d.concentration.level && <span className={"mp-chip lv-" + d.concentration.level}>{LEVEL_WORD[d.concentration.level]}</span>}</div><p>{d.concentration.text}</p></section>
          {locked && <section className="card mp-teaser"><Icon name="lock" /><div><b>Each fund's Health Score is part of Gold</b><p className="muted">Gold shows a score from 0 to 100 for every fund you hold, with its four parts: Performance, Risk, Cost and Quality. {MF_SCORE_LINE}</p></div><button className="btn" onClick={unlock}>Unlock with Gold</button></section>}
          <section className="card pf-tabs-card">
            <div className="card-h"><h3>Your funds</h3><span className="s">{d.count} of {limit}</span><button className="btn" onClick={() => saveFile(csvFileName(), toCsv(rows, locked), "text/csv;charset=utf-8")}>Export CSV</button></div>
            {!locked && <p className="faint mp-note">Score parts: Perf = Performance, Risk, Cost, Qual = Quality. Green 70 or more, orange 50 to 69, red under 50.</p>}
            <div className="mp-tablewrap"><table className="mp-t">
              <thead><tr>{th("name", "Fund", "l")}{th("score", "Health Score")}{COLS.map((c) => th(c.k, c.label))}<th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
              <tbody>{rows.map((h) => (<Fragment key={h.id}>
                <tr>
                  <td data-label="Fund" className="l"><Link to={`/funds/${h.code}`}><b>{h.name || `Scheme ${h.code}`}</b></Link><small>{h.amc} · {h.plan} · {h.option}{h.categoryLabel ? ` · ${h.categoryLabel}` : ""}{h.folio ? ` · folio ${h.folio}` : ""}</small></td>
                  <td data-label="Health Score"><Score h={h} locked={locked} onUnlock={unlock} /></td>
                  <td data-label="Current value">{h.current == null ? <Dash why={h.currentWhy} /> : <><b>{rupees(h.current)}</b><small className={h.navStale ? "warn" : ""} title={h.navNote || undefined}>{h.units.toLocaleString("en-IN", { maximumFractionDigits: 4 })} × ₹{h.nav} · {h.navDate ? dateIN(h.navDate) : ""}</small></>}</td>
                  <td data-label="Invested">{h.invested == null ? <Dash why={h.investedWhy} /> : rupees(h.invested)}</td>
                  <td data-label="Gain" className={gainTone(h.gain)}>{h.gain == null ? <Dash why={h.gainWhy} /> : <><b>{(h.gain > 0 ? "+" : "") + rupees(h.gain)}</b><small>{pct1(h.gainPct, true)}</small></>}</td>
                  <td data-label="XIRR">{h.xirr == null ? <Dash why={h.xirrWhy} /> : <><b>{pct1(h.xirr)}</b><small>{h.xirrKind === "cagr" ? "CAGR" : "XIRR"}</small></>}</td>
                  {(["r1y", "r3y", "r5y"] as const).map((k) => <td key={k} data-label={k.slice(1).toUpperCase()}>{h.returns[k] == null ? <Dash why={h.returns.why || h.returns.partialWhy} /> : pct1(h.returns[k])}</td>)}
                  <td data-label="Expense ratio">{h.ter == null ? <Dash why={h.terWhy} /> : pct1(h.ter)}</td>
                  <td data-label="Fund size">{h.aum == null ? <Dash why={h.aumWhy} /> : crores(h.aum)}</td>
                  <td data-label="Weight">{h.weight == null ? <Dash why={h.weightWhy} /> : pct1(h.weight)}</td>
                  <td className="mp-act"><button className="btn" onClick={() => setEditing(editing === h.id ? null : h.id)} aria-label={`Edit ${h.name}`}>Edit</button> <button className="btn" aria-label={`Remove ${h.name}`} onClick={async () => { try { await w.remove.mutateAsync(h.id); toast("Fund removed."); } catch (x) { toast(errText(x)); } }}>✕</button></td>
                </tr>
                {editing === h.id && <tr className="mp-er"><td colSpan={13}><EditRow h={h} onClose={() => setEditing(null)} onDone={(m) => { setEditing(null); toast(m); }} /></td></tr>}
              </Fragment>))}</tbody></table></div>
            <p className="faint mp-note">Values use each fund's latest published NAV (date shown). Returns are the fund's own 1, 3 and 5 year returns (3 and 5 per year), not yours. XIRR needs every purchase dated. {MF_INFO_ONLY}</p>
          </section>
        </>}
      </Gate>
    </div>
  );
}
