// Site-wide search (Ctrl K or "/"): stocks, mutual funds, ETFs and news in one box, with filter pills, recent visits, live prices,
// scores, logos and a preview of the highlighted result. Stocks are matched in the browser over every listed company (no wait); funds,
// ETFs and news are asked from the server after a short pause in typing. Information only: no buy or sell words anywhere.
import { useUniverse } from "../../lib/screener";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { useNavigate } from "react-router";
import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, prefetchStock, useSearchIndex, useSearchQuotes, useSummary, type SearchRow } from "../../lib/api";
import { etfGet, type EtfItem, type EtfList } from "../../lib/etf";
import { mfGet, type FundList, type FundRow, type HotList } from "../../lib/mf";
import { useScores } from "../../lib/mfScore";
import { ScoreChip } from "../../mf/ScoreCell";
import { useMyCompanies } from "../../lib/mycompanies";
import { visits, type Visit } from "../../lib/recentVisits";
import { MINUS, dateIN, nf } from "../../lib/format";
import {
  KIND_LABEL, TABS, allSections, amcLogo, flat, moversToday, quoteMap, searchStocks, stockItem, todayIST,
  type Band, type Item, type Quotes, type Section, type Tab,
} from "../../lib/globalSearch";
import { SearchFilters } from "../SearchFilters";
import { NO_FILTER, filterNoun, filterOn, filterPhrase, filterStocks, hasFilterData, indexFacets, passes, type StockFilter } from "../../lib/searchFilters";
import { useGold } from "../../lib/premium";
import { usePrismScores, type PrismScoreMap } from "../../lib/prismScores";
import { PrismChips, PrismPreviewScores, stateOf } from "./prismParts";
import { FlagIN, Hl, Logo, PriceChange, Range52, ScoreRing, Spark } from "./parts";
import "../../styles/search.css";

type News = { id: number; title: string; symbol: string | null; company: string | null; source: string | null; link: string | null; date: string; category: string | null };
const PLACEHOLDER: Record<Tab, string> = {
  all: "Search stocks, mutual funds, ETFs and news", stocks: "Company name, NSE symbol or BSE code", mf: "Fund name or fund house, e.g. flexi cap, SBI",
  etf: "ETF name or symbol, e.g. NIFTYBEES, gold", news: "Company or headline (3 letters or more)", global: "Global markets are coming soon",
};

const PAGE = 40;
/** Every listed company, largest first, those with a price ahead of those without (a preview build holds quotes for only a few). */
function allStocks(rows: readonly SearchRow[] | undefined, q: Map<string, { price: number | null }>): SearchRow[] {
  const all = (rows || []).filter((r) => !r[0].startsWith("^"));
  const priced = all.filter((r) => q.get(r[0])?.price != null);
  return priced.length >= 4 ? [...priced, ...all.filter((r) => q.get(r[0])?.price == null)] : all;
}

/** Symbols of the stock rows currently in view in the list (rows carry data-sym), measured on every change of the list and on scroll. */
function useVisibleSymbols(list: React.RefObject<HTMLDivElement | null>, items: Item[], on: boolean): string[] {
  const [seen, setSeen] = useState<string[]>([]);
  useEffect(() => {
    const root = list.current;
    if (!on || !root) { setSeen([]); return; }
    const measure = () => {
      const box = root.getBoundingClientRect(), out: string[] = [];
      root.querySelectorAll<HTMLElement>("[data-sym]").forEach((el) => { const r = el.getBoundingClientRect(); if (r.bottom > box.top - 120 && r.top < box.bottom + 120) out.push(el.dataset.sym!); });
      setSeen((old) => (old.length === out.length && old.every((s, i) => s === out[i]) ? old : out));
    };
    const t = window.setTimeout(measure, 30);
    root.addEventListener("scroll", measure, { passive: true });
    return () => { window.clearTimeout(t); root.removeEventListener("scroll", measure); };
  }, [list, items, on]);
  return seen;
}

function useDebounced<T>(v: T, ms: number): T {
  const [d, setD] = useState(v);
  useEffect(() => { const t = window.setTimeout(() => setD(v), ms); return () => window.clearTimeout(t); }, [v, ms]);
  return d;
}

/** Fund name without the plan and option words, so the Direct and Regular plans of one fund show once. */
const fundStem = (n: string) => n.replace(/\s*[-–(]\s*(direct|regular)\b.*$/i, "").replace(/\s*-\s*growth.*$/i, "").trim();
function fundItems(rows: FundRow[] | undefined, logos: Quotes["amcLogos"] | undefined): Item[] {
  const seen = new Map<string, Item>();
  for (const r of rows || []) {
    const stem = fundStem(r.name);
    if (seen.has(stem) && r.plan !== "Direct") continue;
    seen.set(stem, {
      kind: "mf", key: "mf:" + r.code, title: stem, sub: [r.amc?.replace(/ Mutual Fund$/i, ""), r.category?.replace(/^.*?-\s*/, "")].filter(Boolean).join(" · "),
      href: `/funds/${r.code}`, price: r.nav, chg: r.change, date: r.navDate, logo: amcLogo(r.amc, logos), tag: "Fund", meta: `${r.plan} · ${r.option || r.optionClass}`,
      metrics: [{ label: "1Y return", value: r.r1y }, { label: "5Y a year", value: r.r5y }],
    });
  }
  return [...seen.values()];
}
const etfItems = (rows: EtfItem[] | undefined, logos: Quotes["amcLogos"] | undefined): Item[] => (rows || []).map((r) => ({
  kind: "etf", key: "etf:" + r.symbol, title: r.name, sub: [r.symbol, r.categoryLabel].filter(Boolean).join(" · "), href: `/etfs/${encodeURIComponent(r.symbol)}`,
  price: r.price, chg: r.changePct, date: r.priceDate, logo: amcLogo(r.fundHouse, logos), tag: "ETF", meta: r.fundHouse || undefined,
  metrics: [{ label: "1Y return", value: r.ret1y }, { label: "From 52W high", value: r.from52 }],
}));
const newsItems = (rows: News[] | undefined): Item[] => (rows || []).map((n) => ({
  kind: "news", key: "news:" + n.id, title: n.title, sub: [n.company, dateIN(n.date, { day: "numeric", month: "short" })].filter(Boolean).join(" · "),
  href: n.link || (n.symbol ? `/stocks/${encodeURIComponent(n.symbol)}` : "/news"), external: !!n.link, tag: n.category || "News", meta: n.source || undefined,
}));

export function SearchOverlay({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [q, setQ] = useState("");
  const [tab, setTab] = useState<Tab>("all");
  const [sel, setSel] = useState(0);
  const [filter, setFilter] = useState<StockFilter>(NO_FILTER);   // sector and market-cap choices: they narrow the stock rows of the All and Stocks tabs
  const [menu, setMenu] = useState<"sector" | "cap" | null>(null);
  const [cap, setCap] = useState(PAGE);      // how many stocks are drawn: the list grows as it is scrolled, so every listed company can be reached
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const back = useRef<HTMLElement | null>(null);
  const nav = useNavigate();
  const qc = useQueryClient();
  const today = todayIST();

  const idx = useSearchIndex(true);
  const quotes = useSearchQuotes(open);
  // The quotes feed is the first choice; for a company it lacks, the screener's own row (price, day change, score) fills in so no row is empty.
  const uni = useUniverse(open);
  const qmap = useMemo(() => {
    const m = quoteMap(quotes.data);
    for (const r of uni.data?.rows || []) {
      const x = m.get(r.symbol);
      if (x && x.price != null) continue;
      if (r.price == null) continue;
      m.set(r.symbol, { price: r.price, chg: r.change_pct ?? null, date: x?.date ?? null, score: x?.score ?? r.overall ?? null, band: x?.band ?? (r.band as Band) ?? null, logo: x?.logo ?? null });
    }
    return m;
  }, [quotes.data, uni.data]);
  const logos = quotes.data?.amcLogos;
  const mine = useMyCompanies();
  const mineSet = useMemo(() => new Set(mine.symbols), [mine.symbols]);
  const bySym = useMemo(() => new Map((idx.data?.rows || []).map((r) => [r[0], r] as [string, SearchRow])), [idx.data]);
  const facets = useMemo(() => indexFacets(idx.data), [idx.data]);
  const canFilter = (tab === "all" || tab === "stocks") && hasFilterData(idx.data);   // an older server sends neither list: no controls then
  const fOn = canFilter && filterOn(filter);
  const keep = useMemo(() => (fOn ? (i: number) => passes(idx.data, i, filter) : undefined), [fOn, idx.data, filter]);
  const recent = useSyncExternalStore(visits.subscribe, () => JSON.stringify(visits.get()), () => "[]");

  const dq = useDebounced(q.trim(), 180);
  const wants = (k: Tab) => open && tab !== "global" && (tab === "all" || tab === k);
  const mfQ = useQuery<FundList>({ queryKey: ["gs", "mf", dq], queryFn: () => mfGet(`/api/mf?q=${encodeURIComponent(dq)}&size=12`), enabled: wants("mf") && dq.length >= 2, staleTime: 120_000, placeholderData: keepPreviousData, retry: 0 });
  const etfQ = useQuery<EtfList>({ queryKey: ["gs", "etf", dq], queryFn: () => etfGet(`/api/etf?q=${encodeURIComponent(dq)}&limit=8&sort=turnover&order=desc`), enabled: wants("etf") && dq.length >= 2, staleTime: 120_000, placeholderData: keepPreviousData, retry: 0 });
  const newsQ = useQuery<{ items: News[] }>({ queryKey: ["gs", "news", dq], queryFn: () => apiGet(`/api/feed?kind=news&q=${encodeURIComponent(dq)}&limit=8`), enabled: wants("news") && dq.length >= 3, staleTime: 120_000, placeholderData: keepPreviousData, retry: 0 });
  // what each tab shows before anything is typed
  const hotMf = useQuery<HotList>({ queryKey: ["mf", "hot"], queryFn: () => mfGet("/api/mf/hot"), enabled: open && tab === "mf" && !q, staleTime: 300_000, retry: 0 });
  const hotEtf = useQuery<EtfList>({ queryKey: ["gs", "etf-top"], queryFn: () => etfGet("/api/etf?limit=6"), enabled: open && tab === "etf" && !q, staleTime: 300_000, retry: 0 });
  const latest = useQuery<{ items: News[] }>({ queryKey: ["gs", "news-latest"], queryFn: () => apiGet("/api/feed?kind=news&limit=8"), enabled: open && tab === "news" && !q, staleTime: 120_000, retry: 0 });

  useEffect(() => {
    if (!open) return;
    back.current = document.activeElement as HTMLElement | null;
    setQ(""); setSel(0); setTab("all"); setFilter(NO_FILTER); setMenu(null);
    const t = window.setTimeout(() => input.current?.focus(), 20);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { window.clearTimeout(t); document.body.style.overflow = prev; back.current?.focus?.(); };
  }, [open]);

  const sections = useMemo<Section[]>(() => {
    const rows = idx.data?.rows;
    const s = q.trim();
    if (tab === "global") return [];
    const stockHits = (n: number) => searchStocks(rows, s, n, mineSet, keep);
    if (!s && fOn) {          // a filter replaces recent visits and movers: the list is the filtered companies, largest market value first
      const got = filterStocks(idx.data, "", filter, cap, mineSet);
      return got.rows.length ? [{ id: "filtered", title: `${filterNoun(filter)} · largest first`, items: got.rows.map((r) => stockItem(r, qmap, mineSet)) }] : [];
    }
    if (!s) {
      const vs = (JSON.parse(recent) as Visit[]).filter((v) => tab === "all" || (tab === "stocks" && v.k === "stock") || v.k === tab).map((v): Item | null => {
        if (v.k === "stock") { const r = bySym.get(v.id); return r ? stockItem(r, qmap, mineSet) : null; }
        return { kind: v.k, key: `${v.k}:${v.id}`, title: v.name, sub: v.sub || "", href: v.k === "mf" ? `/funds/${v.id}` : `/etfs/${encodeURIComponent(v.id)}`, tag: KIND_LABEL[v.k], logo: amcLogo(v.sub, logos) };
      }).filter((x): x is Item => !!x).slice(0, 6);
      const out: Section[] = [];
      if (vs.length) out.push({ id: "recent", title: "Recently visited", items: vs });
      if (tab === "all" || tab === "stocks") {
        const movers = moversToday(rows, qmap, today, 6).map((r) => stockItem(r, qmap, mineSet));
        if (movers.length) out.push({ id: "movers", title: "Moving most today · largest 200 companies", items: movers });
        const every = allStocks(rows, qmap);
        out.push({ id: "largest", title: `All listed companies · largest first`, items: every.slice(0, cap).map((r) => stockItem(r, qmap, mineSet)) });
      }
      if (tab === "mf") out.push({ id: "hot", title: "Largest funds by assets", items: fundItems(hotMf.data?.items, logos).slice(0, 8) });
      if (tab === "etf") out.push({ id: "hot", title: "Most traded ETFs", items: etfItems(hotEtf.data?.items, logos) });
      if (tab === "news") out.push({ id: "latest", title: "Latest company news", items: newsItems(latest.data?.items) });
      return out.filter((x) => x.items.length);
    }
    if (tab === "stocks") return [{ id: "stocks", title: "Stocks", items: stockHits(cap).map((h) => stockItem(h.row, qmap, mineSet)) }].filter((x) => x.items.length);
    const funds = dq.length >= 2 ? fundItems(mfQ.data?.items, logos) : [];
    const etfs = dq.length >= 2 ? etfItems(etfQ.data?.items, logos) : [];
    const news = dq.length >= 3 ? newsItems(newsQ.data?.items) : [];
    if (tab === "mf") return funds.length ? [{ id: "mf", title: "Mutual funds", items: funds }] : [];
    if (tab === "etf") return etfs.length ? [{ id: "etf", title: "ETFs", items: etfs }] : [];
    if (tab === "news") return news.length ? [{ id: "news", title: "News", items: news }] : [];
    const hits = stockHits(8);
    const best = hits[0] && hits[0].rank >= 880 ? stockItem(hits[0].row, qmap, mineSet) : null;
    return allSections(hits.map((h) => stockItem(h.row, qmap, mineSet)), best, funds, etfs, news);
  }, [idx.data, q, dq, tab, cap, filter, fOn, keep, qmap, mineSet, recent, bySym, logos, today, mfQ.data, etfQ.data, newsQ.data, hotMf.data, hotEtf.data, latest.data]);

  useEffect(() => { setCap(PAGE); }, [q, tab, open, filter]);
  const total = useMemo(() => {
    if (fOn && (tab === "stocks" || !q.trim())) return filterStocks(idx.data, q.trim(), filter, 0, mineSet).total;
    return tab === "stocks" && q.trim() ? searchStocks(idx.data?.rows, q.trim(), 1e6, mineSet).length : (idx.data?.rows.length ?? 0);
  }, [tab, q, idx.data, mineSet, fOn, filter]);
  const more = (tab === "stocks" || (tab === "all" && !q.trim())) && cap < total;
  const grow = () => { const el = list.current; if (more && el && el.scrollTop + el.clientHeight > el.scrollHeight - 500) setCap((c) => c + 60); };
  const items = useMemo(() => flat(sections), [sections]);
  const cur = items[Math.min(sel, Math.max(0, items.length - 1))];
  // Gold: the stored Prism scores of the rows on screen (and the highlighted one), asked in batches after a short pause.
  const gold = useGold();
  const mfCodes = useMemo(() => items.filter((it) => it.kind === "mf").map((it) => Number(it.key.split(":")[1])).filter((n) => n > 0).slice(0, 40), [items]);
  const fundScores = useScores(mfCodes, gold && mfCodes.length > 0);    // Gold only: one batch request for the funds on screen
  const scoreOf = useMemo(() => new Map((fundScores.data?.items || []).map((x) => [x.code, x])), [fundScores.data]);
  const seen = useVisibleSymbols(list, items, open && gold);
  const wanted = useMemo(() => (cur?.kind === "stock" ? [...seen, cur.sub] : seen), [seen, cur]);
  const prism = usePrismScores(wanted, open && gold && tab !== "global");
  const busy = (tab === "all" || tab === "mf") && dq.length >= 2 && mfQ.isFetching || (tab === "all" || tab === "etf") && dq.length >= 2 && etfQ.isFetching || (tab === "all" || tab === "news") && dq.length >= 3 && newsQ.isFetching;
  const waiting = q.trim() !== dq;

  useEffect(() => { setSel(0); list.current?.scrollTo?.({ top: 0 }); }, [q, tab, filter]);
  useEffect(() => { setMenu(null); }, [tab, open]);
  useEffect(() => { list.current?.querySelector<HTMLElement>(`[data-i="${sel}"]`)?.scrollIntoView({ block: "nearest" }); }, [sel]);
  useEffect(() => { if (cur?.kind === "stock" && cur.ready) prefetchStock(qc, cur.sub, 120); }, [cur, qc]);

  const pick = (it: Item, newTab = false) => {
    if (it.kind === "mf" || it.kind === "etf") visits.add({ k: it.kind, id: it.key.split(":")[1], name: it.title, sub: it.kind === "mf" ? it.sub.split(" · ")[0] : it.meta });
    if (it.external || newTab) { window.open(it.href, "_blank", "noopener,noreferrer"); if (!newTab) onClose(); return; }
    onClose(); nav(it.href);
  };
  const moveTab = (d: number) => { const i = TABS.findIndex((t) => t.key === tab); setTab(TABS[(i + d + TABS.length) % TABS.length].key); };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setSel((s) => Math.min(s + 1, items.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
    else if (e.key === "PageDown") { e.preventDefault(); setSel((s) => Math.min(s + 5, items.length - 1)); }
    else if (e.key === "PageUp") { e.preventDefault(); setSel((s) => Math.max(s - 5, 0)); }
    else if (e.key === "Enter" && cur) { e.preventDefault(); pick(cur, e.ctrlKey || e.metaKey); }
    else if (e.key === "Tab") { e.preventDefault(); moveTab(e.shiftKey ? -1 : 1); }
    else if ((e.key === "ArrowRight" || e.key === "ArrowLeft") && !q) { e.preventDefault(); moveTab(e.key === "ArrowRight" ? 1 : -1); }
    else if (e.altKey && canFilter && (e.code === "KeyS" || e.code === "KeyM")) { e.preventDefault(); setMenu((m) => { const w = e.code === "KeyS" ? "sector" : "cap"; return m === w ? null : w; }); }
    else if (e.key === "Escape") { e.preventDefault(); if (q) setQ(""); else onClose(); }
  };

  if (!open) return null;
  const n = items.length;
  const phrase = filterPhrase(filter), noun = filterNoun(filter, total), asked = q.trim() ? ` matching “${q.trim()}”` : "";
  const filteredList = fOn && (tab === "stocks" || !q.trim());
  const status = fOn && filteredList && total > 0 && !waiting ? (more ? `Showing ${Math.min(cap, total).toLocaleString("en-IN")} of ${total.toLocaleString("en-IN")} ${noun}${asked} · keep scrolling` : `Showing all ${total.toLocaleString("en-IN")} ${noun}${asked}`)
    : fOn && !filteredList && n && !waiting && !busy ? `${n} result${n === 1 ? "" : "s"} · stocks limited to ${phrase}`
    : tab === "global" ? "Global markets are coming soon." : more ? `Showing ${Math.min(cap, total).toLocaleString("en-IN")} of ${total.toLocaleString("en-IN")} companies · keep scrolling` : !q ? "" : waiting || busy ? "Searching…" : n ? `${n} result${n === 1 ? "" : "s"}` : "No matches";
  let i = -1;
  return (
    <>
      <div className="scrim gs-scrim" onClick={onClose} />
      <div className="gs" role="dialog" aria-modal="true" aria-label="Search stocks, funds, ETFs and news" onKeyDown={(e) => { if (e.key === "Escape" && e.target !== input.current) onClose(); }}>
        <div className="gs-top">
          <div className="gs-in">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
            <input ref={input} className="gs-q" value={q} placeholder={PLACEHOLDER[tab]} autoComplete="off" spellCheck={false} readOnly={tab === "global"}
              role="combobox" aria-expanded={n > 0} aria-controls="gsList" aria-autocomplete="list" aria-activedescendant={cur ? `gs-o-${sel}` : undefined}
              onChange={(e) => setQ(e.target.value)} onKeyDown={onKey} />
            {(waiting || busy) && q && <span className="gs-spin" aria-hidden="true" />}
            {q && <button type="button" className="gs-clear" onClick={() => { setQ(""); input.current?.focus(); }} aria-label="Clear the search">×</button>}
            <button type="button" className="gs-esc" onClick={onClose} aria-label="Close search">Esc</button>
          </div>
          <div className="gs-tabs" role="tablist" aria-label="What to search">
            {TABS.map((t) => (
              <button key={t.key} type="button" role="tab" aria-selected={tab === t.key} className={tab === t.key ? "on" : ""} tabIndex={-1}
                onClick={() => { setTab(t.key); input.current?.focus(); }}>
                {t.key === "global" && <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3Z" /></svg>}
                {t.label}{t.key === "global" && <em>Soon</em>}
              </button>
            ))}
          </div>
          {canFilter && <SearchFilters facets={facets} value={filter} onChange={setFilter} menu={menu} onMenu={setMenu} onDone={() => input.current?.focus()} />}
        </div>
        <div className="gs-body">
          <div className="gs-list" id="gsList" role="listbox" aria-label="Results" ref={list} onScroll={grow}>
            {tab === "global" ? <GlobalSoon /> : null}
            {tab !== "global" && idx.isLoading && <Skeleton />}
            {tab !== "global" && idx.isError && <p className="gs-empty">Search is unavailable right now. Please try again in a moment.</p>}
            {tab !== "global" && !idx.isLoading && !n && (
              fOn && !(q && (waiting || busy)) ? <FilterEmpty q={q.trim()} noun={filterNoun(filter, 2)} filter={filter} onFilter={(f) => { setFilter(f); input.current?.focus(); }} />
                : q ? (waiting || busy ? <Skeleton rows={3} /> : <NoMatch q={q} tab={tab} onTab={setTab} />)
                : tab === "mf" || tab === "etf" || tab === "news" ? <Skeleton rows={4} /> : <p className="gs-empty">Type a company, fund or ETF name.</p>
            )}
            {sections.map((sec) => (
              <div key={sec.id} role="group" aria-labelledby={`gs-h-${sec.id}`} className="gs-sec">
                <div className="gs-h" id={`gs-h-${sec.id}`}>
                  <span>{sec.title}</span>
                  {sec.id === "recent" && <button type="button" onClick={() => visits.clear()}>Clear</button>}
                  {sec.more && tab === "all" && <button type="button" onClick={() => setTab(sec.more!.tab)}>{sec.more.label} →</button>}
                </div>
                {sec.items.map((it) => { i += 1; const me = i; return <Row key={sec.id + it.key} fs={gold && it.kind === "mf" ? scoreOf.get(Number(it.key.split(":")[1])) : undefined} it={it} gold={gold} prism={prism} q={q.trim()} today={today} id={`gs-o-${me}`} active={me === sel} index={me} best={sec.id === "best"} onHover={() => setSel(me)} onPick={pick} />; })}
              </div>
            ))}
          </div>
          {cur && tab !== "global" && <Preview it={cur} gold={gold} prism={prism} today={today} onOpen={() => pick(cur)} onClose={onClose} />}
        </div>
        <div className="gs-foot">
          <span className="gs-keys"><kbd>↑</kbd><kbd>↓</kbd> move <kbd>Enter</kbd> open <kbd>Tab</kbd> switch filter <kbd>Esc</kbd> {q ? "clear" : "close"}</span>
          <span className="gs-src" role="status" aria-live="polite">{status || (idx.data ? `${idx.data.rows.length.toLocaleString("en-IN")} listed companies · information only, not advice` : "")}</span>
        </div>
      </div>
    </>
  );
}

function Row({ fs, it, gold, prism, q, today, id, active, index, best, onHover, onPick }: { it: Item; gold: boolean; prism: PrismScoreMap; q: string; today: string; id: string; active: boolean; index: number; best: boolean; onHover: () => void; onPick: (it: Item, newTab?: boolean) => void; fs?: import("../../lib/mfScore").ScoreItem }) {
  return (
    <div id={id} data-i={index} data-sym={gold && it.kind === "stock" ? it.sub : undefined} role="option" aria-selected={active} className={`gs-row k-${it.kind}${gold && it.kind === "stock" ? " pz" : ""}${active ? " on" : ""}${best ? " best" : ""}`} onMouseMove={active ? undefined : onHover}
      onClick={(e) => onPick(it, e.ctrlKey || e.metaKey)} onAuxClick={(e) => { if (e.button === 1) onPick(it, true); }}>
      <Logo src={it.logo} name={it.title} kind={it.kind} size={best ? 46 : 40} />
      <span className="gs-main">
        <span className="gs-t"><Hl text={it.title} q={q} />{fs && <ScoreChip item={fs} />}</span>
        <span className="gs-s">
          {it.kind !== "news" && <FlagIN />}
          {it.kind === "stock" ? <span className="gs-tk"><Hl text={it.sub} q={q} /></span> : <span className="gs-sub">{it.sub}</span>}
          {it.mine && <span className="gs-mine">Yours</span>}
          {it.kind === "stock" && it.ready && <span className="gs-ready" title="Report ready: opens instantly" aria-label="report ready" />}
        </span>
      </span>
      {it.kind !== "news" && <PriceChange price={it.price} chg={it.chg} date={it.date} today={today} unit={it.kind === "mf" ? "NAV ₹" : "₹"} />}
      {it.kind === "stock" ? (gold ? <PrismChips state={stateOf(prism, it.sub)} /> : <ScoreRing score={it.score} band={it.band} />) : it.kind !== "news" ? <span className="gs-score gs-none gs-metric">{metricBadge(it)}</span> : null}
      <span className={`gs-tag t-${it.kind}`}>{it.kind === "news" ? (it.tag || "News") : KIND_LABEL[it.kind]}{it.external && <svg viewBox="0 0 24 24" aria-label="opens the source"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></svg>}</span>
    </div>
  );
}

function metricBadge(it: Item) {
  const m = it.metrics?.[0];
  if (!m || m.value == null) return <><span className="gs-ring">{MINUS}</span><span className="gs-band">1Y return</span></>;
  return <><span className={`gs-ring gs-pct ${m.value >= 0 ? "up" : "down"}`}>{m.value < 0 ? MINUS : "+"}{nf(m.value, m.value >= 100 || m.value <= -100 ? 0 : 1)}%</span><span className="gs-band">{m.label}</span></>;
}

function Preview({ it, gold, prism, today, onOpen, onClose }: { it: Item; gold: boolean; prism: PrismScoreMap; today: string; onOpen: () => void; onClose: () => void }) {
  const nav = useNavigate();
  const ready = it.kind === "stock" && !!it.ready;
  const s = useSummary(it.sub, ready);
  const sum = ready && s.data && s.data.meta?.symbol === it.sub ? s.data : null;
  const up = (it.chg ?? 0) >= 0;
  return (
    <aside className="gs-pre" aria-label="Preview">
      <div className="gs-pre-h">
        <Logo src={it.logo} name={it.title} kind={it.kind} size={56} />
        <div><b>{it.title}</b><small>{it.kind === "stock" ? [it.sub, sum?.profile.sector].filter(Boolean).join(" · ") : it.sub}</small></div>
      </div>
      {it.kind !== "news" && <div className="gs-pre-px"><PriceChange price={sum?.quote.price ?? it.price} chg={sum?.quote.changePct ?? it.chg} date={it.date} today={today} unit={it.kind === "mf" ? "NAV ₹" : "₹"} /></div>}
      {sum && <Spark values={sum.sparkline.c} up={up} />}
      {sum && <Range52 low={sum.range52.low} high={sum.range52.high} price={sum.quote.price} />}
      {it.kind === "stock" && gold && <PrismPreviewScores state={stateOf(prism, it.sub)} />}
      {it.kind === "stock" && !gold && (
        <div className="gs-pre-sc">
          <ScoreRing score={it.score ?? sum?.score.overall} band={it.band ?? (sum?.score.band.key as Item["band"])} size={54} />
          {sum?.score.pillars?.length ? (
            <ul className="gs-pil">{sum.score.pillars.slice(0, 5).map((p) => <li key={p.key}><span>{p.label}</span><i><em style={{ width: `${p.score ?? 0}%` }} /></i><b>{p.score ?? MINUS}</b></li>)}</ul>
          ) : <p className="gs-pre-note">{it.band === "locked" ? "The score and its five pillars are part of the Silver plan." : ready ? "Loading the report…" : "The full report is built the first time it is opened."}</p>}
        </div>
      )}
      {(it.kind === "mf" || it.kind === "etf") && (
        <div className="gs-pre-m">{(it.metrics || []).map((m) => <div key={m.label}><span>{m.label}</span><b className={m.value == null ? "" : m.value >= 0 ? "up" : "down"}>{m.value == null ? MINUS : `${m.value < 0 ? MINUS : "+"}${nf(m.value, 2)}%`}</b></div>)}{it.meta && <p>{it.meta}</p>}</div>
      )}
      {it.kind === "news" && <p className="gs-pre-note">{it.meta ? `Source: ${it.meta}. ` : ""}{it.external ? "Opens the original announcement in a new tab." : "Opens the company's report."}</p>}
      <button type="button" className="gs-open" onClick={onOpen}>{it.kind === "news" ? "Open" : it.kind === "stock" ? "Open the full report" : it.kind === "mf" ? "Open the fund" : "Open the ETF"} <span aria-hidden="true">→</span></button>
      {it.kind === "stock" && gold && <button type="button" className="gs-open gs-open-2" onClick={() => { onClose(); nav(`/prism/${encodeURIComponent(it.sub)}`); }}>Open Prism <span aria-hidden="true">→</span></button>}
      <p className="gs-pre-f">Information only, not advice.</p>
    </aside>
  );
}

function Skeleton({ rows = 5 }: { rows?: number }) {
  return <div className="gs-skel" aria-hidden="true">{Array.from({ length: rows }, (_, k) => <div key={k} className="gs-sk"><i /><span><b /><em /></span><u /></div>)}</div>;
}

function NoMatch({ q, tab, onTab }: { q: string; tab: Tab; onTab: (t: Tab) => void }) {
  return (
    <div className="gs-none-box">
      <b>No {tab === "all" ? "results" : TABS.find((t) => t.key === tab)?.label.toLowerCase()} for “{q}”</b>
      <p>Check the spelling, or try a ticker such as RELIANCE or a fund house such as SBI.</p>
      {tab !== "all" && <button type="button" onClick={() => onTab("all")}>Search everything instead</button>}
    </div>
  );
}

/** Nothing passes the sector / market-cap choice (with or without a typed query): say so plainly and offer the way out. */
function FilterEmpty({ q, noun, filter, onFilter }: { q: string; noun: string; filter: StockFilter; onFilter: (f: StockFilter) => void }) {
  return (
    <div className="gs-none-box" role="status">
      <b>{q ? `No ${noun} match “${q}”` : `No ${noun} in the list`}</b>
      <p>{q ? "Check the spelling, or widen the filters. " : ""}Companies with no sector or no market value on file are left out while that filter is chosen.</p>
      <span className="gs-none-acts">
        {filter.sector && filter.cap && <button type="button" onClick={() => onFilter({ ...filter, sector: null })}>Clear sector</button>}
        {filter.sector && filter.cap && <button type="button" onClick={() => onFilter({ ...filter, cap: null })}>Clear market cap</button>}
        <button type="button" onClick={() => onFilter(NO_FILTER)}>Clear {filter.sector && filter.cap ? "both" : "filter"}</button>
      </span>
    </div>
  );
}

function GlobalSoon() {
  return (
    <div className="gs-global">
      <svg className="gs-globe" viewBox="0 0 120 120" aria-hidden="true">
        <circle cx="60" cy="60" r="44" /><ellipse cx="60" cy="60" rx="18" ry="44" /><ellipse cx="60" cy="60" rx="34" ry="44" /><path d="M16 60h88M22 38h76M22 82h76" />
        <circle className="gs-dot" cx="78" cy="44" r="3.5" /><circle className="gs-dot d2" cx="42" cy="70" r="3.5" /><circle className="gs-dot d3" cx="88" cy="74" r="3.5" />
      </svg>
      <b>Global markets are on the way</b>
      <p>Companies and funds listed outside India will appear here, searched the same way. Today the search covers Indian stocks, mutual funds, ETFs and company news.</p>
    </div>
  );
}
