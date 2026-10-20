import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { canon } from "../lib/aliases";
import { ApiError, usePrice, useSection, useSummary, type Events, type Financials, type Ownership, type Peers, type Ratios, type Segments } from "../lib/api";
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
import { BusinessSection, DividendsSection, MethodSection, OwnershipSection } from "./Sections2";
import { PlansBand } from "../pages/Plans";
import { useDocTitle } from "../lib/title";

const NAV: [string, string, string][] = [["business", "Company", "building"], ["notes", "Scorecard", "notes"], ["price", "Price", "line"], ["quarter", "Quarter", "notes"], ["financials", "Financials", "bars"], ["trends", "Trends", "line"], ["ratios", "Ratios", "gauge"], ["ownership", "Ownership", "pie"], ["peers", "Peers", "layers"], ["insights", "Insights", "crown"], ["dividends", "Dividends", "coins"], ["method", "Pros & cons", "info"], ["plans", "Plans", "medal"]];

export function StockPage() {
  const { symbol: raw = "" } = useParams();
  const symbol = canon(raw.toUpperCase());
  const nav = useNavigate();
  useEffect(() => { if (symbol !== raw.toUpperCase()) nav(`/stocks/${symbol}`, { replace: true }); }, [symbol, raw]); // eslint-disable-line react-hooks/exhaustive-deps
  const { showcase } = useAuth();
  const sum = useSummary(symbol);
  const s = sum.data;
  const ready = !!s;
  const ratios = useSection<Ratios>(symbol, "ratios", ready).data;
  const fin = useSection<Financials>(symbol, "financials", ready).data;
  const own = useSection<Ownership>(symbol, "ownership", ready).data;
  const peers = useSection<Peers>(symbol, "peers", ready).data;
  const seg = useSection<Segments>(symbol, "segments", ready).data;
  const events = useSection<Events>(symbol, "events", ready).data;
  const tech = usePrice(symbol, "1Y", ready).data?.technical;   // waits for the summary, so a new stock is asked for once, not twice
  useDocTitle(s ? `${s.profile.name} research` : `${symbol} research`, s ? `FinLit research report for ${s.profile.name}: score ${s.score.overall ?? "n/a"}, financials, ratios, ownership and peers.` : undefined);

  const [active, setActive] = useState<string | null>(null);
  const [stuck, setStuck] = useState(false);
  const idrow = useRef<HTMLDivElement>(null);
  const links = useRef<HTMLDivElement>(null);
  const pill = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!s) return;
    const vis = new Map<string, boolean>();
    const io = new IntersectionObserver((es) => { es.forEach((e) => vis.set(e.target.id, e.isIntersecting)); const f = NAV.find(([id]) => vis.get(id)); setActive(f ? f[0] : null); }, { rootMargin: "-130px 0px -55% 0px" });
    NAV.forEach(([id]) => { const n = document.getElementById(id); if (n) io.observe(n); });
    const hero = document.querySelector(".idrow");
    const io2 = new IntersectionObserver(([e]) => setStuck(!e.isIntersecting), { rootMargin: "-130px 0px 0px 0px" });
    if (hero) io2.observe(hero);
    return () => { io.disconnect(); io2.disconnect(); };
  }, [s, ratios, fin, own, peers, seg, events]);

  useEffect(() => {
    const a = links.current?.querySelector<HTMLAnchorElement>(`a[data-s="${active}"]`);
    if (!pill.current) return;
    if (!a) { pill.current.style.width = "0px"; return; }
    pill.current.style.width = a.offsetWidth + "px"; pill.current.style.transform = `translateX(${a.offsetLeft}px)`;
    links.current?.scrollTo({ left: Math.max(0, a.offsetLeft - links.current.clientWidth / 2 + a.offsetWidth / 2), behavior: "smooth" });
  }, [active]);

  const jump = (id: string) => { const t = document.getElementById(id); if (t) window.scrollTo({ top: t.getBoundingClientRect().top + scrollY - 124, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" }); };
  const q = useMemo(() => s?.quote, [s]);

  const waiting = sum.isError && [202, 429].includes((sum.error as ApiError).status);
  if (sum.isLoading || waiting) {
    const queued = sum.isError || sum.failureCount > 0;
    const busy = (sum.error as ApiError | null)?.status === 429 || (sum.failureReason as ApiError | null)?.status === 429;
    const gaveUp = waiting && !sum.isFetching;   // stopped asking after several minutes: offer a manual retry instead of a dead end
    return <div className="wrap state" role="status"><div className="skeleton" style={{ height: 14, width: 220, margin: "0 auto 18px" }} /><h2>{queued ? "Preparing this report" : "Loading the report"}</h2>
      <p>{!queued ? "One moment." : busy ? "Many reports are being prepared right now. Yours is in the queue and will open by itself." : gaveUp ? "This is taking longer than usual. The report is still being built." : "This company hasn't been opened yet, so we are building its report from the latest filings. It usually takes under half a minute and opens by itself."}</p>
      {gaveUp && <button className="btn primary" onClick={() => sum.refetch()}>Check again</button>}</div>;
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
          <nav ref={links} aria-label="Sections"><span className="pill" ref={pill} />{NAV.map(([id, label, ic]) => <a key={id} data-s={id} href={`#${id}`} className={active === id ? "active" : ""} aria-current={active === id ? "true" : undefined} onClick={(e) => { e.preventDefault(); jump(id); }}><Icon name={ic} />{label}</a>)}</nav>
        </div>
      </div>
      <div className="wrap">
        <div ref={idrow} />
        {/* What the company does comes first: someone who has never heard of it starts here, then the score, then the numbers. */}
        <ErrorBoundary section="This section"><BusinessSection s={s} /></ErrorBoundary>
        <ErrorBoundary section="This section"><Notes s={s} /></ErrorBoundary>
        <ErrorBoundary section="This section"><PriceSection s={s} symbol={symbol} ratios={ratios} /></ErrorBoundary>
        <ErrorBoundary section="This section"><QuarterSection f={fin} /></ErrorBoundary>
        <ErrorBoundary section="This section"><FinancialsSection f={fin} /></ErrorBoundary>
        <ErrorBoundary section="This section"><TrendsSection f={fin} seg={seg} e={events} r={ratios} /></ErrorBoundary>
        <ErrorBoundary section="This section"><ChartLab s={s} symbol={symbol} f={fin} r={ratios} o={own} e={events} p={peers} /></ErrorBoundary>
        <ErrorBoundary section="This section"><RatiosSection r={ratios} lender={!!s.dataQuality.isBank} /></ErrorBoundary>
        <ErrorBoundary section="This section"><OwnershipSection o={own} /></ErrorBoundary>
        <ErrorBoundary section="This section"><PeersSection p={peers} self={symbol} s={s} /></ErrorBoundary>
        <ErrorBoundary section="This section"><InsightsSection s={s} r={ratios} seg={seg} tech={tech} /></ErrorBoundary>
        <ErrorBoundary section="This section"><DividendsSection e={events} price={q?.price} r={ratios} /></ErrorBoundary>
        <ErrorBoundary section="This section"><MethodSection s={s} r={ratios} /></ErrorBoundary>
      </div>
      <PlansBand id="plans" />
    </>
    </OpenAccess.Provider>
  );
}
