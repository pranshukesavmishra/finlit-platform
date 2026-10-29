// FinLit Prism (Gold): /prism finds a company, /prism/:symbol shows its stored rating or calculates one.
// Replaces the upstream admin "Premium Report" page: no CMS token, no browser-held snapshot. A calculation runs behind the page (POST with
// background: true, then GET /api/prism/jobs) and the page shows the stored rating when it is ready.
// The research API keeps the signed snapshot; the browser gets a PrismReport and downloads the PDF from the API.
import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { Icon } from "../lib/icons";
import { Gate } from "../components/Gate";
import { PrismReportView, ReportSkeleton } from "../components/prism/ReportView";
import { LandingBody, PRISM_WHAT, Picker } from "../components/prism/pzr/Landing";
import { useAuth } from "../lib/auth";
import { useGold } from "../lib/premium";
import {
  PRISM_NAME, PRISM_NOTE, cleanSymbol, downloadPrismPdf, prismProblem, progressFraction, pushPrismRecent, statementWord,
  useLatestPrism, usePrismCalculation, usePrismStatus, type PrismReport, type Problem, type Statement,
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

/** The honest wait: the seconds that have really passed and a bar that follows the usual time. Nothing moves in a loop. */
function Working({ since, expected }: { since: number; expected: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  const s = Math.max(0, Math.round((now - since) / 1000));
  const pct = Math.round(progressFraction(s, expected) * 100);
  return (
    <div className="card pzr-card pzr-work">
      <div className="pzr-workbody">
        <b role="status">Calculating the rating…</b>
        <p>Reading the financial statements, prices and the industry's valuations, and checking the inputs. This usually takes about {Math.max(5, Math.round(expected))} seconds. You can keep this page open: the rating appears here by itself.</p>
        <div className="pzr-prog" role="progressbar" aria-label="Calculation progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}><i style={{ width: `${pct}%` }} /></div>
        <p className="pzr-small">{s} second{s === 1 ? "" : "s"} so far</p>
      </div>
    </div>
  );
}

function CompanyView({ symbol, statement, picker }: { symbol: string; statement: Statement; picker: React.ReactNode }) {
  const { isAdmin } = useAuth();
  const latest = useLatestPrism(symbol, statement), status = usePrismStatus(), { calc, start } = usePrismCalculation(symbol, statement);
  const [downloading, setDownloading] = useState(false), [pdfErr, setPdfErr] = useState<Problem | null>(null);
  useEffect(() => { pushPrismRecent(symbol); }, [symbol]);
  const report = latest.data ?? null;
  const down = status.data && !status.data.available;
  const run = (refresh: boolean) => { setPdfErr(null); void start(refresh); };
  // A company opened with no rating starts calculating by itself, once, so the next visit is instant (and this one shows it as soon as it is ready).
  const autoStarted = useRef("");
  useEffect(() => {
    const key = `${symbol}:${statement}`;
    if (latest.isLoading || latest.isError || latest.data !== null || down || calc.phase !== "idle" || autoStarted.current === key) return;
    autoStarted.current = key;
    void start(false);
  }, [latest.isLoading, latest.isError, latest.data, down, calc.phase, symbol, statement, start]);
  const download = async () => {
    if (!report) return;
    setDownloading(true); setPdfErr(null);
    try { await downloadPrismPdf(report); } catch (e) { setPdfErr(prismProblem(e)); } finally { setDownloading(false); }
  };
  useDocTitle(report ? `${report.company.name} ${PRISM_NAME}` : `${symbol} ${PRISM_NAME}`, `FinLit Prism financial-health rating for ${symbol}.`);
  const busy = calc.phase === "working";
  // No stored rating: calculate it as soon as the page opens (once per company; a failure shows its message and a retry button).
  const autoRan = useRef("");
  useEffect(() => {
    if (!latest.isLoading && !latest.isError && !report && calc.phase === "idle" && !down && autoRan.current !== `${symbol}|${statement}`) { autoRan.current = `${symbol}|${statement}`; run(false); }
  }, [latest.isLoading, latest.isError, report, calc.phase, down, symbol, statement]);   // eslint-disable-line react-hooks/exhaustive-deps
  const expired = pdfErr?.kind === "expired";
  return (
    <div aria-busy={busy || latest.isLoading}>
      <div className="pzr-pagebar">
        {picker}
        {isAdmin && report && (
          <button type="button" className="btn primary pzr-dl" onClick={download} disabled={downloading} title="Download the full Prism report of this company as a PDF (administrators only)">
            <Icon name="download" />{downloading ? "Preparing PDF…" : "Download report (PDF)"}</button>
        )}
      </div>
      {down && <div className="pzr-problem unavailable" role="note"><Icon name="alert" /><div><b>{PRISM_NAME} is not connected right now</b><p>{status.data?.reason || "The rating service is unavailable."} Stored ratings may still open.</p></div></div>}
      {latest.isLoading && <ReportSkeleton />}
      {latest.isError && !busy && <Problem_ p={prismProblem(latest.error)} onRetry={() => latest.refetch()} />}
      {calc.phase === "failed" && <Problem_ p={calc.problem} onRetry={calc.retryable ? () => run(!!report) : undefined} retryLabel="Retry" />}
      {pdfErr && !expired && <Problem_ p={pdfErr} />}
      {expired && <Problem_ p={pdfErr!} onRetry={() => run(true)} retryLabel="Recalculate" />}
      {calc.phase === "working" && <Working since={calc.startedAt} expected={calc.expectedSeconds} />}
      {!latest.isLoading && !latest.isError && !report && calc.phase === "idle" && (
        <div className="card pzr-card pzr-empty-card">
          <div className="pzr-ico"><Icon name="prism" /></div>
          <h3>No {PRISM_NAME} rating for {symbol} yet</h3>
          <p>It is calculated from the company's latest filings and prices; this usually takes under half a minute. {statementWord(statement)} statements.</p>
          <button type="button" className="btn primary lg" disabled={!!down} onClick={() => run(false)}><Icon name="prism" />Generate the Prism rating</button>
          <p className="pzr-note">{PRISM_NOTE}</p>
        </div>
      )}
      {report && <PrismReportView key={report.id} report={report} actions={{ onRecalculate: () => run(true), recalculating: busy, }} />}
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
        <CompanyView key={symbol + statement} symbol={symbol} statement={statement}
          picker={<Picker statement={statement} setStatement={(s) => setSp(s === "standalone" ? { statement: s } : {}, { replace: true })} />} />
      </div>
    </>
  );
}
