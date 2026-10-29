import { SplitDivider, useSideWidth } from "../components/SplitDivider";
import { HScroll } from "../components/HScroll";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { Icon } from "../lib/icons";
import { PageArt } from "../components/PageArt";
import { Plain } from "../components/Plain";
import { useUI, TIER } from "../lib/ui";
import { limitsFor } from "../lib/auth";
import { screens, useSavedScreens } from "../lib/screens";
import { useDocTitle } from "../lib/title";
import { csvText, nf } from "../lib/format";
import { saveFile } from "../stock/derive";
import { BAND_LABEL, EMPTY, GROUPS, METRICS, QUICK, activeCount, applyFilters, fmt, useUniverse, type NumKey, type Row, type State } from "../lib/screener";

const COLS: { id: string; label: string; keys: NumKey[] }[] = [
  { id: "size", label: "Size & price", keys: ["market_cap", "price"] },
  { id: "returns", label: "Returns", keys: ["change_pct", "return_1m", "return_1y"] },
  { id: "valuation", label: "Valuation", keys: ["pe", "pb", "dividend_yield"] },
  { id: "profit", label: "Profitability", keys: ["roe", "roce", "operating_margin"] },
  { id: "growth", label: "Growth", keys: ["sales_cagr", "profit_cagr"] },
  { id: "health", label: "Financial health", keys: ["debt_to_equity"] },
  { id: "model", label: "FinLit model", keys: ["overall", "pillar_quality", "pillar_growth", "pillar_profitability", "pillar_balance", "pillar_technical"] },
];
const DEFAULT_COLS: NumKey[] = ["market_cap", "price", "change_pct", "return_1y", "pe", "pb", "roe", "roce", "debt_to_equity"];
const GOLD_COLS: NumKey[] = ["overall", "pillar_quality", "pillar_growth"];

export function ScreenerLite() {
  const [sideW, setSide] = useSideWidth("lite");
  useDocTitle("Stock screener", "Filter every listed Indian stock by size, valuation, profitability, growth and financial health. Gold adds filters built on the FinLit research model.");
  const { has, upgrade, toast, plan } = useUI();
  const nav = useNavigate();
  const { data, isLoading, isError } = useUniverse();
  const [tab, setTab] = useState<"filters" | "quick">("filters");
  const [f, setF] = useState<State>(EMPTY);
  const [open, setOpen] = useState<Record<string, boolean>>({ size: true, valuation: true });
  const [find, setFind] = useState("");
  const [q, setQ] = useState("");
  const [cols, setCols] = useState<NumKey[]>(DEFAULT_COLS);
  const [colMenu, setColMenu] = useState(false);
  const [sort, setSort] = useState<{ key: NumKey | "name"; dir: 1 | -1 }>({ key: "market_cap", dir: -1 });
  const [shown, setShown] = useState(40);
  const saved = useSavedScreens();
  const [saveName, setSaveName] = useState("");
  const gold = has("gold");
  useEffect(() => { if (gold) setCols((c) => (c.includes("overall") ? c : [...GOLD_COLS, ...c])); else setCols((c) => c.filter((k) => !METRICS[k].model)); }, [gold]);

  const rows = data?.rows || [];
  const result = useMemo(() => {
    let r = applyFilters(rows, gold ? f : { ...f, ranges: Object.fromEntries(Object.entries(f.ranges).filter(([k]) => !METRICS[k as NumKey].model)), bands: [] });
    if (q.trim()) { const s = q.trim().toLowerCase(); r = r.filter((x) => x.symbol.toLowerCase().includes(s) || (x.name || "").toLowerCase().includes(s)); }
    const g = (x: Row) => (sort.key === "name" ? (x.name || "") : (x[sort.key] as number | null));
    return [...r].sort((a, b) => { const A = g(a), B = g(b); if (A == null && B == null) return 0; if (A == null) return 1; if (B == null) return -1; return (A < B ? -1 : A > B ? 1 : 0) * sort.dir; });
  }, [rows, f, q, sort, gold]);
  useEffect(() => setShown(40), [f, q, sort]);

  const sectors = useMemo(() => { const m = new Map<string, number>(); rows.forEach((r) => r.sector && m.set(r.sector, (m.get(r.sector) || 0) + 1)); return [...m.entries()].sort((a, b) => b[1] - a[1]); }, [rows]);
  const heat = useMemo(() => {
    const out: Partial<Record<NumKey, [number, number]>> = {};
    for (const k of cols) { const v = result.map((r) => r[k]).filter((x): x is number => x != null).sort((a, b) => a - b); if (v.length > 4) out[k] = [v[Math.floor(v.length * 0.25)], v[Math.floor(v.length * 0.75)]]; }
    return out;
  }, [result, cols]);
  const tone = (k: NumKey, v: number | null) => {
    const m = METRICS[k], h = heat[k]; if (v == null || !h || m.better === "none" || k === "price") return "";
    const good = m.better === "higher" ? v >= h[1] : v <= h[0], bad = m.better === "higher" ? v <= h[0] : v >= h[1];
    return good ? "tone-good" : bad ? "tone-bad" : "";
  };

  const setRange = (k: NumKey, side: "min" | "max", raw: string) => setF((s) => {
    const cur = { ...(s.ranges[k] || {}) }, n = raw === "" ? undefined : Number(raw);
    if (n != null && Number.isNaN(n)) return s;
    cur[side] = n; return { ...s, ranges: { ...s.ranges, [k]: cur } };
  });
  const toggle = (arr: string[], v: string) => (arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v]);
  const lockedTap = () => { upgrade("gold", "FinLit model filters come with the Gold plan."); };
  const nActive = activeCount(f);
  const chips: { label: string; clear: () => void }[] = [
    ...Object.entries(f.ranges).filter(([, r]) => r && (r.min != null || r.max != null)).map(([k, r]) => ({ label: `${METRICS[k as NumKey].short} ${r!.min != null ? "≥ " + r!.min : ""}${r!.min != null && r!.max != null ? " and " : ""}${r!.max != null ? "≤ " + r!.max : ""}`, clear: () => setF((s) => ({ ...s, ranges: { ...s.ranges, [k]: {} } })) })),
    ...f.sectors.map((s) => ({ label: s, clear: () => setF((x) => ({ ...x, sectors: x.sectors.filter((y) => y !== s) })) })),
    ...f.bands.map((s) => ({ label: `Band: ${BAND_LABEL[s]}`, clear: () => setF((x) => ({ ...x, bands: x.bands.filter((y) => y !== s) })) })),
  ];
  const save = () => { const n = saveName.trim(); if (!n || !nActive) { toast("Add a filter and a name first."); return; } if (saved.length >= limitsFor(plan).screens && !saved.some((s) => s.name === n)) { toast(`Your plan keeps up to ${limitsFor(plan).screens} saved screens. Remove one first.`); return; } screens.save(n, f, limitsFor(plan).screens); setSaveName(""); toast(`Saved “${n}” in Quick screens.`); };
  const download = () => {
    if (!has("silver")) { toast("Downloads come with the Silver plan. Showing plans."); nav("/plans"); return; }
    const ks = cols; const esc = (s: string) => `"${csvText(s).replace(/"/g, '""')}"`;
    const csv = [["Symbol", "Company", "Sector", ...ks.map((k) => METRICS[k].label)].map(esc).join(","), ...result.map((r) => [r.symbol, r.name || "", r.sector || "", ...ks.map((k) => r[k] ?? "")].map((v) => (typeof v === "string" ? esc(v) : v)).join(","))].join("\n");
    saveFile("FinLit-screen.csv", csv, "text/csv;charset=utf-8"); toast(`Saved ${result.length} companies as FinLit-screen.csv.`);
  };
  const sortBy = (key: NumKey | "name") => setSort((s) => (s.key === key ? { key, dir: (-s.dir) as 1 | -1 } : { key, dir: key === "name" ? 1 : METRICS[key as NumKey]?.better === "lower" ? 1 : -1 }));
  const openRow = (r: Row) => { if (r.sample) { toast("Sample company: the live site opens a full report here."); return; } nav(`/stocks/${r.symbol}`); };
  const fl = find.trim().toLowerCase();
  const groups = GROUPS.filter((g) => !fl || g.label.toLowerCase().includes(fl) || g.filters.some((x) => METRICS[x.key].label.toLowerCase().includes(fl)));

  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><PageArt kind="research" />
        <div className="eyebrow">Stock screener</div><h1>Find the companies that fit your rules.</h1>
        <p>Filter every listed company by size, valuation, profitability, growth and debt. Gold adds filters built on the FinLit research model. Prefer a simpler start? Try the <Link to="/score-screener">Basic score screener</Link> (Silver) or the <Link to="/advanced-score-screener">Advanced score screener</Link> (Gold).</p></div></section>
      <div className="wrap scr-wrap">
        {data?.sample && <div className="sample-note" role="note"><Icon name="info" /><span><b>Sample data.</b> Reliance is a real report; the other companies in this demo are fictional (symbols start with SMP-) so you can try the filters. The live site screens every listed company.</span></div>}
        <div className="scr" style={{ "--side-w": `${sideW}px` } as React.CSSProperties}>
          <aside className="scr-side card" aria-label="Filters" hidden={sideW === 0}>
            <div className="seg scr-tabs" role="tablist"><button role="tab" aria-selected={tab === "filters"} onClick={() => setTab("filters")}>Filters{nActive ? <i className="dotn">{nActive}</i> : null}</button><button role="tab" aria-selected={tab === "quick"} onClick={() => setTab("quick")}>Quick screens</button></div>
            {tab === "filters" ? (
              <>
                <label className="scr-find"><Icon name="table" /><input value={find} onChange={(e) => setFind(e.target.value)} placeholder="Search for a filter" aria-label="Search for a filter" /></label>
                <div className="scr-groups">{groups.map((g) => {
                  const locked = g.model && !gold, isOpen = !!(open[g.id] || fl);
                  const n = g.id === "sector" ? sectors.length : g.id === "model" ? g.filters.length + 1 : g.filters.length;
                  return (
                    <div key={g.id} className={"scr-g" + (g.model ? " is-model" : "")}>
                      <button className="scr-gh" aria-expanded={isOpen} onClick={() => setOpen((o) => ({ ...o, [g.id]: !o[g.id] }))}>
                        <span>{g.label}{g.model && <span className={"tier gold"} style={{ marginLeft: 8 }}><Icon name="crown" />Gold</span>}</span><span className="scr-n">{n}</span><Icon name="arrow" />
                      </button>
                      {isOpen && (
                        <div className="scr-gb">
                          {g.id === "sector" && (<ul className="scr-sec">{sectors.map(([s, c]) => <li key={s}><label><input type="checkbox" checked={f.sectors.includes(s)} onChange={() => setF((x) => ({ ...x, sectors: toggle(x.sectors, s) }))} />{s}<em>{c}</em></label></li>)}</ul>)}
                          {g.model && locked && (<div className="scr-lock"><span className="lk"><Icon name="lock" /></span><b>Filter by the FinLit model</b><p>FinLit score, band and each of the five pillars: Quality, Growth, Profitability, Balance sheet and Technical.</p><button className="btn" onClick={lockedTap}>Unlock with Gold <Icon name="arrow" /></button></div>)}
                          {g.model && !locked && (<div className="scr-bands" role="group" aria-label="FinLit band">{(["strong", "healthy", "mixed", "watch"] as const).map((b) => <button key={b} className={"bandc " + b} aria-pressed={f.bands.includes(b)} onClick={() => setF((x) => ({ ...x, bands: toggle(x.bands, b) }))}>{BAND_LABEL[b]}</button>)}</div>)}
                          {!(g.model && locked) && g.filters.map((d) => { const m = METRICS[d.key], r = f.ranges[d.key] || {}; return (
                            <div className="scr-f" key={d.key}>
                              <div className="scr-fl"><span>{m.label}</span><small>{d.hint}</small></div>
                              <div className="scr-fi"><input type="number" inputMode="decimal" step={d.step} placeholder="Min" value={r.min ?? ""} onChange={(e) => setRange(d.key, "min", e.target.value)} aria-label={`${m.label} minimum`} /><span>to</span><input type="number" inputMode="decimal" step={d.step} placeholder="Max" value={r.max ?? ""} onChange={(e) => setRange(d.key, "max", e.target.value)} aria-label={`${m.label} maximum`} /></div>
                            </div>); })}
                        </div>
                      )}
                    </div>
                  );
                })}</div>
                <div className="scr-save"><div className="scr-sh"><span>Save as a screen</span><button className="lnk" onClick={() => { setF(EMPTY); toast("Filters cleared."); }}>Reset all</button></div>
                  <div className="scr-sr"><input value={saveName} onChange={(e) => setSaveName(e.target.value)} placeholder="Name this screen" aria-label="Screen name" maxLength={40} onKeyDown={(e) => e.key === "Enter" && save()} /><button className="btn" onClick={save}>Save</button></div></div>
              </>
            ) : (
              <div className="scr-quick">
                {saved.length > 0 && <><div className="label">My screens</div>{saved.map((s) => <button key={s.name} className="qs" onClick={() => { setF(s.state); setTab("filters"); }}><b>{s.name}</b><span>{activeCount(s.state)} filters</span></button>)}</>}
                <div className="label">Ready-made screens</div>
                {QUICK.map((s) => { const lock = s.model && !gold; return (
                  <button key={s.id} className={"qs" + (lock ? " lock" : "")} onClick={() => { if (lock) { lockedTap(); return; } setF(s.state); setTab("filters"); toast(`Applied: ${s.label}.`); }}>
                    <b>{s.model && <Icon name={lock ? "lock" : "crown"} />}{s.label}</b><span>{s.says}</span>
                  </button>); })}
              </div>
            )}
          </aside>
          <SplitDivider width={sideW} set={setSide} />

          <section className="scr-main card" aria-label="Results">
            <div className="scr-top">
              <div><b className="scr-count">{isLoading ? "…" : nf(result.length, 0)}</b> <span className="muted">of {nf(rows.length, 0)} stocks · sorted by {sort.key === "name" ? "name" : METRICS[sort.key].label.toLowerCase()}</span></div>
              <div className="scr-tools">
                <label className="scr-find sm"><Icon name="table" /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search stocks" aria-label="Search stocks in results" /></label>
                <div className="scr-cm"><button className="btn" aria-expanded={colMenu} onClick={() => setColMenu(!colMenu)}>Columns</button>
                  {colMenu && <div className="scr-colmenu" role="menu">{COLS.map((g) => (g.id === "model" && !gold ? null : <div key={g.id}><div className="label">{g.label}</div>{g.keys.map((k) => <label key={k}><input type="checkbox" checked={cols.includes(k)} onChange={() => setCols((c) => (c.includes(k) ? c.filter((x) => x !== k) : [...c, k]))} />{METRICS[k].label}</label>)}</div>))}
                    {!gold && <button className="lk-row" onClick={lockedTap}><Icon name="lock" />Model score columns · Gold</button>}</div>}</div>
                <button className="btn" onClick={download}><Icon name="table" />Download</button>
              </div>
            </div>
            {chips.length > 0 && <div className="scr-chips">{chips.map((c) => <button key={c.label} className="fchip" onClick={c.clear}>{c.label}<span aria-hidden="true">×</span><span className="sr">remove</span></button>)}</div>}
            {isError ? <div className="state"><h2>The screener is unavailable right now</h2><p>Please try again in a moment.</p></div> : isLoading ? <div className="skeleton" style={{ height: 380 }} /> : (
              <HScroll className="scr-tw" label="results table"><table className="scr-t">
                <thead>
                  <tr className="gh"><th />{COLS.map((g) => { const n = g.keys.filter((k) => cols.includes(k)).length; return n ? <th key={g.id} colSpan={n} className="grp">{g.label}</th> : null; })}</tr>
                  <tr><th className="stick"><button onClick={() => sortBy("name")}>Company {sort.key === "name" ? (sort.dir > 0 ? "▲" : "▼") : "▾"}</button></th>
                    {COLS.flatMap((g) => g.keys).filter((k) => cols.includes(k)).map((k) => <th key={k}><button onClick={() => sortBy(k)} aria-label={`Sort by ${METRICS[k].label}`}>{METRICS[k].short} {sort.key === k ? (sort.dir > 0 ? "▲" : "▼") : "▾"}</button></th>)}</tr>
                </thead>
                <tbody>{result.slice(0, shown).map((r) => (
                  <tr key={r.symbol} tabIndex={0} onClick={() => openRow(r)} onKeyDown={(e) => e.key === "Enter" && openRow(r)}>
                    <td className="stick"><span className="co"><span className="av mini" aria-hidden="true">{(r.name || r.symbol).slice(0, 2).toUpperCase()}</span><span><b>{r.symbol}</b><small>{r.name}</small></span></span></td>
                    {COLS.flatMap((g) => g.keys).filter((k) => cols.includes(k)).map((k) => <td key={k} className={tone(k, r[k]) + (k === "overall" ? " sc" : "")}>{k === "overall" && r.band ? <span className={"vd " + r.band}>{r.overall}</span> : fmt(METRICS[k], r[k])}</td>)}
                  </tr>))}
                  {!result.length && <tr><td colSpan={cols.length + 1} className="empty">No companies match all of these filters. Try loosening one.</td></tr>}
                </tbody>
              </table>
                {result.length > shown && <div className="more"><button className="btn" onClick={() => setShown((s) => s + 40)}>Show more ({result.length - shown} left)</button></div>}
              </HScroll>
            )}
            <Plain>Green cells are in the best quarter of the results for that column, red cells the weakest quarter. “Best” means lower for P/E, P/B and debt, higher for returns and profitability.</Plain>
            <p className="faint scr-foot">A screen narrows a long list; it does not say what to buy. Open a company's report to see why a number looks the way it does. {TIER.gold.n} adds model-based filters.</p>
          </section>
        </div>
      </div>
    </>
  );
}
