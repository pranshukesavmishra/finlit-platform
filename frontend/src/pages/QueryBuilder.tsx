// Query builder: type a rule in plain words, get the listed companies that match it, and keep it as a basket. The language, every error and the
// matching happen on the server (backend/finlit/screener/ql.py, qeval.py); this page helps a person write the query without mistakes:
// autocomplete, live checking with one-click fixes, an "Add a condition" helper, examples and a list of every ratio.
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { PageArt } from "../components/PageArt";
import { Plain } from "../components/Plain";
import { HScroll } from "../components/HScroll";
import { Icon } from "../lib/icons";
import { nf } from "../lib/format";
import { API_BASE, ApiError, apiUrl } from "../lib/api";
import { useAuth } from "../lib/auth";
import { DEMO } from "../lib/demo";
import { fmtMetric } from "../lib/proscreen";
import {
  CONNECTORS, OPS, acceptCompletion, addCondition, applyFix, basketNameProblem, completionAt, conditionText, draftProblem, leftOutLines, nameSet, quarterLabel, rankRatios,
  runQuery, segments, unitHint, useBasket, useBasketActions, useBaskets, useRatios, validateQuery,
  type Basket, type Completion, type Problem, type Ratio, type Reading, type RunBad, type RunBody, type RunOk, type Validation,
} from "../lib/query";
import { saveFile } from "../stock/derive";
import { useDocTitle } from "../lib/title";
import { TIER, useUI, type Plan } from "../lib/ui";
import "../styles/qbuilder.css";

const PAGE = 50;
const DRAFT = "finlit-qb-draft";
const readDraft = () => { try { return localStorage.getItem(DRAFT) || ""; } catch { return ""; } };
const keepDraft = (t: string) => { try { localStorage.setItem(DRAFT, t); } catch { /* private mode */ } };

function ReadingTree({ r, top = true }: { r: Reading; top?: boolean }) {
  if (r.type === "cond") return <li>{r.text}</li>;
  const word = r.type === "and" ? "All of these are true" : "At least one of these is true";
  const body = <ul>{r.items.map((i, k) => <ReadingTree key={k} r={i} top={false} />)}</ul>;
  return top ? <div className="qb-read"><b>{word}:</b>{body}</div> : <li><b>{word}:</b>{body}</li>;
}

/** A search box over the ratios; picking one calls onPick. Used by the "Add a condition" helper and the column menu. */
function RatioPicker({ ratios, onPick, placeholder = "Search a ratio, e.g. ROE or debt", label = "Search ratios", autoFocus }: { ratios: Ratio[]; onPick: (r: Ratio) => void; placeholder?: string; label?: string; autoFocus?: boolean }) {
  const [q, setQ] = useState(""), [hi, setHi] = useState(0);
  const list = useMemo(() => rankRatios(ratios, q, 8), [ratios, q]);
  useEffect(() => setHi(0), [q]);
  const pick = (r: Ratio) => { onPick(r); setQ(""); };
  return (
    <div className="qb-pick">
      <label className="scr-find sm"><Icon name="search" /><input value={q} autoFocus={autoFocus} onChange={(e) => setQ(e.target.value)} placeholder={placeholder} aria-label={label} role="combobox" aria-expanded={list.length > 0} aria-controls="qb-pick-list"
        onKeyDown={(e) => { if (e.key === "ArrowDown") { e.preventDefault(); setHi((h) => Math.min(list.length - 1, h + 1)); } else if (e.key === "ArrowUp") { e.preventDefault(); setHi((h) => Math.max(0, h - 1)); } else if (e.key === "Enter" && list[hi]) { e.preventDefault(); pick(list[hi]); } }} /></label>
      <ul id="qb-pick-list" className="qb-opts" role="listbox" aria-label="Matching ratios">
        {list.map((r, i) => <li key={r.key} role="option" aria-selected={i === hi}><button className={i === hi ? "on" : ""} onClick={() => pick(r)} onMouseEnter={() => setHi(i)}><b>{r.label}</b><small>{r.groupLabel} · {r.unitLabel}</small>{r.locked && <span className="qb-lk"><Icon name="lock" />{TIER[r.tier].n}</span>}</button></li>)}
        {!list.length && <li className="faint qb-none">No ratio is called that. Try another word, or open “Show all ratios”.</li>}
      </ul>
    </div>
  );
}

/** Pick a ratio, a comparison and a value; the page writes the text. */
function ConditionHelper({ ratios, hasText, onAdd }: { ratios: Ratio[]; hasText: boolean; onAdd: (text: string, joiner: "AND" | "OR") => void }) {
  const [ratio, setRatio] = useState<Ratio | null>(null), [op, setOp] = useState(">"), [value, setValue] = useState(""), [yes, setYes] = useState(true), [joiner, setJoiner] = useState<"AND" | "OR">("AND"), [touched, setTouched] = useState(false);
  const draft = { ratio, op, value, yes };
  const bad = draftProblem(draft), text = conditionText(draft);
  const add = () => { setTouched(true); if (bad) return; onAdd(text, joiner); setValue(""); setTouched(false); };
  return (
    <div className="qb-help card" role="group" aria-label="Add a condition">
      <h3>Add a condition</h3>
      <p className="qb-sub">Pick a ratio, say how it should compare, and we write the line for you.</p>
      <div className="qb-step"><span className="qb-n">1</span><div>
        {ratio ? <div className="qb-chosen"><b>{ratio.label}</b><small>{ratio.unitLabel}</small><button className="lnk" onClick={() => setRatio(null)}>Change</button></div> : <RatioPicker ratios={ratios} onPick={(r) => { setRatio(r); setTouched(false); }} />}
        {ratio && ratio.definition && <small className="qb-def">{ratio.definition}</small>}
      </div></div>
      {ratio && ratio.unit !== "flag" && <>
        <div className="qb-step"><span className="qb-n">2</span><label>Compare<select value={op} onChange={(e) => setOp(e.target.value)} aria-label="How to compare">{OPS.map((o) => <option key={o.op} value={o.op}>{ratio.label} {o.say}</option>)}</select></label></div>
        <div className="qb-step"><span className="qb-n">3</span><label>Value<input value={value} inputMode="decimal" onChange={(e) => setValue(e.target.value)} onKeyDown={(e) => e.key === "Enter" && add()} placeholder={ratio.example.replace(/^.*[<>=!]+\s*/, "")} aria-label={`Value for ${ratio.label}`} aria-invalid={touched && !!bad} />
          <small>{unitHint(ratio)}</small></label></div>
      </>}
      {ratio && ratio.unit === "flag" && <div className="qb-step"><span className="qb-n">2</span><div className="seg" role="group" aria-label="Yes or no">{[true, false].map((y) => <button key={String(y)} aria-pressed={yes === y} onClick={() => setYes(y)}>{y ? "Yes" : "No"}</button>)}</div></div>}
      {hasText && <div className="qb-step"><span className="qb-n">{ratio?.unit === "flag" ? 3 : 4}</span><div className="seg" role="group" aria-label="How it joins the rest">
        {CONNECTORS.map((c) => <button key={c.op} aria-pressed={joiner === c.op} onClick={() => setJoiner(c.op as "AND" | "OR")}>{c.op === "AND" ? "AND: must also match" : "OR: or this instead"}</button>)}</div></div>}
      <div className="qb-prev" aria-live="polite">{bad && touched ? <span className="qb-err">{bad}</span> : text ? <><small>This line will be added:</small><code>{text}</code></> : <small>Your line appears here.</small>}</div>
      <button className="btn primary" onClick={add} disabled={!ratio}>Add to query</button>
    </div>
  );
}

/** Every ratio, searchable, with its meaning, unit and plan. Slides in from the right (full screen on a phone). */
function RatioDrawer({ ratios, open, onClose, seed, onAdd, onInsert, ask }: { ratios: Ratio[]; open: boolean; onClose: () => void; seed: string; onAdd: (r: Ratio) => void; onInsert: (r: Ratio) => void; ask: (t: Plan, why: string) => void }) {
  const [q, setQ] = useState(seed), [group, setGroup] = useState("");
  useEffect(() => { if (open) setQ(seed); }, [open, seed]);
  useEffect(() => { if (!open) return; const k = (e: KeyboardEvent) => e.key === "Escape" && onClose(); addEventListener("keydown", k); return () => removeEventListener("keydown", k); }, [open, onClose]);
  const groups = useMemo(() => Array.from(new Map(ratios.map((r) => [r.group, r.groupLabel])).entries()), [ratios]);
  const list = useMemo(() => rankRatios(ratios.filter((r) => !group || r.group === group), q, 400), [ratios, q, group]);
  if (!open) return null;
  return (
    <>
      <div className="qb-scrim" onClick={onClose} aria-hidden="true" />
      <aside className="qb-drawer" role="dialog" aria-modal="true" aria-label="All ratios">
        <header><h2>All ratios <small>{ratios.length}</small></h2><button className="btn" onClick={onClose} aria-label="Close the list of ratios">Close</button></header>
        <label className="scr-find"><Icon name="search" /><input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by name, short form or meaning" aria-label="Search all ratios" /></label>
        <div className="qb-groups" role="group" aria-label="Filter by group"><button aria-pressed={!group} onClick={() => setGroup("")}>All</button>{groups.map(([id, label]) => <button key={id} aria-pressed={group === id} onClick={() => setGroup(id)}>{label}</button>)}</div>
        <ul className="qb-all">
          {list.map((r) => (
            <li key={r.key} className={r.locked ? "is-locked" : ""}>
              <div className="qb-allh"><b>{r.label}</b><span className="qb-unit">{r.unitLabel}</span>{r.tier !== "basic" && <span className={"tier " + r.tier}><Icon name={r.locked ? "lock" : TIER[r.tier].ic} />{TIER[r.tier].n}</span>}</div>
              {r.definition && <p>{r.definition}</p>}
              <small className="qb-names">You can also write: {r.names.slice(1, 6).join(", ") || r.label}</small>
              <div className="qb-allx"><code>{r.example}</code>
                {r.locked ? <button className="btn" onClick={() => ask(r.tier, `${r.label} is part of the ${TIER[r.tier].n} plan.`)}>Unlock with {TIER[r.tier].n}</button>
                  : <><button className="btn" onClick={() => { onAdd(r); onClose(); }}>Add this example</button><button className="btn" onClick={() => { onInsert(r); onClose(); }}>Insert the name</button></>}</div>
            </li>))}
          {!list.length && <li className="faint qb-none">No ratio matches “{q}”. We only offer ratios we can calculate, so a name that is not here cannot be used.</li>}
        </ul>
      </aside>
    </>
  );
}

export function QueryBuilder() {
  useDocTitle("Formula screener", "Type a rule such as Market cap > 500 AND P/E < 15 and get every listed Indian company that matches. Live checking, one-click fixes, examples and saved baskets.");
  const { upgrade, toast } = useUI();
  const { user } = useAuth();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const rat = useRatios();
  const ratios = rat.data?.ratios ?? [];
  const byKey = useMemo(() => new Map(ratios.map((r) => [r.key, r])), [ratios]);
  const names = useMemo(() => nameSet(ratios), [ratios]);
  const basketId = params.get("basket");
  const loaded = useBasket(basketId);
  const baskets = useBaskets(!!user && !DEMO);
  const act = useBasketActions();

  const [text, setText] = useState(() => params.get("q") ?? readDraft());
  const [undo, setUndo] = useState<string | null>(null);
  const [val, setVal] = useState<Validation | null>(null), [checking, setChecking] = useState(false), [netErr, setNetErr] = useState(false);
  const [cols, setCols] = useState<string[]>([]), [recent, setRecent] = useState(false);
  const [sort, setSort] = useState<{ key: string; dir: "asc" | "desc" }>({ key: "market_cap", dir: "desc" });
  const [page, setPage] = useState(0), [running, setRunning] = useState(false);
  const [res, setRes] = useState<RunOk | null>(null), [bad, setBad] = useState<RunBad | null>(null), [ranText, setRanText] = useState(""), [runErr, setRunErr] = useState("");
  const [caret, setCaret] = useState(0), [hi, setHi] = useState(0), [force, setForce] = useState(false), [closed, setClosed] = useState(false);
  const [drawer, setDrawer] = useState(false), [seed, setSeed] = useState(""), [helper, setHelper] = useState(false), [colMenu, setColMenu] = useState(false);
  const [saveName, setSaveName] = useState(""), [saveNote, setSaveNote] = useState(""), [saveErr, setSaveErr] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null), mirrorRef = useRef<HTMLDivElement>(null), seq = useRef(0), loadedFor = useRef<string | null>(null);

  // ---- a basket opened from ?basket=
  const basket: Basket | undefined = loaded.data?.basket;
  useEffect(() => {
    if (!basket || loadedFor.current === basket.id) return;
    loadedFor.current = basket.id;
    setText(basket.query); setCols(basket.columns); setRecent(basket.recent); setSaveName(basket.name); setSaveNote(basket.note || ""); if (basket.sort) setSort(basket.sort);
    setRes(null); setBad(null);
  }, [basket]);
  useEffect(() => { if (!basketId) { loadedFor.current = null; } }, [basketId]);
  useEffect(() => { if (!basketId) keepDraft(text); }, [text, basketId]);

  // ---- live checking, a moment after typing stops
  useEffect(() => {
    if (!text.trim()) { setVal(null); setChecking(false); return; }
    setChecking(true);
    const id = ++seq.current;
    const t = setTimeout(() => {
      validateQuery(text).then((v) => { if (id === seq.current) { setVal(v); setNetErr(false); setChecking(false); } })
        .catch(() => { if (id === seq.current) { setNetErr(true); setChecking(false); } });
    }, 280);
    return () => clearTimeout(t);
  }, [text]);

  const problems: Problem[] = val ? [...val.errors, ...val.warnings] : [];
  const errors = val?.errors ?? [], warnings = val?.warnings ?? [];
  const valid = !!val && val.ok && !checking && !netErr;
  const ask = useCallback((tier: Plan, why: string) => upgrade(tier, why), [upgrade]);

  // ---- autocomplete
  const comp: Completion = useMemo(() => {
    const c = completionAt(text, caret, names);
    return c.kind === "none" && force ? { kind: "metric", start: caret, end: caret, prefix: "" } : c;
  }, [text, caret, names, force]);
  type Opt = { label: string; sub: string; locked?: Ratio["tier"] | null; insert: string };
  const opts: Opt[] = useMemo(() => {
    if (closed || !ratios.length) return [];
    if (comp.kind === "metric") return rankRatios(ratios, comp.prefix, 8).map((r) => ({ label: r.label, sub: `${r.groupLabel} · ${r.unitLabel}`, locked: r.locked ? r.tier : null, insert: r.label }));
    if (comp.kind === "operator") return OPS.map((o) => ({ label: o.op, sub: o.say, insert: o.op }));
    if (comp.kind === "connector") return CONNECTORS.map((c) => ({ label: c.op, sub: c.say, insert: c.op }));
    return [];
  }, [comp, ratios, closed]);
  useEffect(() => setHi(0), [comp.kind, comp.prefix]);
  const edit = (next: string, at?: number) => {
    setText(next); setUndo(null); setClosed(false); setForce(false);
    if (at != null) requestAnimationFrame(() => { const t = taRef.current; if (t) { t.focus(); t.setSelectionRange(at, at); setCaret(at); } });
  };
  const accept = (o: Opt) => { const r = acceptCompletion(text, comp, o.insert); edit(r.text, r.caret); };

  const grow = useCallback(() => { const t = taRef.current; if (t) { t.style.height = "auto"; t.style.height = Math.min(Math.max(t.scrollHeight, 116), 360) + "px"; } }, []);
  useEffect(grow, [text, grow]);
  const syncScroll = () => { if (mirrorRef.current && taRef.current) { mirrorRef.current.scrollTop = taRef.current.scrollTop; } };

  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); run(0); return; }
    if ((e.ctrlKey || e.metaKey) && e.key === " ") { e.preventDefault(); setForce(true); setClosed(false); return; }
    if (!opts.length) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setHi((h) => (h + 1) % opts.length); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setHi((h) => (h - 1 + opts.length) % opts.length); }
    else if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); accept(opts[hi]); }
    else if (e.key === "Escape") { e.preventDefault(); setClosed(true); }
  };

  // ---- fixes and jumping to a problem
  const useFix = (f: { start: number; end: number; text: string }) => { const r = applyFix(text, f); edit(r.text, r.caret); };
  const jump = (p: Problem) => { const t = taRef.current; if (!t) return; t.focus(); t.setSelectionRange(p.start, Math.max(p.end, p.start)); setCaret(p.start); };
  const openAll = (q = "") => { setSeed(q); setDrawer(true); };
  const insertName = (r: Ratio) => { const t = taRef.current; const s = t?.selectionStart ?? text.length, e = t?.selectionEnd ?? text.length; const next = text.slice(0, s) + r.label + text.slice(e); edit(next, s + r.label.length); };
  const addLine = (cond: string, joiner: "AND" | "OR" = "AND") => { const r = addCondition(text, cond, joiner); edit(r.text, r.caret); };
  const loadExample = (q: string) => { if (text.trim() && text.trim() !== q) setUndo(text); setText(q); setClosed(true); setRes(null); setBad(null); if (basketId) { setParams({}, { replace: true }); } };

  // ---- running
  const bodyFor = (offset: number, s = sort): RunBody => ({ query: text, sort: s, columns: cols, recent, offset, limit: PAGE });
  const run = async (offset = 0, s = sort) => {
    if (!text.trim()) { setRunErr("Type a query first, or pick an example."); return; }
    setRunning(true); setRunErr("");
    try {
      const r = await runQuery(bodyFor(offset, s));
      if (r.ok) { setRes(r); setBad(null); setRanText(text); setPage(Math.floor(r.offset / PAGE)); } else { setBad(r); setRes(null); setVal((v) => v); }
    } catch (e) { setRunErr(e instanceof ApiError && e.body.detail ? e.body.detail : "We could not run the query just now. Please try again."); }
    finally { setRunning(false); }
  };
  const sortBy = (key: string) => {
    const next = sort.key === key ? { key, dir: sort.dir === "desc" ? ("asc" as const) : ("desc" as const) } : { key, dir: key === "name" || byKey.get(key)?.better === "lower" ? ("asc" as const) : ("desc" as const) };
    setSort(next); if (res) run(0, next);
  };
  const exportCsv = async () => {
    if (!rat.data?.limits.export) { ask("silver", "Downloading results comes with the Silver plan."); return; }
    try {
      const r = await fetch(apiUrl("/api/screener/ql/export"), { method: "POST", credentials: API_BASE ? "include" : "same-origin", headers: { "Content-Type": "application/json", Accept: "text/csv" }, body: JSON.stringify(bodyFor(0)) });
      if (!r.ok) throw new Error(String(r.status));
      saveFile("FinLit-query.csv", await r.text(), "text/csv;charset=utf-8"); toast("Saved your results as FinLit-query.csv.");
    } catch { toast("We could not prepare the download. Please try again."); }
  };
  const stale = !!res && ranText !== text;

  // ---- baskets
  const existing = (baskets.data?.baskets ?? []).map((b) => b.name);
  const nameBad = saveName.trim() ? basketNameProblem(saveName, existing, basket?.name) : null;
  const dirty = !!basket && (text !== basket.query || recent !== basket.recent || JSON.stringify(cols) !== JSON.stringify(basket.columns) || saveName.trim() !== basket.name || (saveNote.trim() || null) !== (basket.note || null));
  const failSave = (e: unknown) => {
    const b = (e as ApiError).body as { detail?: string; status?: string } | undefined;
    setSaveErr(b?.detail || "We could not save the basket. Please try again.");
  };
  const saveNew = () => {
    setSaveErr("");
    const n = saveName.trim(); if (!n) { setSaveErr("Give the basket a name first."); return; }
    act.create.mutate({ name: n, query: text, note: saveNote.trim() || null, columns: cols, sort, recent }, {
      onSuccess: (r) => { loadedFor.current = r.basket.id; setParams({ basket: r.basket.id }, { replace: true }); toast(`Saved the basket “${r.basket.name}”.`); }, onError: failSave });
  };
  const update = () => {
    if (!basket) return; setSaveErr("");
    act.update.mutate({ id: basket.id, name: saveName.trim(), query: text, note: saveNote.trim() || null, columns: cols, sort, recent }, { onSuccess: (r) => toast(`Updated “${r.basket.name}”.`), onError: failSave });
  };
  const saveBlock = !valid ? (text.trim() ? "Fix the problems above before saving." : "Write a query first.") : nameBad;

  if (DEMO) return (
    <section className="pagehead"><div className="wrap"><div className="eyebrow">Formula screener</div><h1>The formula screener runs on the live site.</h1><p>It needs the server's data, so it is not part of this offline preview. The Screener works here.</p><Link className="btn primary" to="/screener">Open the screener</Link></div></section>
  );

  const underline = segments(text, problems);
  const colsToShow = res?.columns ?? [];
  const sortMark = (k: string) => (res?.sort.key === k ? (res.sort.dir === "asc" ? "▲" : "▼") : "▾");
  const total = res?.total ?? 0;
  const statusLine = !text.trim() ? "Type a query, or pick an example below."
    : netErr ? "We could not check the query just now. You can still run it."
    : checking || !val ? "Checking…"
    : errors.length ? `${errors.length} problem${errors.length > 1 ? "s" : ""} to fix${warnings.length ? `, ${warnings.length} thing${warnings.length > 1 ? "s" : ""} to look at` : ""}`
    : `Looks good: ${val.conditions} condition${val.conditions === 1 ? "" : "s"} using ${val.metrics.length} ratio${val.metrics.length === 1 ? "" : "s"}${warnings.length ? `. ${warnings.length} thing${warnings.length > 1 ? "s" : ""} to look at.` : "."}`;

  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><PageArt kind="research" />
        <div className="eyebrow">Formula screener</div><h1>Type the rule. Get the companies.</h1>
        <p>Write what you are looking for, like <code className="qb-inl">Market cap &gt; 500 AND P/E &lt; 15</code>. We check every word as you type, show you how we read it, and list the listed companies that match all of it. Prefer clicking? <a className="alx-link" href="/screener" onClick={(e) => { e.preventDefault(); nav("/screener"); }}>Use the Screener</a>.</p></div></section>

      <div className="wrap qb">
        <section className="card qb-ed" aria-label="Your query">
          <div className="qb-bar">
            <label htmlFor="qb-text" className="qb-lab">Your query</label>
            <div className="qb-bar-b">
              <button className={"btn" + (helper ? " on" : "")} aria-expanded={helper} aria-controls="qb-helper" onClick={() => setHelper(!helper)}>Add a condition</button>
              <button className="btn" onClick={() => openAll()}><Icon name="table" />Show all ratios</button>
            </div>
          </div>

          <div className="qb-box">
            <div className="qb-mirror" ref={mirrorRef} aria-hidden="true">{underline.map((s, i) => s.problem ? <mark key={i} className={"qb-m " + s.problem.severity}>{s.text}</mark> : <Fragment key={i}>{s.text}</Fragment>)}{"​"}</div>
            <textarea id="qb-text" ref={taRef} value={text} rows={4} spellCheck={false} autoCapitalize="off" autoCorrect="off" autoComplete="off" maxLength={rat.data?.limits.chars ?? 2000}
              placeholder={"Market cap > 500 Cr\nP/E < 15\nROCE > 22%"} aria-describedby="qb-status qb-problems" aria-invalid={errors.length > 0}
              onChange={(e) => { setText(e.target.value); setUndo(null); setClosed(false); setForce(false); setCaret(e.target.selectionStart); }}
              onKeyDown={onKey} onKeyUp={(e) => { if (!["ArrowDown", "ArrowUp", "Enter", "Tab", "Escape"].includes(e.key)) setCaret(e.currentTarget.selectionStart); }}
              onClick={(e) => setCaret(e.currentTarget.selectionStart)} onSelect={(e) => setCaret(e.currentTarget.selectionStart)} onScroll={syncScroll} onBlur={() => setTimeout(() => setForce(false), 150)} />
          </div>
          <div className="qb-meta"><span id="qb-status" role="status" aria-live="polite" className={errors.length ? "qb-err" : valid ? "qb-ok" : ""}>{valid && <Icon name="check" />}{statusLine}</span>
            <span className="qb-count">{text.length.toLocaleString("en-IN")} / {(rat.data?.limits.chars ?? 2000).toLocaleString("en-IN")}</span></div>

          {opts.length > 0 && <ul className="qb-sugg" role="listbox" aria-label={comp.kind === "metric" ? "Ratio suggestions" : comp.kind === "operator" ? "Comparison suggestions" : "Joiner suggestions"}>
            {opts.map((o, i) => <li key={o.label} role="option" aria-selected={i === hi}><button className={i === hi ? "on" : ""} onMouseDown={(e) => e.preventDefault()} onClick={() => accept(o)}><b>{o.label}</b><small>{o.sub}</small>{o.locked && <span className="qb-lk"><Icon name="lock" />{TIER[o.locked].n}</span>}</button></li>)}
            <li className="qb-hint" aria-hidden="true"><small>↑ ↓ to choose, Enter or Tab to add, Esc to close</small></li>
          </ul>}
          {!opts.length && text.trim() === "" && <p className="qb-tip">Tip: start typing a ratio name (like <i>roe</i> or <i>market cap</i>) and we suggest the rest. Put each condition on its own line, or join them with AND / OR.</p>}

          <div id="qb-problems">
            {problems.length > 0 && <ul className="qb-probs" aria-label="Problems with the query">
              {problems.map((p, i) => (
                <li key={p.code + p.start + i} className={"qb-p " + p.severity}>
                  <span className="qb-pi"><Icon name={p.severity === "error" ? "alert" : "info"} /></span>
                  <div>
                    <div className="qb-pw"><button className="lnk" onClick={() => jump(p)} aria-label={`Go to line ${p.line}, column ${p.col}`}>Line {p.line}, column {p.col}</button>{p.text && <code>{p.text}</code>}<span className="qb-kind">{p.severity === "error" ? "Needs fixing" : "Check this"}</span></div>
                    <p>{p.message}</p>
                    <div className="qb-fx">
                      {p.fixes.map((f) => <button key={f.label} className="qb-fix" onClick={() => useFix(f)}>{f.label}</button>)}
                      {p.seeAll && <button className="qb-fix ghost" onClick={() => openAll(p.name || "")}>See all ratios</button>}
                      {p.code === "plan_locked" && p.plan && <button className="qb-fix ghost" onClick={() => ask(p.plan!, p.message)}>See the {TIER[p.plan].n} plan</button>}
                    </div>
                  </div>
                </li>))}
            </ul>}
          </div>

          {valid && val?.reading && <details className="qb-reading" open={val.conditions <= 6}><summary>How we read your query</summary><ReadingTree r={val.reading} />
            {val.canonical && val.canonical !== text && <button className="alx-link" onClick={() => edit(val.canonical!)}>Write the ratio names out in full</button>}</details>}

          {undo != null && <p className="qb-undo">Your earlier query was replaced. <button className="lnk" onClick={() => { setText(undo); setUndo(null); }}>Undo</button></p>}

          <div className="qb-opts-row">
            {rat.data?.recentResults.available && <label className="qb-check"><input type="checkbox" checked={recent} onChange={(e) => setRecent(e.target.checked)} /><span>Show only recent results<small>Only companies that have reported the quarter ended {quarterLabel(rat.data.recentResults.quarterEnd)} ({nf(rat.data.recentResults.companies, 0)} so far)</small></span></label>}
            <div className="scr-cm"><button className="btn" aria-expanded={colMenu} onClick={() => setColMenu(!colMenu)}>Columns{cols.length ? ` · +${cols.length}` : ""}</button>
              {colMenu && <div className="qb-colmenu card" role="dialog" aria-label="Add result columns"><p className="qb-sub">The table always shows market cap, price and the ratios in your query. Add more:</p>
                <RatioPicker ratios={ratios.filter((r) => !r.locked && !cols.includes(r.key))} onPick={(r) => { if (cols.length < 12) setCols([...cols, r.key]); else toast("You can add up to 12 extra columns."); }} placeholder="Search a column to add" label="Search columns" />
                <div className="qb-chips">{cols.map((k) => <button key={k} className="fchip" onClick={() => setCols(cols.filter((c) => c !== k))} aria-label={`Remove the ${byKey.get(k)?.label ?? k} column`}>{byKey.get(k)?.label ?? k}<span aria-hidden="true"> ✕</span></button>)}</div>
                <button className="alx-link" onClick={() => setColMenu(false)}>Done</button></div>}</div>
            <button className="btn primary qb-run" onClick={() => run(0)} disabled={running || !text.trim() || (!!val && !val.ok && !checking)} title={errors.length ? "Fix the problems first" : "Ctrl or Cmd + Enter"}>{running ? "Running…" : "Run this query"}</button>
          </div>
          {runErr && <p className="qb-err" role="alert">{runErr}</p>}
        </section>

        {helper && rat.data && <div id="qb-helper"><ConditionHelper ratios={ratios} hasText={!!text.trim()} onAdd={addLine} /></div>}

        <section className="qb-examples" aria-label="Examples">
          <div className="label">Start from an example</div>
          <div className="qb-chips">{(rat.data?.examples ?? []).map((x) => <button key={x.id} className="qb-ex" onClick={() => loadExample(x.query)} title={x.about}><b>{x.title}</b><small>{x.about}</small>{x.locked && <span className="qb-lk"><Icon name="lock" />{TIER[x.plan].n}</span>}</button>)}
            {rat.isLoading && <div className="skeleton" style={{ height: 64, width: "100%" }} />}
            {rat.isError && <p className="qb-err">The list of ratios did not load. <button className="lnk" onClick={() => rat.refetch()}>Try again</button></p>}</div>
        </section>

        <section className="card qb-save" aria-label="Save as a basket">
          <h3>Keep this query as a basket</h3>
          {!user ? <p>Baskets are saved to your account so you can come back to them. <Link className="alx-link" to="/login">Sign in</Link> or <Link className="alx-link" to="/login">create a free account</Link> to keep up to 3.</p> : <>
            <div className="qb-saveform">
              <label>Name<input value={saveName} maxLength={80} onChange={(e) => setSaveName(e.target.value)} placeholder="e.g. Cheap and profitable" aria-invalid={!!nameBad} /></label>
              <label>Note (optional)<input value={saveNote} maxLength={300} onChange={(e) => setSaveNote(e.target.value)} placeholder="Why you made it" /></label>
              <div className="qb-saveb">
                {basket ? <><button className="btn primary" onClick={update} disabled={!!saveBlock || act.update.isPending || !dirty}>{dirty ? `Update “${basket.name}”` : "Saved"}</button>
                  <button className="btn" onClick={() => { loadedFor.current = null; setParams({}, { replace: true }); setSaveName(saveName + " copy"); }} title="Start a new basket from this query">Save as new</button></>
                  : <button className="btn primary" onClick={saveNew} disabled={!!saveBlock || act.create.isPending}>Save as basket</button>}
                <Link className="btn" to="/baskets">My baskets{baskets.data ? ` · ${baskets.data.baskets.length}/${baskets.data.max}` : ""}</Link>
              </div>
            </div>
            {(saveBlock && (saveName.trim() || text.trim())) ? <p className="qb-sub" aria-live="polite">{saveBlock}</p> : null}
            {saveErr && <p className="qb-err" role="alert">{saveErr}</p>}
            {basket && dirty && <p className="qb-sub">You have changes that are not saved yet.</p>}
          </>}
        </section>

        {(bad || res) && <section className="card qb-res" aria-label="Results">
          {bad && <div className="state"><h2>The query needs fixing first</h2>{bad.errors.map((e, i) => <p key={i}>{e.message}</p>)}</div>}
          {res && <>
            <div className="scr-top">
              <div aria-live="polite"><b className="scr-count">{nf(total, 0)}</b> <span className="muted">of {nf(res.universe, 0)} listed stocks match · {res.took} ms</span></div>
              <div className="scr-tools"><button className="btn" onClick={exportCsv}><Icon name="table" />Download CSV</button></div>
            </div>
            {stale && <p className="qb-stale" role="status">You changed the query after this was run. <button className="lnk" onClick={() => run(0)}>Run it again</button></p>}
            {res.warnings.length > 0 && <ul className="qb-probs">{res.warnings.map((p, i) => <li key={i} className="qb-p warning"><span className="qb-pi"><Icon name="info" /></span><div><p>{p.message}</p></div></li>)}</ul>}
            {res.recent && <p className="qb-sub">Only companies that reported the quarter ended {quarterLabel(res.recent.quarterEnd)} are included. {nf(res.recent.dropped, 0)} other match{res.recent.dropped === 1 ? "" : "es"} left out because that quarter's results are not in yet.</p>}
            <HScroll className={"scr-tw" + (running ? " is-busy" : "")} label="query results table"><table className="scr-t">
              <thead><tr><th className="stick"><button onClick={() => sortBy("name")}>Company {sortMark("name")}</button></th>
                {colsToShow.map((k) => { const m = byKey.get(k); return <th key={k}><button onClick={() => sortBy(k)} title={m?.definition} aria-label={`Sort by ${m?.label ?? k}`}>{m?.label ?? k} {sortMark(k)}</button></th>; })}</tr></thead>
              <tbody>{res.rows.map((r) => (
                <tr key={r.symbol} tabIndex={0} onClick={() => nav(`/stocks/${r.symbol}`)} onKeyDown={(e) => e.key === "Enter" && nav(`/stocks/${r.symbol}`)}>
                  <td className="stick"><span className="co"><span className="av mini" aria-hidden="true">{(r.name || r.symbol).slice(0, 2).toUpperCase()}</span><span><b>{r.symbol}</b><small>{r.name}{r.cap ? ` · ${r.cap}` : ""}</small></span></span></td>
                  {colsToShow.map((k) => { const m = byKey.get(k); return <td key={k}>{m ? fmtMetric(m, r.v[k]) : "—"}</td>; })}
                </tr>))}
                {!res.rows.length && <tr><td colSpan={colsToShow.length + 1} className="empty">No company matches every part of this query. Loosen one of the numbers, or switch an AND to an OR.</td></tr>}
              </tbody></table></HScroll>
            {res.capped ? (
              <div className="pl-cap"><Icon name="lock" /><span><b>Showing the first {res.limit} of {nf(total, 0)} matches.</b> Silver shows every match and lets you download them.</span>
                <button className="btn primary" onClick={() => ask("silver", "See every match with Silver.")}>Unlock with Silver</button></div>
            ) : total > PAGE && (
              <div className="pm-pager"><span>{page * PAGE + 1}–{Math.min(total, page * PAGE + PAGE)} of {nf(total, 0)}</span>
                <button className="btn" disabled={page === 0 || running} onClick={() => run((page - 1) * PAGE)}>Previous</button><button className="btn" disabled={(page + 1) * PAGE >= total || running} onClick={() => run((page + 1) * PAGE)}>Next</button></div>)}
            <details className="qb-left" open={res.leftOut.total > 0}>
              <summary>{res.leftOut.total > 0 ? `${nf(res.leftOut.total, 0)} companies were left out because a figure is missing` : "Every company had the figures this query needs"}</summary>
              <p className="qb-sub">A company with no value for a ratio never matches a condition on it, and is never guessed. {nf(res.withReport, 0)} of {nf(res.universe, 0)} listed companies have a full report loaded; the rest have only price and market cap.</p>
              {leftOutLines(res.leftOut.metrics, res.universe).length > 0 && <ul>{leftOutLines(res.leftOut.metrics, res.universe).map((l) => <li key={l}>{l}</li>)}</ul>}
              {res.leftOut.divisionByZero > 0 && <p className="qb-sub">{nf(res.leftOut.divisionByZero, 0)} {res.leftOut.divisionByZero === 1 ? "company was" : "companies were"} left out because the query divides by zero for {res.leftOut.divisionByZero === 1 ? "it" : "them"}.</p>}
            </details>
          </>}
          <Plain>The table lists companies that meet your rules. It does not say what to buy or sell. Open a company's report to see why a number looks the way it does. Figures are as of the last data refresh. General information, not investment advice.</Plain>
        </section>}

        <div className="qb-foot faint"><Icon name="info" /> {rat.data ? `${nf(rat.data.ratios.length, 0)} ratios, ${nf(rat.data.aliases, 0)} accepted names. ` : ""}Ratios we do not calculate give an error instead of being ignored. Your baskets live under <Link to="/baskets" className="alx-link">My baskets</Link>.</div>
      </div>

      <RatioDrawer ratios={ratios} open={drawer} onClose={() => setDrawer(false)} seed={seed} ask={ask} onInsert={insertName} onAdd={(r) => addLine(r.example)} />
    </>
  );
}

