import { useFocusTrap } from "../lib/focusTrap";
import { DEMO } from "../lib/demo";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { Icon } from "../lib/icons";
import { useAuth } from "../lib/auth";
import { useUI } from "../lib/ui";
import { useSearchIndex, type SearchRow } from "../lib/api";
import { useUniverse } from "../lib/screener";
import { askBrowserPermission, browserPermission, useAlerts, useCurrentValue, type Channel, type Created } from "../lib/alerts";
import { GROUPS, LIVE_NOTE, METRICS, OP_LABEL, describe, fixedTarget, fmtValue, isEvent, type Op } from "../lib/alertCatalog";

/** Search any listed company by name or ticker and pick one. */
export function StockPicker({ value, onChange, id }: { value: string; onChange: (symbol: string, name?: string) => void; id?: string }) {
  const [q, setQ] = useState(value), [open, setOpen] = useState(false), [sel, setSel] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const { data } = useSearchIndex(true);
  useEffect(() => setQ(value), [value]);
  useEffect(() => { const h = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); }; document.addEventListener("mousedown", h); return () => document.removeEventListener("mousedown", h); }, []);
  const hits = useMemo<SearchRow[]>(() => {
    const s = q.trim().toUpperCase(); if (!s || s === value) return [];
    const rows = data?.rows || [];
    const rank = (r: SearchRow) => (r[0] === s ? 0 : r[0].startsWith(s) ? 1 : r[1].toUpperCase().startsWith(s) ? 2 : 3);
    return rows.filter((r) => r[0].includes(s) || r[1].toUpperCase().includes(s)).sort((a, b) => rank(a) - rank(b) || b[3] - a[3]).slice(0, 7);
  }, [q, data, value]);
  const pick = (r: SearchRow) => { onChange(r[0], r[1]); setQ(r[0]); setOpen(false); };
  return (
    <div className="alx-pick" ref={box}>
      <span className="alx-pi"><Icon name="search" /></span>
      <input id={id} value={q} placeholder="Search a company or ticker" autoComplete="off" role="combobox" aria-expanded={open && hits.length > 0} aria-controls={(id || "alx-st") + "-l"} aria-autocomplete="list"
        onChange={(e) => { setQ(e.target.value); setOpen(true); setSel(0); if (value) onChange(""); }} onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, hits.length - 1)); }
          if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
          if (e.key === "Enter" && open && hits[sel]) { e.preventDefault(); pick(hits[sel]); }
          if (e.key === "Escape") setOpen(false);
        }} />
      {open && hits.length > 0 && (
        <ul id={(id || "alx-st") + "-l"} className="alx-dd" role="listbox">
          {hits.map((r, i) => <li key={r[0]} role="option" aria-selected={i === sel}><button type="button" className={i === sel ? "on" : ""} onMouseEnter={() => setSel(i)} onClick={() => pick(r)}><b>{r[0]}</b><small>{r[1]}</small></button></li>)}
        </ul>
      )}
    </div>
  );
}

export type Preset = Partial<{ symbol: string; metric: string; op: Op; value: number; keyword: string }>;
const num = (s: string) => (s.trim() === "" || isNaN(Number(s)) ? null : Number(s));

export function AlertComposer({ preset, onDone, compact }: { preset?: Preset; onDone?: (a: Created) => void; compact?: boolean }) {
  const { user } = useAuth();
  const { plan, toast, upgrade } = useUI();
  const { data: uni } = useUniverse(DEMO);   // the company list is only needed by the demo (no server to ask)
  const rows = uni?.rows;
  const { create, alerts, limit } = useAlerts(rows);
  const [symbol, setSymbol] = useState(preset?.symbol || "");
  const [metric, setMetric] = useState(preset?.metric || "price");
  const [op, setOp] = useState<Op>(preset?.op || "above");
  const [val, setVal] = useState(preset?.value != null ? String(preset.value) : "");
  const [kw, setKw] = useState(preset?.keyword || "");
  const [ch, setCh] = useState<Channel[]>(["app", "email"]);
  const [repeat, setRepeat] = useState<"once" | "every">("once");
  const [note, setNote] = useState("");
  const [touched, setTouched] = useState(preset?.value != null);
  const [made, setMade] = useState<Created | null>(null);
  const [err, setErr] = useState<{ status?: string; detail: string; plan?: string } | null>(null);
  const m = METRICS[metric];
  const locked = m.tier === "silver" && plan === "basic";
  const used = alerts.filter((a) => a.status !== "done").length;
  const current = useCurrentValue(symbol, metric, rows);

  // a new preset (a quick-alert tile, or "Set alert" from a stock page) replaces the form
  const key = JSON.stringify(preset || {});
  const first = useRef(key);
  useEffect(() => {
    if (first.current === key) return; first.current = key;
    setSymbol(preset?.symbol || symbol); setMetric(preset?.metric || "price"); setOp(preset?.op || METRICS[preset?.metric || "price"].ops[0]); setVal(preset?.value != null ? String(preset.value) : ""); setKw(preset?.keyword || ""); setTouched(preset?.value != null); setMade(null); setErr(null);
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  const pickMetric = (k: string) => { setMetric(k); setOp(METRICS[k].ops[0]); setTouched(false); setVal(""); setMade(null); setErr(null); };
  // suggest a sensible target until the member types their own
  useEffect(() => {
    if (touched || isEvent(metric) && metric !== "result_soon") return;
    if (metric === "price") { if (current != null) setVal(String(Math.round(current * (op === "above" ? 1.05 : 0.95) * 100) / 100)); }
    else setVal(String(m.sample * (metric === "rsi14" && op === "above" ? 70 / 30 : 1)));
  }, [metric, op, current, touched]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggle = async (c: Channel) => {
    if (c === "app") return;
    if (ch.includes(c)) { setCh(ch.filter((x) => x !== c)); return; }
    if (c === "browser") {
      const p = browserPermission();
      if (p === "unsupported") { toast("This browser cannot show notifications. In-app and email alerts still work."); return; }
      if (p === "denied") { toast("Notifications are blocked for this site. Allow them in the browser's site settings, then try again."); return; }
      if (p === "default" && (await askBrowserPermission()) !== "granted") { toast("Browser notifications were not allowed."); return; }
    }
    setCh([...ch, c]);
  };

  const fixed = fixedTarget(metric, op);
  const v = fixed ?? (isEvent(metric) ? (metric === "result_soon" ? num(val) : null) : num(val));
  const ready = !!symbol && !locked && (metric === "news_keyword" ? kw.trim().length >= 2 : metric === "new_filing" ? true : v != null);
  const sentence = symbol && ready ? `${symbol}: ${describe({ metric, op, value: v, keyword: kw.trim().toLowerCase() })}` : null;

  const submit = (e: React.FormEvent) => {
    e.preventDefault(); if (!ready || create.isPending) return;
    setErr(null);
    if (!user) { upgrade("basic", "Alerts need a free account."); return; }
    create.mutate({ symbol, metric, op, value: v, keyword: metric === "news_keyword" ? kw.trim() : undefined, channels: ch, repeat: isEvent(metric) ? repeat : repeat, note: note.trim() || undefined }, {
      onSuccess: (a) => { setMade(a); toast(`Alert created for ${symbol}.`); onDone?.(a); },
      onError: (x: unknown) => { const b = (x as { body?: { status?: string; detail?: string; plan?: string } })?.body; setErr({ status: b?.status, detail: b?.detail || "The alert could not be saved. Please try again.", plan: b?.plan }); },
    });
  };

  return (
    <form className={"alx-form" + (compact ? " is-compact" : "")} onSubmit={submit} noValidate>
      <div className="alx-row">
        <label htmlFor="alx-stock">Stock</label>
        <StockPicker id="alx-stock" value={symbol} onChange={(s) => { setSymbol(s); setMade(null); }} />
      </div>
      <div className="alx-2">
        <div className="alx-row">
          <label htmlFor="alx-metric">Metric</label>
          <select id="alx-metric" value={metric} onChange={(e) => pickMetric(e.target.value)}>
            {GROUPS.map((g) => (
              <optgroup key={g} label={g}>
                {Object.entries(METRICS).filter(([, x]) => x.group === g).map(([k, x]) => <option key={k} value={k}>{x.label}{x.tier === "silver" && plan === "basic" ? " · Silver" : ""}</option>)}
              </optgroup>
            ))}
          </select>
        </div>
        <div className="alx-row">
          <label htmlFor="alx-op">Condition</label>
          <select id="alx-op" value={op} onChange={(e) => { setOp(e.target.value as Op); setTouched(false); }} disabled={m.ops.length === 1}>
            {m.ops.map((o) => <option key={o} value={o}>{OP_LABEL(metric, o)}</option>)}
          </select>
        </div>
      </div>
      <p className="alx-hint">{m.hint}</p>

      {metric === "news_keyword" && (
        <div className="alx-row"><label htmlFor="alx-kw">Word or phrase</label><input id="alx-kw" value={kw} maxLength={40} placeholder={m.text} onChange={(e) => setKw(e.target.value)} /></div>
      )}
      {fixed != null && symbol && <p className="alx-cur">{current != null ? <>Currently <b>{fmtValue(metric, current)}</b></> : "The day's price band is not available for this stock right now, so this alert cannot fire until it is."}</p>}
      {fixed == null && (!isEvent(metric) || metric === "result_soon") ? (
        <div className="alx-row">
          <label htmlFor="alx-val">{metric === "result_soon" ? "Days ahead" : "Target value"}{m.unit && m.unit !== "days" ? <> <span className="alx-u">({m.unit === "₹" ? "₹" : m.unit})</span></> : null}</label>
          <div className="alx-val">
            {m.unit === "₹" && <span className="alx-pre">₹</span>}
            <input id="alx-val" inputMode="decimal" value={val} placeholder={m.unit === "Cr" ? "e.g. 5,000" : "e.g. 30"} onChange={(e) => { setVal(e.target.value.replace(/[^0-9.\-]/g, "")); setTouched(true); }} />
            {m.unit && m.unit !== "₹" && <span className="alx-suf">{m.unit}</span>}
          </div>
          {symbol && !isEvent(metric) && <small className="alx-cur">{current != null ? <>Currently <b>{fmtValue(metric, current)}</b></> : "Current value is not available for this stock."}</small>}
        </div>
      ) : null}

      <fieldset className="alx-notify">
        <legend>Notify via</legend>
        <label className="alx-ck is-on is-fixed"><input type="checkbox" checked readOnly disabled /><span><Icon name="bell" />In-app</span></label>
        <label className={"alx-ck" + (ch.includes("email") ? " is-on" : "")}><input type="checkbox" checked={ch.includes("email")} onChange={() => toggle("email")} /><span><Icon name="mail" />Email</span></label>
        <label className={"alx-ck" + (ch.includes("browser") ? " is-on" : "")}><input type="checkbox" checked={ch.includes("browser")} onChange={() => toggle("browser")} /><span><Icon name="activity" />Browser</span></label>
        <label className="alx-ck is-soon" title="Coming with the FinLit app"><input type="checkbox" disabled /><span><Icon name="panel" />Mobile app<em>Soon</em></span></label>
      </fieldset>

      <div className="alx-2">
        <div className="alx-row">
          <label htmlFor="alx-rep">How often</label>
          <select id="alx-rep" value={repeat} onChange={(e) => setRepeat(e.target.value as "once" | "every")}>
            <option value="once">Tell me once</option>
            <option value="every">{isEvent(metric) ? "Every time something new appears" : "Every time it crosses"}</option>
          </select>
        </div>
        <div className="alx-row"><label htmlFor="alx-note">Note to self <span className="alx-u">(optional)</span></label><input id="alx-note" value={note} maxLength={140} placeholder="e.g. Add to my portfolio" onChange={(e) => setNote(e.target.value)} /></div>
      </div>

      {sentence && <p className="alx-sentence" role="status"><Icon name="check" /><span>You will be told when <b>{sentence}</b></span></p>}
      <p className="alx-live"><Icon name="activity" /><span>{m.live ? "Checked every few minutes while the market is open." : "Checked on weekday evenings, once the day's data is in."} Anything that fires lands in your notifications.</span></p>

      {locked && <div className="alx-warn" role="alert"><b>{m.label} alerts are part of Silver.</b> <button type="button" className="alx-link" onClick={() => upgrade("silver", `${m.label} alerts are part of Silver.`)}>See Silver</button></div>}
      {err && <div className="alx-warn" role="alert">{err.detail} {(err.status === "plan_required" || err.status === "plan_limit") && <button type="button" className="alx-link" onClick={() => upgrade((err.plan as "silver" | "gold") || "silver", err.detail)}>See plans</button>}</div>}
      {made && <div className="alx-ok" role="status"><b>Alert saved.</b> {made.alreadyMet ? <>It is already true right now ({fmtValue(made.metric, made.current)}), so you will hear when it next crosses.</> : "We will tell you when it fires."} <Link to="/alerts">View my alerts</Link></div>}

      <div className="alx-foot">
        <button className="btn primary" type="submit" disabled={!ready || create.isPending}><Icon name="bell" /><span>{create.isPending ? "Saving…" : "Create alert"}</span></button>
        <span className="alx-count">{used} of {limit} alerts used</span>
      </div>
      <p className="alx-fine">{LIVE_NOTE}</p>
    </form>
  );
}

/** Dialog form used from stock pages and lists, so an alert is one click away wherever a company appears. */
export function AlertModal({ open, onClose, preset }: { open: boolean; onClose: () => void; preset?: Preset }) {
  const ref = useRef<HTMLDivElement>(null);
  useFocusTrap(ref, open);
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    addEventListener("keydown", k); const t = setTimeout(() => ref.current?.querySelector<HTMLElement>("select, input")?.focus(), 40);
    const prev = document.body.style.overflow; document.body.style.overflow = "hidden";
    return () => { removeEventListener("keydown", k); clearTimeout(t); document.body.style.overflow = prev; };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <>
      <div className="scrim" onClick={onClose} />
      <div className="alx-modal" role="dialog" aria-modal="true" aria-label="Create a new alert" ref={ref}>
        <div className="alx-mh"><h2><Icon name="bell" />Create new alert</h2><button className="alx-x" onClick={onClose} aria-label="Close">✕</button></div>
        <AlertComposer preset={preset} compact onDone={() => setTimeout(onClose, 1600)} />
      </div>
    </>
  );
}

/** A small bell button that opens the form for one company. */
export function AlertButton({ symbol, className, label }: { symbol: string; className?: string; label?: string }) {
  const [open, setOpen] = useState(false);
  const { user } = useAuth();
  const { upgrade } = useUI();
  return (
    <>
      <button className={className || "alx-bell"} onClick={() => (user ? setOpen(true) : upgrade("basic", "Alerts need a free account."))} aria-label={`Create an alert for ${symbol}`} title="Create an alert">
        <Icon name="bell" />{label && <span>{label}</span>}
      </button>
      <AlertModal open={open} onClose={() => setOpen(false)} preset={{ symbol }} />
    </>
  );
}
