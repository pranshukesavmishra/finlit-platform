import { PageHeader } from "../components/PageHeader";
import { titleOf, subOf, codeNote } from "../lib/companyLabel";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { AlertButton } from "../components/AlertComposer";
import { Link, useNavigate } from "react-router";
import { Icon } from "../lib/icons";
import { Gate } from "../components/Gate";
import { Plain } from "../components/Plain";
import { useUI } from "../lib/ui";
import { limitsFor } from "../lib/auth";
import { useDocTitle } from "../lib/title";
import { DEMO } from "../lib/demo";
import { cr, csvText, nf } from "../lib/format";
import { saveFile } from "../stock/derive";
import { watch as wl, useWatchlist } from "../lib/watchlist";
import { FilterNote, SearchFilters, useRowFilter } from "../components/SearchFilters";
import { hiddenRowMatches } from "../lib/searchFilters";
import { BAND_LABEL, METRICS, fmt, useUniverse, type NumKey, type Row } from "../lib/screener";
import { ChartHelp } from "../components/ChartHelp";
import { Logo } from "../components/search/parts";
import { useQuotesFor } from "../lib/api";
import { quoteMap } from "../lib/globalSearch";
import { scoreBand } from "../lib/scoreBands";

type GroupBy = "none" | "sector" | "size" | "band" | "style";
const GROUPS: { id: GroupBy; label: string; gold?: boolean }[] = [{ id: "none", label: "No grouping" }, { id: "sector", label: "Industry" }, { id: "size", label: "Company size" }, { id: "band", label: "FinLit band", gold: true }, { id: "style", label: "Style", gold: true }];
const SORTS: { id: NumKey | "name"; label: string }[] = [{ id: "overall", label: "FinLit IQ" }, { id: "change_pct", label: "Today's change" }, { id: "market_cap", label: "Market cap" }, { id: "price", label: "Price" }, { id: "roe", label: "ROE" }, { id: "pe", label: "P/E" }, { id: "dividend_yield", label: "Dividend yield" }, { id: "name", label: "Name" }];
const size = (c: number | null) => (c == null ? "Unknown" : c >= 100000 ? "Large cap" : c >= 30000 ? "Mid cap" : c >= 5000 ? "Small cap" : "Micro cap");
const style = (r: Row) => (r.pe == null ? "Unknown" : r.pe < 15 || (r.pb != null && r.pb < 1.5) ? "Value" : r.pe > 35 ? "Premium growth" : "Blend");
const keyOf = (g: GroupBy, r: Row) => (g === "sector" ? r.sector || "Other" : g === "size" ? size(r.market_cap) : g === "band" ? (r.band ? BAND_LABEL[r.band] : "Unscored") : g === "style" ? style(r) : "");

export function signals(r: Row, target?: number): string[] {
  const out: string[] = [];
  if (r.band === "watch") out.push(`FinLit IQ is ${r.overall}, in the Watch band`);
  if ((r.pillar_balance ?? 100) <= 35) out.push(`Weak balance sheet (${r.pillar_balance}/100)`);
  if ((r.return_1m ?? 0) <= -10) out.push(`Fell ${nf(Math.abs(r.return_1m!), 1)}% in a month`);
  if ((r.pe ?? 0) >= 60) out.push(`Expensive at ${nf(r.pe!, 0)}× earnings`);
  if (target && r.price) { const d = ((r.price - target) / target) * 100; if (Math.abs(d) <= 5) out.push(`Within ${nf(Math.abs(d), 1)}% of your target ₹${nf(target, 0)}`); }
  return out;
}

function Th({ id, label, sort, on, r, c }: { id: NumKey | "name"; label: string; sort: NumKey | "name"; on: (k: NumKey | "name") => void; r?: boolean; c?: boolean }) {
  const active = sort === id;
  return (
    <th scope="col" className={(r ? "r " : c ? "c " : "") + (active ? "is-sorted" : "")} aria-sort={active ? (id === "pe" || id === "name" ? "ascending" : "descending") : "none"}>
      <button type="button" onClick={() => on(id)} title={`Sort by ${label}`}>{label}<svg viewBox="0 0 12 12" width="10" height="10" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M3.5 5 6 2.5 8.5 5M3.5 7 6 9.5 8.5 7" /></svg></button>
    </th>
  );
}

function Add({ rows: all, taken, onAdd }: { rows: Row[]; taken: string[]; onAdd: (r: Row) => void }) {
  const [q, setQ] = useState(""), [open, setOpen] = useState(false), box = useRef<HTMLDivElement>(null);
  useEffect(() => { const h = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); }; document.addEventListener("mousedown", h); return () => document.removeEventListener("mousedown", h); }, []);
  const sf = useRowFilter(all, (r) => ({ sector: r.sector, cap: r.market_cap }));
  const rows = sf.rows, s = q.trim().toLowerCase();
  const list = s ? rows.filter((r) => !taken.includes(r.symbol) && (r.symbol.toLowerCase().includes(s) || (r.name || "").toLowerCase().includes(s))).slice(0, 7) : sf.on ? [...rows].sort((a, b) => (b.market_cap ?? -1) - (a.market_cap ?? -1)).filter((r) => !taken.includes(r.symbol)).slice(0, 7) : [];
  return (
    <div className="wl-add" ref={box}>
      <label><Icon name="table" /><input value={q} onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} placeholder="Add a stock to this list…" aria-label="Add a stock" /><SearchFilters variant="panel" className="sf-flex" facets={sf.facets} value={sf.filter} onChange={sf.setFilter} count={sf.count} /></label>
      {open && sf.on && !list.length && <div className="pk-m"><FilterNote filter={sf.filter} q={q.trim()} onChange={sf.setFilter} hidden={hiddenRowMatches(all.filter((r) => !taken.includes(r.symbol)), (r) => ({ sector: r.sector, cap: r.market_cap }), q, sf.filter)} /></div>}
      {open && list.length > 0 && <div className="pk-m" role="listbox">{list.map((r) => <button key={r.symbol} role="option" aria-selected="false" onClick={() => { onAdd(r); setQ(""); setOpen(false); }}><b>{r.name}</b><small>{r.symbol} · {r.sector}</small></button>)}</div>}
    </div>
  );
}

export function WatchlistPage() {
  useDocTitle("Watchlist", "Track your stocks in named lists, bucket them by industry, size or FinLit band, and see what needs attention.");
  const { has, toast, upgrade, plan } = useUI();
  const nav = useNavigate();
  const st = useWatchlist();
  const uniQ = useUniverse(), { data } = uniQ;
  const rows = data?.rows || [], bySym = useMemo(() => new Map(rows.map((r) => [r.symbol, r])), [rows]);
  const [lid, setLid] = useState(st.lists[0].id), [group, setGroup] = useState<GroupBy>("none"), [sort, setSort] = useState<NumKey | "name">("overall");
  const [sel, setSel] = useState<string[]>([]), [naming, setNaming] = useState(false), [name, setName] = useState(""), [edit, setEdit] = useState<string | null>(null);
  const gold = has("gold"), silver = has("silver");
  const list = st.lists.find((l) => l.id === lid) || st.lists[0];
  useEffect(() => { if (!st.lists.some((l) => l.id === lid)) setLid(st.lists[0].id); }, [st.lists, lid]);
  useEffect(() => { if (DEMO && !st.seeded && rows.length) wl.seed([...rows].sort((a, b) => (b.market_cap || 0) - (a.market_cap || 0)).slice(0, 9).map((r) => r.symbol)); }, [rows, st.seeded]);
  useEffect(() => { if (!gold && (group === "band" || group === "style")) setGroup("sector"); }, [gold, group]);

  const items = useMemo(() => list.symbols.map((s) => bySym.get(s)).filter((r): r is Row => !!r).sort((a, b) => {
    if (sort === "name") return (a.name || "").localeCompare(b.name || "");
    const A = a[sort] as number | null, B = b[sort] as number | null; if (A == null && B == null) return 0; if (A == null) return 1; if (B == null) return -1;
    return sort === "pe" ? A - B : B - A;
  }), [list, bySym, sort]);
  const buckets = useMemo(() => { if (group === "none") return [["", items] as [string, Row[]]]; const m = new Map<string, Row[]>(); items.forEach((r) => { const k = keyOf(group, r); m.set(k, [...(m.get(k) || []), r]); }); return [...m.entries()].sort((a, b) => b[1].length - a[1].length); }, [items, group]);
  const logos = quoteMap(useQuotesFor(list.symbols).data);
  const adv = items.filter((r) => (r.change_pct ?? 0) > 0).length, dec = items.filter((r) => (r.change_pct ?? 0) < 0).length;
  const scored = items.filter((r) => r.overall != null), avg = scored.length ? scored.reduce((a, r) => a + (r.overall as number), 0) / scored.length : null;
  const attention = items.map((r) => ({ r, s: signals(r, st.meta[r.symbol]?.target) })).filter((x) => x.s.length);
  const secMix = useMemo(() => { const m = new Map<string, number>(); items.forEach((r) => m.set(r.sector || "Other", (m.get(r.sector || "Other") || 0) + 1)); return [...m.entries()].sort((a, b) => b[1] - a[1]); }, [items]);
  const topShare = items.length ? (secMix[0]?.[1] || 0) / items.length : 0;
  const lim = limitsFor(plan), MAXL = lim.watchlist_lists;

  const addStock = (r: Row) => { if (wl.total() >= lim.watchlist_symbols && !wl.has(r.symbol)) { if (gold) toast(`Your watchlist is full (${lim.watchlist_symbols} stocks).`); else upgrade("gold", "Silver holds up to 30 stocks; Gold holds up to 1,000."); return; } wl.add(r.symbol, list.id); toast(`${r.symbol} added to ${list.name}.`); };
  const newList = () => { if (st.lists.length >= MAXL) { if (gold) toast(`You have reached ${MAXL} lists.`); else upgrade("gold", "Silver includes 3 lists; Gold has up to 50."); return; } const id = wl.create(name || `List ${st.lists.length + 1}`); setLid(id); setName(""); setNaming(false); };
  const exportCsv = () => { if (!silver) { toast("Downloads come with the Silver plan."); nav("/plans"); return; } const esc = (s: string) => `"${csvText(s).replace(/"/g, '""')}"`; const ks: NumKey[] = ["price", "change_pct", "market_cap", "pe", "roe", "dividend_yield", "overall"]; saveFile("FinLit-watchlist.csv", [["Symbol", "Company", "Sector", ...ks.map((k) => METRICS[k].label), "Target", "Note"].map(esc).join(","), ...items.map((r) => [r.symbol, r.name || "", r.sector || "", ...ks.map((k) => r[k] ?? ""), st.meta[r.symbol]?.target ?? "", st.meta[r.symbol]?.note ?? ""].map((v) => (typeof v === "string" ? esc(v) : v)).join(","))].join("\n"), "text/csv;charset=utf-8"); toast("Saved FinLit-watchlist.csv."); };
  const toggleSel = (s: string) => setSel((x) => (x.includes(s) ? x.filter((y) => y !== s) : x.length >= (gold ? 4 : 2) ? (toast(gold ? "Compare up to 4 companies." : "Silver compares 2 companies. Gold compares up to 4."), x) : [...x, s]));

  return (
    <>
      <PageHeader wrap plan="silver" title="Watchlists" art="portfolio" links={["/holdings", "/alerts", "/compare"]}
        description={<>Track and manage your shortlisted companies. Add notes, set targets and monitor them in one place.</>} />
      <div className="wrap wl">
        <Gate tier="silver" title="Build your watchlist" points={["Named lists for your own themes", "Bucket stocks by industry and size", "Notes, target prices and one-click comparison"]}>
          {data?.sample && <div className="sample-note" role="note"><Icon name="info" /><span><b>Sample data.</b> Lists are saved in this browser. Reliance is real; the other companies are fictional (SMP-). On the live site your lists will follow your account to the app.</span></div>}
          <div className="wl-tabs" role="group" aria-label="Your lists">
            {st.lists.map((l) => (
              <span key={l.id} className={"wl-tab" + (l.id === list.id ? " on" : "")}>
                {edit === l.id ? <input autoFocus defaultValue={l.name} aria-label="List name" onBlur={(e) => { wl.rename(l.id, e.target.value); setEdit(null); }} onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }} />
                  : <button aria-pressed={l.id === list.id} onClick={() => setLid(l.id)} onDoubleClick={() => setEdit(l.id)}>{l.name}<i>{l.symbols.length}</i></button>}
              </span>))}
            {naming ? <span className="wl-tab on"><input autoFocus value={name} onChange={(e) => setName(e.target.value)} placeholder="List name" aria-label="New list name" onKeyDown={(e) => { if (e.key === "Enter") newList(); if (e.key === "Escape") setNaming(false); }} onBlur={() => !name && setNaming(false)} /></span> : <button className="wl-new" onClick={() => (st.lists.length >= MAXL ? newList() : setNaming(true))}>+ New list{st.lists.length >= MAXL && !gold ? " · Gold" : ""}</button>}
            <span className="grow" />
            {st.lists.length > 1 && edit !== list.id && <><button className="lnk" onClick={() => setEdit(list.id)}>Rename</button><button className="lnk" onClick={() => { wl.drop(list.id); toast(`Deleted “${list.name}”.`); }}>Delete list</button></>}
          </div>

          <div className="wl-kpi">
            <div className="wk"><b>{items.length}</b><span>Stocks in this list</span></div>
            <div className="wk up"><b>{adv}</b><span>Rising today</span></div>
            <div className="wk down"><b>{dec}</b><span>Falling today</span></div>
            <div className="wk"><b>{avg == null ? "—" : nf(avg, 0)}</b><span>Average FinLit IQ</span></div>
            <div className={"wk" + (attention.length ? " warn" : "")}><b>{gold ? attention.length : "—"}</b><span>{gold ? "Need a second look" : "Needs attention · Gold"}</span></div>
          </div>

          <div className="wl-bar">
            <Add rows={rows} taken={list.symbols} onAdd={addStock} />
            <label className="wl-sel"><span>Bucket by</span><select value={group} onChange={(e) => { const g = e.target.value as GroupBy; if (GROUPS.find((x) => x.id === g)?.gold && !gold) { upgrade("gold", "Bucketing by FinLit band and style comes with Gold."); } setGroup(g); }} aria-label="Bucket by">{GROUPS.map((g) => <option key={g.id} value={g.id}>{g.label}{g.gold && !gold ? " (Gold)" : ""}</option>)}</select></label>
            <label className="wl-sel"><span>Sort by</span><select value={sort} onChange={(e) => setSort(e.target.value as NumKey | "name")} aria-label="Sort by">{SORTS.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}</select></label>
            <button className="btn" onClick={exportCsv}>Download</button>
          </div>

          {items.length === 0 && (uniQ.isLoading || uniQ.isError) && list.symbols.length > 0 ? (
            uniQ.isError ? <div className="state"><h2>Your stocks could not be loaded</h2><p>The company data did not arrive. Your list is safe.</p><button className="btn" onClick={() => uniQ.refetch()}>Try again</button></div>
              : <div className="skeleton" style={{ height: 220 }} aria-busy="true" aria-label="Loading your stocks" />
          ) : items.length === 0 ? (
            <div className="state"><h2>This list is empty</h2><p>Search above to add a stock, or tap the star on any company report. Try one of these:</p>
              <div className="wl-sug">{[...rows].sort((a, b) => (b.market_cap || 0) - (a.market_cap || 0)).slice(0, 6).map((r) => <button key={r.symbol} className="btn" onClick={() => addStock(r)}>+ {r.symbol}</button>)}</div></div>
          ) : (
            <>
              {items.length > 1 && (
                <div className="card wl-mix"><div className="card-h"><h3><span className="ci"><Icon name="pie" /></span>Where your list is concentrated<ChartHelp id="wl-concentration" /></h3><span className="s">By industry</span></div>
                  <div className="rib" role="img" aria-label="Industry mix">{secMix.map(([s, c], i) => <span key={s} style={{ flex: c, background: ["var(--c1)", "var(--c2)", "var(--c3)", "var(--c4)", "var(--c5)"][i % 5] }} title={`${s}: ${c}`}><b>{c / items.length >= 0.14 ? Math.round((c / items.length) * 100) + "%" : ""}</b></span>)}</div>
                  <div className="wl-leg">{secMix.map(([s, c], i) => <span key={s}><i style={{ background: ["var(--c1)", "var(--c2)", "var(--c3)", "var(--c4)", "var(--c5)"][i % 5] }} />{s} <b>{c}</b></span>)}</div>
                  <p className={"seg-note" + (topShare >= 0.5 ? " warn" : "")}>{topShare >= 0.5 ? `${Math.round(topShare * 100)}% of this list is in ${secMix[0][0]}. A downturn in one industry would hit most of it.` : "This list is spread across several industries, which spreads the risk."}</p></div>
              )}
              {gold && attention.length > 0 && (
                <div className="card acc wl-att" style={{ "--ac": "var(--gold)" } as React.CSSProperties}><div className="card-h"><h3><span className="ci"><Icon name="alert" /></span>Worth a second look<ChartHelp id="wl-second" /></h3><span className="s">Based on the FinLit model and your targets</span></div>
                  <ul>{attention.map(({ r, s }) => <li key={r.symbol}><Link to={`/stocks/${r.symbol}`} onClick={(e) => { if (r.sample) { e.preventDefault(); toast("Sample company: the live site opens its report here."); } }}><b title={codeNote(r)}>{titleOf(r)}</b></Link><span>{s.join(" · ")}</span></li>)}</ul></div>
              )}
              <div className="wl-tw card">
                <table className="wl-t" aria-label={`${list.name}: your stocks`}>
                  <thead>
                    <tr>
                      <th className="wl-ck"><input type="checkbox" checked={sel.length > 0} disabled={!sel.length} onChange={() => setSel([])} aria-label="Clear the selection" title="Clear the selection" /></th>
                      <Th id="name" label="Company" sort={sort} on={setSort} />
                      <th scope="col">Industry</th>
                      <Th id="price" label="Price" sort={sort} on={setSort} r />
                      <Th id="pe" label="P/E" sort={sort} on={setSort} r />
                      <Th id="roe" label="ROE" sort={sort} on={setSort} r />
                      <Th id="market_cap" label="Mkt cap" sort={sort} on={setSort} r />
                      <Th id="overall" label="FinLit IQ" sort={sort} on={setSort} c />
                      <th scope="col">Status</th>
                      <th scope="col">Target</th>
                      <th scope="col">Your note</th>
                      <th scope="col" className="r">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {buckets.map(([k, rs]) => {
                      const ch = rs.filter((r) => r.change_pct != null), a = ch.reduce((x, r) => x + (r.change_pct as number), 0) / Math.max(1, ch.length), sc = rs.filter((r) => r.overall != null);
                      return (
                        <Fragment key={k || "all"}>
                          {k && (
                            <tr className="wl-grow"><th colSpan={12} scope="colgroup">
                              <b>{k}</b><span>{rs.length} stock{rs.length === 1 ? "" : "s"}</span><span className={a >= 0 ? "pos" : "neg"}>{a >= 0 ? "▲ +" : "▼ −"}{nf(Math.abs(a), 2)}% today on average</span>
                              {sc.length > 0 && <span>Avg score {nf(sc.reduce((x, r) => x + (r.overall as number), 0) / sc.length, 0)}</span>}
                            </th></tr>
                          )}
                          {rs.map((r) => {
                            const m = st.meta[r.symbol] || { added: 0 }, d = m.target && r.price ? ((m.target - r.price) / r.price) * 100 : null, lg = logos.get(r.symbol);
                            return (
                              <tr className={sel.includes(r.symbol) ? "sel" : ""} key={r.symbol}>
                                <td className="wl-ck" data-l=""><input type="checkbox" checked={sel.includes(r.symbol)} onChange={() => toggleSel(r.symbol)} aria-label={`Select ${r.symbol} to compare`} /></td>
                                <td className="wl-co" data-l="Company"><div className="wl-coin">
                                  <Logo src={lg?.logo} name={titleOf(r)} kind="stock" size={36} />
                                  <span className="wc-n"><Link to={`/stocks/${r.symbol}`} onClick={(e) => { if (r.sample) { e.preventDefault(); toast("Sample company: the live site opens its report here."); } }}><b title={codeNote(r)}>{titleOf(r)}</b></Link>{subOf(r) && <small>{subOf(r)}</small>}</span>
                                </div></td>
                                <td className="wl-ind" data-l="Industry">{r.sector || "—"}</td>
                                <td className="r" data-l="Price"><b>{fmt(METRICS.price, r.price)}</b><span className={(r.change_pct ?? 0) >= 0 ? "pos" : "neg"}>{(r.change_pct ?? 0) >= 0 ? "▲" : "▼"} {fmt(METRICS.change_pct, r.change_pct).replace("+", "")}</span></td>
                                <td className="r" data-l="P/E">{fmt(METRICS.pe, r.pe)}</td>
                                <td className="r" data-l="ROE">{fmt(METRICS.roe, r.roe)}</td>
                                <td className="r" data-l="Mkt cap">{cr(r.market_cap)}</td>
                                <td className="c" data-l="FinLit IQ">{r.overall != null ? <span className={"wl-iq " + scoreBand(r.overall)}>{Math.round(r.overall)}</span> : <span className="faint" title="Not scored yet">—</span>}</td>
                                <td data-l="Status">{r.overall != null && r.band ? <span className={"wl-st " + r.band}><i aria-hidden="true" />{BAND_LABEL[r.band]}</span> : <span className="faint">Not scored</span>}</td>
                                <td data-l="Target">
                                  <input className="wl-tg" type="number" inputMode="decimal" min={0} value={m.target ?? ""} placeholder="Set" onChange={(e) => wl.setMeta(r.symbol, { target: e.target.value === "" ? undefined : Math.max(0, Number(e.target.value)) })} aria-label={`${r.symbol} target price in rupees`} />
                                  {d != null && <em className={d >= 0 ? "pos" : "neg"}>{d >= 0 ? "▲ " : "▼ "}{nf(Math.abs(d), 1)}% to target</em>}
                                </td>
                                <td className="wl-ntc" data-l="Your note"><textarea className="wl-nt" rows={2} maxLength={200} placeholder="Add a note…" value={m.note ?? ""} onChange={(e) => wl.setMeta(r.symbol, { note: e.target.value })} aria-label={`${r.symbol} note`} /></td>
                                <td className="r wl-ac" data-l="">
                                  {st.lists.length > 1 && <select className="wl-mv" aria-label={`Move ${r.symbol} to another list`} value="" onChange={(e) => { if (e.target.value) { wl.move(r.symbol, list.id, e.target.value); toast(`Moved ${r.symbol}.`); } }}><option value="">Move…</option>{st.lists.filter((l) => l.id !== list.id).map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}</select>}
                                  <AlertButton symbol={r.symbol} className="wl-ib" />
                                  <button type="button" className="wl-ib" onClick={() => { wl.remove(r.symbol, list.id); setSel((x) => x.filter((y) => y !== r.symbol)); }} aria-label={`Remove ${r.symbol} from this list`} title="Remove from this list"><Icon name="trash" /></button>
                                </td>
                              </tr>
                            );
                          })}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {sel.length > 0 && (
                <div className="wl-dock" role="region" aria-label="Selected stocks"><span><b>{sel.length}</b> selected</span>
                  <button className="btn primary" disabled={sel.length < 2} onClick={() => nav(`/compare?c=${sel.join(",")}`)}>{sel.length < 2 ? "Pick one more to compare" : "Compare selected"}</button>
                  <button className="lnk" onClick={() => setSel([])}>Clear</button></div>)}
              <Plain>Lists, notes and targets are saved in this browser. Targets are your own reminders, not predictions; FinLit does not tell you when to buy or sell.</Plain>
            </>)}
        </Gate>
      </div>
    </>
  );
}
