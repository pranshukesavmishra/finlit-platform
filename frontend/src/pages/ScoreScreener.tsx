import { HScroll } from "../components/HScroll";
import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { PageArt } from "../components/PageArt";
import { Plain } from "../components/Plain";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import { useUniverse, type Row } from "../lib/screener";
import { useUI } from "../lib/ui";
import { useWatchlist, watch } from "../lib/watchlist";
import { cr, nf, MINUS } from "../lib/format";

/** Score screener: size, sector and score-range filters on the live company universe (the same database-backed list the Screener and Compare pages use). */
type Cap = "Large" | "Mid" | "Small";
type Band = "low" | "mid" | "high";
type Item = Row & { cap: Cap | null; f: number | null; t: number | null };
type Pillar = "pillar_quality" | "pillar_growth" | "pillar_profitability" | "pillar_balance";
type SortKey = "name" | "price" | "market_cap" | "sector" | "f" | "t" | "overall" | Pillar;
type BandKey = "f" | "t" | "q" | "g" | "p" | "b";

const CAPS: Cap[] = ["Large", "Mid", "Small"];
const BANDS: Record<Band, { label: string; min: number; max: number }> = {
  low: { label: "Under 50", min: 0, max: 49 }, mid: { label: "50 to 79", min: 50, max: 79 }, high: { label: "80 and above", min: 80, max: 100 },
};
const FUNDAMENTAL = ["pillar_quality", "pillar_growth", "pillar_profitability", "pillar_balance"] as const;
/** The four business pillars that make up the Fundamental score, each filterable on its own (URL keys q, g, p, b). */
const PILLARS: { k: "q" | "g" | "p" | "b"; col: Pillar; label: string; short: string; say: string }[] = [
  { k: "q", col: "pillar_quality", label: "Quality", short: "Quality", say: "Steady earnings, clean accounts, cash that matches profit." },
  { k: "g", col: "pillar_growth", label: "Growth", short: "Growth", say: "How fast sales and profit have grown over 3 to 5 years." },
  { k: "p", col: "pillar_profitability", label: "Profitability", short: "Profit.", say: "Margins and returns on the money in the business." },
  { k: "b", col: "pillar_balance", label: "Balance sheet", short: "Balance", say: "Debt, interest cover and liquidity." },
];
const BAND_KEYS: BandKey[] = ["f", "t", "q", "g", "p", "b"];
const level = (v: number | null) => (v == null ? "na" : v >= 80 ? "hi" : v >= 50 ? "mid" : "lo");
const inBands = (v: number | null, bands: Band[]) => !bands.length || (v != null && bands.some((b) => v >= BANDS[b].min && v <= BANDS[b].max));
const parseBands = (s: string | null): Band[] => (s || "").split(",").filter((b): b is Band => b in BANDS);

/** Fundamental score = the average of the four business pillars (quality, growth, profitability, balance sheet); Technical = the price-trend pillar. */
function withScores(rows: Row[]): Item[] {
  // Size buckets follow SEBI's rule: the 100 largest companies are Large, the next 150 Mid, the rest Small (ranked among the companies loaded here).
  const rank = new Map(rows.filter((r) => (r.market_cap ?? 0) > 0 && r.price != null).sort((a, b) => (b.market_cap as number) - (a.market_cap as number)).map((r, i) => [r.symbol, i + 1]));
  return rows.map((r) => {
    const parts = FUNDAMENTAL.map((k) => r[k]).filter((v): v is number => v != null);
    const n = rank.get(r.symbol);
    return { ...r, f: parts.length >= 3 ? Math.round(parts.reduce((a, b) => a + b, 0) / parts.length) : null, t: r.pillar_technical,
      cap: n == null ? null : n <= 100 ? "Large" : n <= 250 ? "Mid" : "Small" };
  });
}

const Score = ({ v, locked }: { v: number | null; locked: boolean }) =>
  v == null ? <span className="ssp na" title={locked ? "Scores are part of the Silver plan" : "Not enough data to score"}>{locked ? <Icon name="lock" /> : MINUS}</span> : <span className={"ssp " + level(v)}>{v}</span>;

export function ScoreScreener() {
  useDocTitle("Score screener", "Filter every listed company by size, sector and its FinLit fundamental and technical scores.");
  const { data, isLoading, isError } = useUniverse();
  const { has, upgrade, toast } = useUI();
  const nav = useNavigate();
  useWatchlist();
  const [params, setParams] = useSearchParams();
  const applied = { cap: (CAPS.find((c) => c === params.get("cap")) ?? null) as Cap | null, sector: params.get("sector"),
    ...(Object.fromEntries(BAND_KEYS.map((k) => [k, parseBands(params.get(k))])) as Record<BandKey, Band[]>) };
  const [draft, setDraft] = useState(applied);
  const [secQ, setSecQ] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "market_cap", dir: -1 });
  const [size, setSize] = useState(10), [page, setPage] = useState(0);
  const [picked, setPicked] = useState<string[]>([]);
  const [how, setHow] = useState(false);
  const silver = has("silver"), maxCompare = has("gold") ? 4 : 2;

  const items = useMemo(() => withScores(data?.rows || []), [data]);
  const locked = !silver;   // visitors and Basic members: the server removes scores (except the free example company), so score filters would match almost nothing
  const sectors = useMemo(() => {
    const m = new Map<string, number>(); items.forEach((r) => r.sector && m.set(r.sector, (m.get(r.sector) || 0) + 1));
    return [...m.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  }, [items]);
  const capCount = useMemo(() => Object.fromEntries(CAPS.map((c) => [c, items.filter((r) => r.cap === c).length])) as Record<Cap, number>, [items]);

  const rows = useMemo(() => {
    const out = items.filter((r) => (!applied.cap || r.cap === applied.cap) && (!applied.sector || r.sector === applied.sector) && inBands(r.f, applied.f) && inBands(r.t, applied.t)
      && PILLARS.every((x) => inBands(r[x.col], applied[x.k])));
    const k = sort.key;
    return out.sort((a, b) => {
      const x = k === "name" ? (a.name || a.symbol) : k === "sector" ? a.sector : a[k], y = k === "name" ? (b.name || b.symbol) : k === "sector" ? b.sector : b[k];
      if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1;
      return (typeof x === "string" ? x.localeCompare(y as string) : (x as number) - (y as number)) * sort.dir;
    });
  }, [items, applied.cap, applied.sector, BAND_KEYS.map((k) => applied[k].join()).join("|"), sort]); // eslint-disable-line react-hooks/exhaustive-deps
  const pages = Math.max(1, Math.ceil(rows.length / size));
  const view = rows.slice(Math.min(page, pages - 1) * size, (Math.min(page, pages - 1) + 1) * size);
  const nSectors = new Set(rows.map((r) => r.sector)).size;

  const write = (next: typeof applied) => {
    const p = new URLSearchParams();
    if (next.cap) p.set("cap", next.cap); if (next.sector) p.set("sector", next.sector);
    BAND_KEYS.forEach((k) => { if (next[k].length) p.set(k, next[k].join(",")); });
    setParams(p, { replace: true }); setPage(0); setPicked([]);
  };
  const apply = () => write(draft);
  const empty = { cap: null, sector: null, ...(Object.fromEntries(BAND_KEYS.map((k) => [k, [] as Band[]])) as Record<BandKey, Band[]>) };
  const clear = () => { setDraft(empty); write(empty); };
  const drop = (k: "cap" | "sector" | BandKey) => { const n = { ...applied, [k]: k === "cap" || k === "sector" ? null : [] }; setDraft(n); write(n); };
  const toggleBand = (k: BandKey, b: Band) => setDraft((d) => ({ ...d, [k]: d[k].includes(b) ? d[k].filter((x) => x !== b) : [...d[k], b] }));
  const allStrong = PILLARS.every((x) => draft[x.k].length === 1 && draft[x.k][0] === "high");
  const setAllStrong = () => { const n = { ...draft, ...Object.fromEntries(PILLARS.map((x) => [x.k, allStrong ? [] : ["high"]])) }; setDraft(n); write(n); };
  const NAMES: Record<BandKey, string> = { f: "Fundamental", t: "Technical", q: "Quality", g: "Growth", p: "Profitability", b: "Balance sheet" };
  const chips = [
    applied.cap && ["cap", `${applied.cap} cap`], applied.sector && ["sector", applied.sector],
    ...BAND_KEYS.map((k) => applied[k].length && [k, `${NAMES[k]} ${applied[k].map((b) => BANDS[b].label.toLowerCase()).join(", ")}`]),
  ].filter(Boolean) as ["cap" | "sector" | BandKey, string][];
  const sortBy = (key: SortKey) => setSort((s) => ({ key, dir: s.key === key ? (s.dir === 1 ? -1 : 1) : key === "name" || key === "sector" ? 1 : -1 }));
  const head = (key: SortKey, label: string, cls = "") => <th className={cls}><button onClick={() => sortBy(key)} aria-label={`Sort by ${label}`}>{label} {sort.key === key ? (sort.dir > 0 ? "▲" : "▼") : "▾"}</button></th>;
  const togglePick = (s: string) => setPicked((p) => (p.includes(s) ? p.filter((x) => x !== s) : p.length >= maxCompare ? (toast(has("gold") ? "Compare up to 4 companies." : "Compare up to 2 companies. Gold compares 4."), p) : [...p, s]));
  const addWatch = (s: string) => {
    if (!silver) { upgrade("silver", "Watchlists come with the Silver plan."); return; }
    if (watch.has(s)) { watch.remove(s); toast(`${s} removed from your watchlist.`); } else { watch.add(s); toast(`${s} added to your watchlist.`); }
  };

  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><PageArt kind="research" />
        <div className="eyebrow">Score screener</div><h1>Find strong businesses by score.</h1>
        <p>Pick a size, a sector and the score range you want. Every company is scored from its latest statements and prices. Need more rules? Use the <Link to="/screener">full screener</Link>.</p></div></section>
      <div className="wrap scr-wrap">
        <div className="scr">
          <aside className="scr-side card" aria-label="Score screener filters">
            <div className="label">Market cap</div>
            <div className="scr-bands" role="group" aria-label="Market cap size">
              <button className={"bandc" + (!draft.cap ? " on" : "")} aria-pressed={!draft.cap} onClick={() => setDraft({ ...draft, cap: null })}>All</button>
              {CAPS.map((c) => <button key={c} className={"bandc" + (draft.cap === c ? " on" : "")} aria-pressed={draft.cap === c} onClick={() => setDraft({ ...draft, cap: draft.cap === c ? null : c })}>{c} cap <small>{capCount[c]}</small></button>)}
            </div>
            <div className="label" style={{ marginTop: 18 }}>Industry / sector</div>
            <label className="scr-find sm"><Icon name="table" /><input value={secQ} onChange={(e) => setSecQ(e.target.value)} placeholder="Search sectors" aria-label="Search sectors" /></label>
            <ul className="scr-sec" aria-label="Sectors">
              {sectors.filter(([s]) => s.toLowerCase().includes(secQ.toLowerCase())).map(([s, n]) => (
                <li key={s}><label><input type="radio" name="sector" checked={draft.sector === s} onChange={() => setDraft({ ...draft, sector: s })} onClick={() => draft.sector === s && setDraft({ ...draft, sector: null })} /><span>{s}</span><small className="faint" style={{ marginLeft: "auto" }}>{n}</small></label></li>))}
              {!sectors.length && !isLoading && <li className="faint">No sectors loaded yet.</li>}
            </ul>
            <div className="label" style={{ marginTop: 18, display: "flex", justifyContent: "space-between" }}>Score filters<button className="alx-link" onClick={() => setHow(!how)} aria-expanded={how} aria-controls="ss-how"><Icon name="info" /> How scores work</button></div>
            {locked ? (
              <div className="scr-lock"><b><Icon name="lock" /> Score filters are part of Silver</b><span>See and filter by Fundamental, Technical and Overall scores.</span>
                <button className="btn primary" onClick={() => upgrade("silver", "Score filters come with the Silver plan.")}>Unlock with Silver</button></div>
            ) : (<>
              {(["f"] as const).map((k) => (
                <fieldset key={k} className="ss-fs"><legend>Fundamental score</legend>
                  {(Object.keys(BANDS) as Band[]).map((b) => <label key={b}><input type="checkbox" checked={draft[k].includes(b)} onChange={() => toggleBand(k, b)} /><span>{BANDS[b].label}</span></label>)}</fieldset>
              ))}
              <fieldset className="ss-fs ss-pil"><legend>Fundamental, by pillar</legend>
                <button type="button" className={"bandc ss-all" + (allStrong ? " on" : "")} aria-pressed={allStrong} onClick={setAllStrong}>Strong on all four (80 and above)</button>
                {PILLARS.map((x) => (
                  <div key={x.k} className="ss-prow" role="group" aria-label={`${x.label} score`}>
                    <span className="ss-pn" title={x.say}>{x.label}</span>
                    <span className="ss-seg">{(Object.keys(BANDS) as Band[]).map((b) => (
                      <button key={b} type="button" className={"ss-sb " + b + (draft[x.k].includes(b) ? " on" : "")} aria-pressed={draft[x.k].includes(b)} aria-label={`${x.label} ${BANDS[b].label}`} onClick={() => toggleBand(x.k, b)}>
                        {b === "low" ? "<50" : b === "mid" ? "50–79" : "80+"}</button>))}</span>
                  </div>))}
              </fieldset>
              {(["t"] as const).map((k) => (
                <fieldset key={k} className="ss-fs"><legend>Technical score</legend>
                  {(Object.keys(BANDS) as Band[]).map((b) => <label key={b}><input type="checkbox" checked={draft[k].includes(b)} onChange={() => toggleBand(k, b)} /><span>{BANDS[b].label}</span></label>)}</fieldset>
              ))}
            </>)}
            <div className="ss-actions"><button className="btn primary" onClick={apply}>Apply filters</button><button className="btn" onClick={clear}>Clear all</button></div>
          </aside>

          <section className="scr-main card" aria-label="Results">
            {how && <div id="ss-how" className="ss-how" role="note"><b>How scores work</b>
              <p><b>Fundamental</b> is the average of four business pillars, and each can be filtered on its own: <b>Quality</b> (steady earnings, cash that matches profit), <b>Growth</b> (sales and profit growth over 3 to 5 years), <b>Profitability</b> (margins and returns on capital) and <b>Balance sheet</b> (debt, interest cover, liquidity). <b>Technical</b> is how the price is trending against its 50 and 200 day averages and momentum. <b>Overall</b> is the FinLit model score, the average of all five pillars. Each runs from 0 to 100.</p>
              <p>Size follows SEBI's rule: the 100 largest companies are Large cap, the next 150 Mid cap, the rest Small cap. Scores are research, not a recommendation. <Link to="/glossary">See the glossary</Link>.</p></div>}
            <div className="ss-stats" aria-label="Summary">
              {([["Stocks found", isLoading ? "…" : nf(rows.length, 0)], ["Sectors", isLoading ? "…" : nf(nSectors, 0)], ["Market cap", applied.cap ? `${applied.cap} cap` : "All"], ["Active filters", nf(chips.length, 0)]] as const).map(([l, v]) => <div key={l} className="ss-stat"><b>{v}</b><small>{l}</small></div>)}
            </div>
            {chips.length > 0 && <div className="scr-chips">{chips.map(([k, label]) => <button key={k} className="fchip" onClick={() => drop(k)}>{label}<span aria-hidden="true">×</span><span className="sr">remove</span></button>)}<button className="alx-link" onClick={clear}>Clear all</button></div>}
            {isError ? <div className="state"><h2>The score screener is unavailable right now</h2><p>Please try again in a moment.</p></div> : isLoading ? <div className="skeleton" style={{ height: 380 }} /> : (
              <>
                <HScroll className="scr-tw" label="results table"><table className="scr-t ss-t">
                  <thead><tr><th><span className="sr">Select</span></th>{head("name", "Stock", "stick")}{head("price", "LTP (₹)")}{head("market_cap", "Market cap")}{head("sector", "Sector")}{head("f", "Fundamental")}{PILLARS.map((x) => <th key={x.k} className="ss-ph" title={x.say}><button onClick={() => sortBy(x.col)} aria-label={`Sort by ${x.label}`}>{x.short} {sort.key === x.col ? (sort.dir > 0 ? "▲" : "▼") : "▾"}</button></th>)}{head("t", "Technical")}{head("overall", "Overall")}<th>Action</th></tr></thead>
                  <tbody>{view.map((r) => (
                    <tr key={r.symbol}>
                      <td><input type="checkbox" checked={picked.includes(r.symbol)} onChange={() => togglePick(r.symbol)} aria-label={`Select ${r.symbol} to compare`} /></td>
                      <td className="stick"><Link to={`/stocks/${r.symbol}`} className="co"><span className="av mini" aria-hidden="true">{(r.name || r.symbol).slice(0, 2).toUpperCase()}</span><span><b>{r.symbol}</b><small>{r.name}</small></span></Link></td>
                      <td>{r.price != null ? nf(r.price) : MINUS}</td><td>{cr(r.market_cap)}</td><td style={{ fontFamily: "var(--sans)", textAlign: "left" }}>{r.sector || MINUS}</td>
                      <td><Score v={r.f} locked={!silver} /></td>{PILLARS.map((x) => <td key={x.k} className="ss-pc"><Score v={r[x.col]} locked={!silver} /></td>)}<td><Score v={r.t} locked={!silver} /></td><td><Score v={r.overall} locked={!silver} /></td>
                      <td className="ss-act"><Link className="btn" to={`/stocks/${r.symbol}`}>Report</Link>
                        <button className={"btn" + (watch.has(r.symbol) ? " on" : "")} aria-pressed={watch.has(r.symbol)} aria-label={`${watch.has(r.symbol) ? "Remove" : "Add"} ${r.symbol} ${watch.has(r.symbol) ? "from" : "to"} watchlist`} onClick={() => addWatch(r.symbol)}><Icon name="wallet" /></button></td>
                    </tr>))}
                    {!rows.length && <tr><td colSpan={13} className="empty">No companies match all of these filters. Try loosening one, or clear them all.</td></tr>}
                  </tbody>
                </table></HScroll>
                <div className="ss-foot">
                  <label className="muted">Rows per page <select value={size} onChange={(e) => { setSize(Number(e.target.value)); setPage(0); }} aria-label="Rows per page">{[5, 10, 20, 50].map((n) => <option key={n} value={n}>{n}</option>)}</select></label>
                  <span className="muted">Page {Math.min(page, pages - 1) + 1} of {pages}</span>
                  <span><button className="btn" disabled={page <= 0} onClick={() => setPage(page - 1)} aria-label="Previous page">‹</button> <button className="btn" disabled={page >= pages - 1} onClick={() => setPage(page + 1)} aria-label="Next page">›</button></span>
                  {picked.length > 0 && <button className="btn primary" disabled={picked.length < 2} onClick={() => nav(`/compare?c=${picked.join(",")}`)}>{picked.length < 2 ? "Pick one more to compare" : `Compare ${picked.length} companies`}</button>}
                </div>
              </>
            )}
            <Plain>A score screen narrows a long list; it does not say what to buy. Open a company's report to see why a score looks the way it does.</Plain>
          </section>
        </div>
      </div>
    </>
  );
}
