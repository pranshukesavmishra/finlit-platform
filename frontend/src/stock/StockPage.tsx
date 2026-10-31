import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { canon } from "../lib/aliases";
import { visits } from "../lib/recentVisits";
import { recents } from "../lib/mycompanies";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError, useSearchIndex, usePrice, useSection, useSummary, type Events, type Financials, type Ownership, type Peers, type Ratios, type Segments } from "../lib/api";
import { Icon } from "../lib/icons";
import { signed, nf } from "../lib/format";
import { OpenAccess } from "../components/Gate";
import { useAuth } from "../lib/auth";
import { Hero } from "./Hero";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { FinancialsSection, Notes, PriceSection } from "./Sections";
import { InsightsSection, PeersSection, RatiosSection } from "./Sections3";
import { QuarterSection, TrendsSection } from "./Sections4";
import { ChartLab } from "./ChartLab";
import { PlFlagsLayer } from "./PlFlagsLayer";
import { DiscussionLink } from "../components/DiscussionLink";
import { BusinessSection, DividendsSection, MethodSection, OwnershipSection } from "./Sections2";
import { useLeadership } from "../lib/leadership";
import { LeadershipSection } from "./Leadership";
import { PlansBand } from "../pages/Plans";
import { useDocTitle } from "../lib/title";
import { navFor } from "../lib/sectionNav";
import { SectionsMenu } from "./SectionsMenu";
import { PreparingReport, type PreparingMode } from "./PreparingReport";


export function StockPage() {
  const { symbol: raw = "" } = useParams();
  const symbol = canon(raw.toUpperCase());
  const nav = useNavigate();
  const queryClient = useQueryClient();
  useEffect(() => { if (symbol !== raw.toUpperCase()) nav(`/stocks/${symbol}`, { replace: true }); }, [symbol, raw]); // eslint-disable-line react-hooks/exhaustive-deps
  const { showcase } = useAuth();
  const sum = useSummary(symbol);
  const s = sum.data;
  const ready = !!s;
  const names = useSearchIndex(!s);   // the company's name for the waiting page, before its report exists (the list is cached for the search box anyway)
  // A report stored with its key numbers while ownership, peers, segments and announcements are still being fetched: ask again every 2.5 s (for up to 2 minutes) until it is complete.
  const partial = !!s?.meta.partial;
  useEffect(() => {
    if (!partial) return;
    const t0 = Date.now();
    const id = setInterval(() => { if (Date.now() - t0 > 120_000) clearInterval(id); else queryClient.invalidateQueries({ queryKey: ["stock", symbol] }); }, 2500);
    return () => clearInterval(id);
  }, [partial, symbol]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (s?.meta.symbol) { recents.add(s.meta.symbol); visits.add({ k: "stock", id: s.meta.symbol, name: s.profile.name }); queryClient.invalidateQueries({ queryKey: ["my-companies"] }); } }, [s?.meta.symbol]); // eslint-disable-line react-hooks/exhaustive-deps
  const ratios = useSection<Ratios>(symbol, "ratios", ready).data;
  const fin = useSection<Financials>(symbol, "financials", ready).data;
  const own = useSection<Ownership>(symbol, "ownership", ready).data;
  const peers = useSection<Peers>(symbol, "peers", ready).data;
  const seg = useSection<Segments>(symbol, "segments", ready).data;
  const events = useSection<Events>(symbol, "events", ready).data;
  const lead = useLeadership(symbol, ready).data;
  const navItems = useMemo(() => navFor(!!(lead && (lead.available || lead.display))), [lead]);   // no pill for a section that is switched off
  const tech = usePrice(symbol, "1Y", ready).data?.technical;   // waits for the summary, so a new stock is asked for once, not twice
  useDocTitle(s ? `${s.profile.name} research` : `${symbol} research`, s ? `FinLit research report for ${s.profile.name}: score ${s.score.overall ?? "n/a"}, financials, ratios, ownership and peers.` : undefined);

  const [active, setActive] = useState<string | null>(null);
  const [stuck, setStuck] = useState(false);
  const idrow = useRef<HTMLDivElement>(null);
  const links = useRef<HTMLDivElement>(null);
  const pill = useRef<HTMLSpanElement>(null);
  const [edge, setEdge] = useState({ l: false, r: false });   // more sections beyond the left / right end of the bar: arrows and a fade say so
  useEffect(() => {
    const el = links.current; if (!el) return;
    const upd = () => setEdge({ l: el.scrollLeft > 4, r: el.scrollLeft + el.clientWidth < el.scrollWidth - 4 });
    upd(); el.addEventListener("scroll", upd, { passive: true });
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(upd) : null; ro?.observe(el);
    return () => { el.removeEventListener("scroll", upd); ro?.disconnect(); };
  }, [s]);
  const slide = (d: number) => links.current?.scrollBy({ left: d * links.current.clientWidth * 0.6, behavior: "smooth" });

  useEffect(() => {
    if (!s) return;
    const vis = new Map<string, boolean>();
    const io = new IntersectionObserver((es) => { es.forEach((e) => vis.set(e.target.id, e.isIntersecting)); const f = navItems.find(([id]) => vis.get(id)); setActive(f ? f[0] : null); }, { rootMargin: "-130px 0px -55% 0px" });
    navItems.forEach(([id]) => { const n = document.getElementById(id); if (n) io.observe(n); });
    const hero = document.querySelector(".idrow");
    const io2 = new IntersectionObserver(([e]) => setStuck(!e.isIntersecting), { rootMargin: "-130px 0px 0px 0px" });
    if (hero) io2.observe(hero);
    return () => { io.disconnect(); io2.disconnect(); };
  }, [s, ratios, fin, own, peers, seg, events, navItems]);

  useEffect(() => {
    const a = links.current?.querySelector<HTMLAnchorElement>(`a[data-s="${active}"]`);
    if (!pill.current) return;
    if (!a) { pill.current.style.width = "0px"; return; }
    pill.current.style.width = a.offsetWidth + "px"; pill.current.style.transform = `translateX(${a.offsetLeft}px)`;
    links.current?.scrollTo({ left: Math.max(0, a.offsetLeft - links.current.clientWidth / 2 + a.offsetWidth / 2), behavior: "smooth" });
  }, [active]);

  // The Prism section hides itself when there is nothing to show; its links then open the Prism page instead.
  const jump = (id: string) => { const t = document.getElementById(id); if (t) window.scrollTo({ top: t.getBoundingClientRect().top + scrollY - 124, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }); else if (id === "prism") nav(`/prism/${encodeURIComponent(symbol)}`); };
  const q = useMemo(() => s?.quote, [s]);

  const err = (sum.error ?? sum.failureReason) as ApiError | null;   // while it retries, the last answer is the failure reason (it carries the progress)
  const st = err?.status;
  const mode: PreparingMode | null = sum.isLoading
    ? (st === 202 ? "building" : st === 429 ? "busy" : "loading")
    : sum.isError && (st === 202 || st === 429) ? "gaveUp"        // stopped asking after about 45 s: a visible end with "Try again", not a dead page
    : sum.isError && (st ?? 0) >= 500 ? "failed"
    : null;
  if (mode) {
    const known = names.data?.rows.find((r) => r[0] === symbol);
    return <PreparingReport symbol={symbol} name={err?.body.company?.name ?? known?.[1] ?? null} sector={err?.body.company?.sector} mode={mode} done={err?.body.done} total={err?.body.total} onRetry={() => sum.refetch()} />;
  }
  if (sum.isError || !s) {
    const st = (sum.error as ApiError | null)?.status;
    const demo = (sum.error as ApiError | null)?.body?.status === "demo";
    if (demo) return <div className="wrap state"><h2>This demo includes the RELIANCE report</h2><p>The live site opens every listed stock. Try RELIANCE to see the full report.</p><Link className="btn primary" to="/stocks/RELIANCE">Open the RELIANCE report</Link></div>;
    return <div className="wrap state"><h2>{st === 404 ? `We couldn't find “${symbol}”` : "This report is unavailable right now"}</h2><p>{st === 404 ? "Check the ticker, or search by company name." : "Please try again in a moment."}</p><Link className="btn primary" to="/research">Browse research</Link></div>;
  }
  return (
    <OpenAccess.Provider value={showcase.includes(symbol)}>
    <>
      <Hero s={s} ratios={ratios} fin={fin} jump={jump} />
      <div className={"secnav" + (stuck ? " stuck" : "")} id="secnav">
        <div className="wrap">
          <div className="mini" aria-hidden="true"><span className="bd">{s.profile.name.split(" ").slice(0, 2).map((w) => w[0]).join("")}</span><b>{s.profile.nse}</b><span>₹{nf(q?.price ?? 0)}</span><span className={(q?.changePct ?? 0) >= 0 ? "pos" : "neg"}>{signed(q?.changePct)}</span><span className="sc">{s.score.overall ?? "—"}</span></div>
          <SectionsMenu items={navItems} active={active} onPick={jump} />
          <div className={"snav" + (edge.l ? " edge-l" : "") + (edge.r ? " edge-r" : "")}>
          {edge.l && <button type="button" className="snav-arrow" aria-label="Earlier sections" onClick={() => slide(-1)}>‹</button>}
          <nav ref={links} aria-label="Sections"><span className="pill" ref={pill} />{navItems.map(([id, label, ic]) => <a key={id} data-s={id} href={`#${id}`} className={active === id ? "active" : ""} aria-current={active === id ? "true" : undefined} onClick={(e) => { e.preventDefault(); jump(id); }}><Icon name={ic} />{label}</a>)}</nav>
          {edge.r && <button type="button" className="snav-arrow" aria-label="More sections" onClick={() => slide(1)}>›</button>}
          </div>
        </div>
      </div>
      <div className="wrap">
        <div ref={idrow} />
        {/* What the company does comes first: someone who has never heard of it starts here, then the score, then the numbers. */}
        <ErrorBoundary section="This section"><BusinessSection s={s} /></ErrorBoundary>
        <ErrorBoundary section="This section"><Notes s={s} /></ErrorBoundary>
        <ErrorBoundary section="This section"><PriceSection s={s} symbol={symbol} ratios={ratios} /></ErrorBoundary>
        <PlFlagsLayer f={fin} lender={!!s.dataQuality.isBank} />
        <ErrorBoundary section="This section"><QuarterSection f={fin} /></ErrorBoundary>
        <ErrorBoundary section="This section"><FinancialsSection f={fin} /></ErrorBoundary>
        <ErrorBoundary section="This section"><TrendsSection f={fin} seg={seg} e={events} r={ratios} /></ErrorBoundary>
        <ErrorBoundary section="This section"><ChartLab s={s} symbol={symbol} f={fin} r={ratios} o={own} e={events} p={peers} /></ErrorBoundary>
        <ErrorBoundary section="This section"><RatiosSection r={ratios} lender={!!s.dataQuality.isBank} /></ErrorBoundary>
        <ErrorBoundary section="This section"><OwnershipSection o={own} /></ErrorBoundary>
        <ErrorBoundary section="This section"><PeersSection p={peers} self={symbol} s={s} /></ErrorBoundary>
        <ErrorBoundary section="This section"><InsightsSection s={s} r={ratios} seg={seg} tech={tech} /></ErrorBoundary>
        <ErrorBoundary section="This section"><DividendsSection e={events} price={q?.price} r={ratios} /></ErrorBoundary>
        <DiscussionLink symbol={symbol} />
        <ErrorBoundary section="This section"><MethodSection s={s} /></ErrorBoundary>
        <ErrorBoundary section="This section"><LeadershipSection symbol={symbol} name={s.profile.name} /></ErrorBoundary>
      </div>
      <PlansBand id="plans" />
      {partial && <div className="prep-toast" role="status"><i aria-hidden="true" />Ownership, peers, segments and announcements are still loading. Everything above is final.</div>}
    </>
    </OpenAccess.Provider>
  );
}
