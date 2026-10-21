import { useEffect, useMemo, useState } from "react";
import { Icon } from "../lib/icons";
import { HScroll } from "./HScroll";
import { useUI } from "../lib/ui";
import { MINUS } from "../lib/format";
import { fmtMetric, useCatalog, type MetricInfo } from "../lib/proscreen";
import { searchMetrics } from "../lib/metricSearch";
import { useCompareMetrics } from "../lib/compareApi";
import { DEFAULT_KEYS, MAX_PICK, MAX_PICK_PHONE, NAME_MAX, STARTERS, bestWorst, cleanKeys, useSavedSets, useSetsSync } from "../lib/compareSets";
import "../styles/compare.css";

type Flat = MetricInfo & { group: string; groupLabel: string };
const UNIT_NAME: Record<string, string> = { Cr: "₹ crore", Rs: "₹", "%": "percent", x: "times (×)", d: "days", n: "count", pts: "points", flag: "yes / no" };
const DIRECTION = { higher: "Higher is better", lower: "Lower is better", none: "No better or worse" } as const;

const usePhone = () => {
  const q = "(max-width: 640px)";
  const [on, setOn] = useState(() => typeof matchMedia !== "undefined" && matchMedia(q).matches);
  useEffect(() => { if (typeof matchMedia === "undefined") return; const m = matchMedia(q); const f = () => setOn(m.matches); m.addEventListener("change", f); return () => m.removeEventListener("change", f); }, []);
  return on;
};

/** "Build your own": every measure the screener offers, a searchable grouped picker, saved sets, and a table with best and weakest marked. */
export function CompareCustom({ companies, keysParam, onKeys }: { companies: { symbol: string; name: string }[]; keysParam: string[] | null; onKeys: (k: string[]) => void }) {
  const { toast, upgrade } = useUI();
  const cat = useCatalog();
  const phone = usePhone();
  const cap = phone ? MAX_PICK_PHONE : MAX_PICK;
  const mine = useSavedSets();
  const sync = useSetsSync();
  const [q, setQ] = useState(""), [open, setOpen] = useState(true), [name, setName] = useState("");

  const flat = useMemo<Flat[]>(() => (cat.data?.groups || []).flatMap((g) => g.metrics.map((m) => ({ ...m, group: g.id, groupLabel: g.label }))), [cat.data]);
  const byKey = useMemo(() => new Map(flat.map((m) => [m.key, m])), [flat]);
  const known = (k: string) => byKey.has(k);
  const free = (k: string) => byKey.has(k) && !byKey.get(k)!.locked;

  // what the link asks for, or the sensible default; measures the plan does not include are set aside, not requested
  const asked = useMemo(() => (keysParam ?? DEFAULT_KEYS).filter(known), [keysParam, byKey]);   // eslint-disable-line react-hooks/exhaustive-deps
  const keys = useMemo(() => asked.filter(free).slice(0, cap), [asked, byKey, cap]);                                // eslint-disable-line react-hooks/exhaustive-deps
  const heldBack = asked.filter((k) => !free(k)).length;
  const set = (next: string[]) => onKeys(cleanKeys(next, known, 200));

  const shown = useMemo(() => {
    const hits = new Set(searchMetrics(flat, q).map((m) => m.key));
    const ranked = q.trim() ? searchMetrics(flat, q) : flat;
    return (cat.data?.groups || []).map((g) => ({ g, items: ranked.filter((m) => m.group === g.id && hits.has(m.key)) })).filter((x) => x.items.length);
  }, [flat, q, cat.data]);
  const nShown = shown.reduce((n, x) => n + x.items.length, 0);

  const toggle = (m: Flat) => {
    if (m.locked) { upgrade(m.tier, `${m.label} is part of the ${m.tier === "gold" ? "Gold" : "Silver"} plan.`); return; }
    if (keys.includes(m.key)) { set(keys.filter((k) => k !== m.key)); return; }
    if (keys.length >= cap) { toast(`You can compare up to ${cap} measures at a time${phone ? " on a phone" : ""}. Remove one first.`); return; }
    set([...keys, m.key]);
  };
  const addGroup = (items: Flat[]) => {
    const add = items.filter((m) => !m.locked && !keys.includes(m.key)).map((m) => m.key);
    const room = cap - keys.length;
    if (add.length > room) toast(`Added ${Math.max(room, 0)} of ${add.length}: the limit is ${cap} measures at a time${phone ? " on a phone" : ""}.`);
    set([...keys, ...add.slice(0, Math.max(room, 0))]);
  };
  const lockedIn = (items: Flat[]) => items.filter((m) => m.locked).length;

  const load = (ks: string[]) => { const ok = ks.filter(free); if (ok.length < ks.length) toast(`${ks.length - ok.length} measure${ks.length - ok.length > 1 ? "s" : ""} in that set need a higher plan and were left out.`); set(ok.slice(0, cap)); };
  const saveSet = () => {
    const n = name.trim();
    if (!n) { toast("Give the set a name first."); return; }
    if (!keys.length) { toast("Pick at least one measure to save."); return; }
    sync.save(n, keys); setName(""); toast(`Saved “${n}” in ${sync.where}.`);
  };
  const share = () => navigator.clipboard?.writeText(location.href).then(() => toast("Link to this comparison copied."), () => toast(location.href));

  const symbols = companies.map((c) => c.symbol);
  const res = useCompareMetrics(symbols, keys, symbols.length >= 2 && !!cat.data);
  const metrics = res.data?.metrics || [];
  const groupsOut = useMemo(() => {
    const order = (cat.data?.groups || []).map((g) => g.id);
    const m = new Map<string, typeof metrics>();
    metrics.forEach((x) => m.set(x.group, [...(m.get(x.group) || []), x]));
    return order.filter((id) => m.has(id)).map((id) => ({ id, label: m.get(id)![0].groupLabel, items: m.get(id)! }));
  }, [metrics, cat.data]);

  if (cat.isLoading) return <div className="skeleton" style={{ height: 160, margin: 16 }} />;
  if (cat.isError || !cat.data) return <p className="muted cx-pad">Custom comparison needs the live FinLit service and is not available right now. Please try again in a moment.</p>;

  return (
    <div className="cx">
      <div className="cx-sets">
        <label className="cx-sel"><span className="label">Start from a set</span>
          <select value="" onChange={(e) => { const v = e.target.value; if (!v) return; const s = [...STARTERS, ...mine].find((x) => x.name === v); if (s) load(s.keys); }} aria-label="Load a saved or ready-made set of measures">
            <option value="">Choose…</option>
            <optgroup label="Ready-made">{STARTERS.map((s) => <option key={"s" + s.name} value={s.name}>{s.name} ({s.keys.length})</option>)}</optgroup>
            {mine.length > 0 && <optgroup label="Your sets">{mine.map((s) => <option key={"m" + s.name} value={s.name}>{s.name} ({s.keys.length})</option>)}</optgroup>}
          </select></label>
        <form className="cx-save" onSubmit={(e) => { e.preventDefault(); saveSet(); }}>
          <label><span className="label">Save these {keys.length} as</span><input value={name} maxLength={NAME_MAX} onChange={(e) => setName(e.target.value)} placeholder="Name your set" /></label>
          <button className="btn" type="submit">Save set</button>
        </form>
        <button className="btn cx-share" type="button" onClick={share}><Icon name="spark" />Copy link</button>
      </div>
      {mine.length > 0 && <div className="cx-mine" aria-label="Your saved sets">{mine.map((s) => (
        <span className="cx-chip" key={s.name}><button type="button" onClick={() => load(s.keys)} title={`Load ${s.keys.length} measures`}>{s.name}</button>
          <button type="button" className="x" aria-label={`Delete the set ${s.name}`} onClick={() => sync.remove(s.name)}>×</button></span>))}</div>}
      <p className="cx-note">Sets are kept in {sync.where}.{sync.where === "this browser" ? " Silver and Gold members also keep them on their account." : ""}</p>

      <div className="cx-pick">
        <div className="cx-pick-h">
          <b>Choose measures</b><span className="cx-count" aria-live="polite">{keys.length} of {cap} chosen</span>
          <button className="cx-lnk" type="button" onClick={() => set(DEFAULT_KEYS.filter(free).slice(0, cap))}>Reset to default</button>
          <button className="cx-lnk" type="button" onClick={() => set([])} disabled={!keys.length}>Clear all</button>
          <button className="cx-lnk" type="button" aria-expanded={open} onClick={() => setOpen((o) => !o)}>{open ? "Hide list" : "Show list"}</button>
        </div>
        {heldBack > 0 && <p className="cx-note warn" role="note"><Icon name="lock" /> {heldBack} measure{heldBack > 1 ? "s" : ""} in this link {heldBack > 1 ? "are" : "is"} not in your plan and {heldBack > 1 ? "are" : "is"} left out.</p>}
        {asked.length > keys.length + heldBack && <p className="cx-note warn" role="note">Showing the first {cap} measures; the link has more.</p>}
        {open && (
          <>
            <label className="cx-search"><span className="sr">Search measures</span><Icon name="search" />
              <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Search ${flat.length} measures: try EV / CFO, margin, debt…`} autoComplete="off" spellCheck={false} /></label>
            <p className="cx-note" aria-live="polite">{q.trim() ? `${nShown} match${nShown === 1 ? "" : "es"}` : `${flat.length} measures in ${cat.data.groups.length} groups`}</p>
            <div className="cx-list">
              {shown.map(({ g, items }) => { const on = items.filter((m) => keys.includes(m.key)).length, free_ = items.length - lockedIn(items);
                return (
                  <section key={g.id} className="cx-g" aria-label={g.label}>
                    <header><h4>{g.label}</h4><span>{on}/{items.length}{q.trim() ? " shown" : ""}</span>
                      <button className="cx-lnk" type="button" disabled={!free_ || on === free_} onClick={() => addGroup(items)}>{q.trim() ? "Select all shown" : "Select all"}</button>
                      <button className="cx-lnk" type="button" disabled={!on} onClick={() => set(keys.filter((k) => !items.some((m) => m.key === k)))}>Clear</button></header>
                    <ul>{items.map((m) => { const on_ = keys.includes(m.key); return (
                      <li key={m.key}>
                        <label className={"cx-m" + (on_ ? " on" : "") + (m.locked ? " locked" : "")}>
                          <input type="checkbox" checked={on_} onChange={() => toggle(m)} aria-describedby={"cxh-" + m.key} />
                          <span className="cx-mt"><b>{m.label}</b><small id={"cxh-" + m.key}>{m.say}</small></span>
                          <span className="cx-u">{m.locked ? <><Icon name="lock" />{m.tier === "gold" ? "Gold" : "Silver"}</> : (UNIT_NAME[m.unit] || m.unit)}</span>
                        </label>
                      </li>); })}</ul>
                  </section>); })}
              {!shown.length && <p className="muted cx-pad">No measure matches “{q}”. Try fewer letters, or a word like margin, debt, growth or cash.</p>}
            </div>
          </>)}
        {!open && keys.length > 0 && <div className="cx-sel-chips">{keys.map((k) => <span className="cx-chip" key={k}><span>{byKey.get(k)?.label}</span><button type="button" className="x" aria-label={`Remove ${byKey.get(k)?.label}`} onClick={() => set(keys.filter((x) => x !== k))}>×</button></span>)}</div>}
      </div>

      {!keys.length ? <p className="muted cx-pad">Pick at least one measure above to see the comparison.</p>
        : symbols.length < 2 ? <p className="muted cx-pad">Pick at least two companies to compare.</p>
        : res.isError ? <p className="muted cx-pad" role="alert">{res.error.status === 403 ? (res.error.body.detail || "Your plan does not include one of these measures.") : "The comparison could not be loaded. Please try again in a moment."}</p>
        : !res.data ? <div className="skeleton" style={{ height: 220, margin: 16 }} />
        : (
          <>
            <p className="cx-legend"><span className="cx-tag best">Best</span> and <span className="cx-tag worst">Weakest</span> follow each measure's direction: lower is better for P/E and debt, higher for returns and growth. Measures with no better or worse are not marked. <b>{MINUS}</b> shows where no figure exists, with the reason.</p>
            <HScroll className="cx-scroll" label="comparison table">
              <table className="cx-t" style={{ "--n": symbols.length } as React.CSSProperties}>
                <caption className="sr">Comparison of {symbols.join(", ")} on {metrics.length} measures</caption>
                <thead><tr><th scope="col">Measure</th>{res.data.companies.map((c, i) => <th scope="col" key={c.symbol} className={"k" + i}><i className={"mk k" + i} /><b>{c.symbol}</b><small>{c.name !== c.symbol ? c.name : ""}</small></th>)}</tr></thead>
                {groupsOut.map((g) => (
                  <tbody key={g.id}>
                    <tr className="cx-gr"><th scope="colgroup" colSpan={symbols.length + 1}>{g.label}</th></tr>
                    {g.items.map((m) => { const cells = res.data!.values[m.key] || {}, mk = bestWorst(Object.fromEntries(symbols.map((s) => [s, cells[s]?.v ?? null])), m.better);
                      return (
                        <tr key={m.key}>
                          <th scope="row"><b>{m.label}</b><small>{UNIT_NAME[m.unit] || m.unit} · {DIRECTION[m.better]}</small></th>
                          {symbols.map((s) => { const c = cells[s], v = c?.v ?? null, best = mk.best.includes(s), worst = mk.worst.includes(s);
                            return (
                              <td key={s} className={best ? "best" : worst ? "worst" : ""}>
                                {v == null ? <><span className="cx-na" aria-label={"No figure. " + (c?.why || "Not available")}>{MINUS}</span><small>{c?.why || "Not available"}</small></>
                                  : <><b>{fmtMetric({ key: m.key, unit: m.unit, digits: m.digits }, v)}</b>{best && <span className="cx-tag best">Best</span>}{worst && <span className="cx-tag worst">Weakest</span>}</>}
                              </td>); })}
                        </tr>); })}
                  </tbody>))}
              </table>
            </HScroll>
            <p className="faint cmp-foot">A comparison shows differences; it is not advice to buy or sell. Figures are the latest reported by each company, as held by FinLit.</p>
          </>)}
    </div>
  );
}
