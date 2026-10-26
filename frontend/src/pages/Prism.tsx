// FinLit Prism (Gold): /prism finds a company, /prism/:symbol shows its stored rating or calculates one.
// Replaces the upstream admin "Premium Report" page: no CMS token, no browser-held snapshot, no polling a background job.
// The research API keeps the signed snapshot; the browser gets a PrismReport and downloads the PDF from the API.
import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { Icon } from "../lib/icons";
import { Gate } from "../components/Gate";
import { PrismReportView, ReportSkeleton } from "../components/prism/ReportView";
import { LandingBody, PRISM_WHAT, Picker } from "../components/prism/pzr/Landing";
import { useAuth } from "../lib/auth";
import { useGold } from "../lib/premium";
import {
  PRISM_NAME, PRISM_NOTE, cleanSymbol, downloadPrismPdf, prismProblem, pushPrismRecent, statementWord,
  useGeneratePrism, useLatestPrism, usePrismStatus, type PrismReport, type Problem, type Statement,
} from "../lib/prism";
import { useDocTitle } from "../lib/title";
import { PremiumHead } from "./Premium";
import example from "../lib/__fixtures__/prismReport.json";

function Head({ children }: { children?: React.ReactNode }) {
  return <PremiumHead eyebrow="Gold · Financial health" title={PRISM_NAME}>{children ?? <p>A company's financial health, split into four parts the way a prism splits light. {PRISM_NOTE}</p>}</PremiumHead>;
}

function Locked({ symbol }: { symbol?: string }) {
  return (
    <>
      <Head />
      <div className="wrap" style={{ paddingBottom: 56 }}>
        <Gate tier="gold" title={`${PRISM_NAME} is part of Gold`} points={PRISM_WHAT}>
          <p className="pzr-small" style={{ margin: "0 0 12px" }}>Example only: a fictional company{symbol ? `, not ${symbol}` : ""}.</p>
          <div className="pzr-preview"><PrismReportView example report={example as unknown as PrismReport} /></div>
        </Gate>
      </div>
    </>
  );
}

function Landing() {
  useDocTitle(PRISM_NAME, "FinLit Prism: a company's financial health in four parts, with a PDF. For Gold members.");
  const [statement, setStatement] = useState<Statement>("consolidated");
  return <><Head /><LandingBody statement={statement} setStatement={setStatement} /></>;
}

/* ------------------------------------------------------------------ one company */
const Problem_ = ({ p, onRetry, retryLabel = "Try again" }: { p: Problem; onRetry?: () => void; retryLabel?: string }) => (
  <div className={"pzr-problem " + p.kind} role="alert"><Icon name="alert" /><div><b>{p.title}</b><p>{p.text}</p>{onRetry && <button type="button" className="btn" onClick={onRetry}>{retryLabel}</button>}</div></div>
);

function Working({ since }: { since: number }) {
  const [s, setS] = useState(0);
  useEffect(() => { const t = setInterval(() => setS(Math.round((Date.now() - since) / 1000)), 1000); return () => clearInterval(t); }, [since]);
  return (
    <div className="card pzr-card pzr-work" role="status" aria-live="polite">
      <span className="pzr-spin" aria-hidden="true" />
      <div><b>Calculating the rating…</b><p>Reading financial statements and prices, and checking the inputs. This can take up to two minutes; keep this page open. {s > 0 && <span className="pzr-small">{s}s so far.</span>}</p></div>
    </div>
  );
}

function CompanyView({ symbol, statement }: { symbol: string; statement: Statement }) {
  const latest = useLatestPrism(symbol, statement), gen = useGeneratePrism(), status = usePrismStatus();
  const [downloading, setDownloading] = useState(false), [pdfErr, setPdfErr] = useState<Problem | null>(null), [started, setStarted] = useState(0);
  useEffect(() => { pushPrismRecent(symbol); }, [symbol]);
  const report = latest.data ?? null;
  const down = status.data && !status.data.available;
  const run = (refresh: boolean) => { setPdfErr(null); setStarted(Date.now()); gen.mutate({ symbol, statement, refresh }); };
  const download = async () => {
    if (!report) return;
    setDownloading(true); setPdfErr(null);
    try { await downloadPrismPdf(report); } catch (e) { setPdfErr(prismProblem(e)); } finally { setDownloading(false); }
  };
  useDocTitle(report ? `${report.company.name} ${PRISM_NAME}` : `${symbol} ${PRISM_NAME}`, `FinLit Prism financial-health rating for ${symbol}.`);
  const busy = gen.isPending;
  const expired = pdfErr?.kind === "expired";
  return (
    <div aria-busy={busy || latest.isLoading}>
      {down && <div className="pzr-problem unavailable" role="note"><Icon name="alert" /><div><b>{PRISM_NAME} is not connected right now</b><p>{status.data?.reason || "The rating service is unavailable."} Stored ratings may still open.</p></div></div>}
      {latest.isLoading && <ReportSkeleton />}
      {latest.isError && !busy && <Problem_ p={prismProblem(latest.error)} onRetry={() => latest.refetch()} />}
      {gen.isError && !busy && <Problem_ p={prismProblem(gen.error)} onRetry={prismProblem(gen.error).kind === "limit" ? undefined : () => run(!!report)} retryLabel="Calculate again" />}
      {pdfErr && !expired && <Problem_ p={pdfErr} />}
      {expired && <Problem_ p={pdfErr!} onRetry={() => run(true)} retryLabel="Recalculate" />}
      {busy && <Working since={started} />}
      {!latest.isLoading && !latest.isError && !report && !busy && (
        <div className="card pzr-card pzr-empty-card">
          <div className="pzr-ico"><Icon name="prism" /></div>
          <h3>No {PRISM_NAME} rating for {symbol} yet</h3>
          <p>Calculate it from the company's latest filings and prices. It takes up to two minutes and counts as one of your 20 calculations today. {statementWord(statement)} statements.</p>
          <button type="button" className="btn primary lg" disabled={!!down} onClick={() => run(false)}><Icon name="prism" />Generate the Prism rating</button>
          <p className="pzr-note">{PRISM_NOTE}</p>
        </div>
      )}
      {report && <PrismReportView key={report.id} report={report} actions={{ onRecalculate: () => run(true), recalculating: busy, onDownload: download, downloading, pdfExpired: expired }} />}
    </div>
  );
}

export function PrismPage() {
  const { symbol: raw } = useParams();
  const [sp, setSp] = useSearchParams();
  const gold = useGold(), { showcase } = useAuth();
  const symbol = cleanSymbol(raw);
  const statement: Statement = sp.get("statement") === "standalone" ? "standalone" : "consolidated";
  if (!raw) return gold ? <Landing /> : <Locked />;
  if (!symbol) return <><Head /><div className="wrap" style={{ paddingBottom: 56 }}><div className="pm-empty"><b>That is not a company symbol.</b><p><Link to="/prism">Search for a company</Link></p></div></div></>;
  if (!gold && !showcase.includes(symbol)) return <Locked symbol={symbol} />;
  return (
    <>
      <Head><p>{symbol} · {statementWord(statement)} statements. <Link to="/prism">Another company</Link></p></Head>
      <div className="wrap pzr-page" style={{ paddingBottom: 56 }}>
        <div className="pzr-pagebar"><Picker statement={statement} setStatement={(s) => setSp(s === "standalone" ? { statement: s } : {}, { replace: true })} /></div>
        <CompanyView key={symbol + statement} symbol={symbol} statement={statement} />
      </div>
    </>
  );
}
