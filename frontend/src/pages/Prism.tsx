// FinLit Prism (Gold): /prism finds a company, /prism/:symbol shows its stored rating or calculates one.
// Replaces the upstream admin "Premium Report" page: no CMS token, no browser-held snapshot, no polling a background job.
// The research API keeps the signed snapshot; the browser gets a PrismReport and downloads the PDF from the API.
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { Icon } from "../lib/icons";
import { Gate } from "../components/Gate";
import { PrismReportView } from "../components/prism/ReportView";
import { useSearchIndex } from "../lib/api";
import { useAuth } from "../lib/auth";
import { rankCompanies } from "../lib/companySearch";
import { useGold, useSlashFocus } from "../lib/premium";
import { useUniverse } from "../lib/screener";
import {
  PRISM_NAME, PRISM_NOTE, cleanSymbol, downloadPrismPdf, prismProblem, pushPrismRecent, readPrismRecent, statementWord,
  useGeneratePrism, useLatestPrism, usePrismStatus, type PrismReport, type Problem, type Statement,
} from "../lib/prism";
import { useDocTitle } from "../lib/title";
import { PremiumHead } from "./Premium";
import example from "../lib/__fixtures__/prismReport.json";

const WHAT = ["A score out of 100 and a label from Strong to Poor, or Not rated when the evidence is thin", "Four parts: Fundamentals, Valuation, Quality and Risk, each with what supports it and what holds it back", "Every factor with its value, points and status, and which inputs are missing", "A PDF of exactly the calculation you see"];

function Head({ children }: { children?: React.ReactNode }) {
  return <PremiumHead eyebrow="Gold · Financial health" title={PRISM_NAME}>{children ?? <p>A company's financial health, split into four parts the way a prism splits light. {PRISM_NOTE}</p>}</PremiumHead>;
}

function Locked({ symbol }: { symbol?: string }) {
  return (
    <>
      <Head />
      <div className="wrap" style={{ paddingBottom: 56 }}>
        <Gate tier="gold" title={`${PRISM_NAME} is part of Gold`} points={WHAT}>
          <p className="pz-sm" style={{ margin: "0 0 12px" }}>Example only: a fictional company{symbol ? `, not ${symbol}` : ""}.</p>
          <div className="pz-preview"><PrismReportView report={example as unknown as PrismReport} /></div>
        </Gate>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ company picker */
function StatementSwitch({ value, set, disabled }: { value: Statement; set: (s: Statement) => void; disabled?: boolean }) {
  return (
    <div className="seg pz-seg" role="group" aria-label="Statement basis">
      {(["consolidated", "standalone"] as Statement[]).map((s) => <button key={s} type="button" className={s === value ? "on" : ""} aria-pressed={s === value} disabled={disabled} onClick={() => set(s)}>{statementWord(s)}</button>)}
    </div>
  );
}

function Picker({ statement, setStatement }: { statement: Statement; setStatement: (s: Statement) => void }) {
  const nav = useNavigate();
  const idx = useSearchIndex(true);
  const [text, setText] = useState(""), [open, setOpen] = useState(false), [cur, setCur] = useState(0);
  const box = useRef<HTMLInputElement>(null);
  useSlashFocus(box);
  const hits = useMemo(() => rankCompanies(idx.data?.rows, text, 8), [idx.data, text]);
  const go = (symbol: string) => { setText(""); setOpen(false); nav(`/prism/${encodeURIComponent(symbol)}${statement === "standalone" ? "?statement=standalone" : ""}`); };
  const submit = () => { const pick = hits[cur] ?? hits[0]; const typed = cleanSymbol(text); if (pick) go(pick.symbol); else if (typed) go(typed); };
  return (
    <div className="pz-pick">
      <div className="pm-search">
        <Icon name="search" />
        <input ref={box} value={text} role="combobox" aria-expanded={open && hits.length > 0} aria-controls="pz-sug" aria-autocomplete="list" aria-label="Choose a company"
          placeholder="Company name or symbol, for example TCS" autoComplete="off" onChange={(e) => { setText(e.target.value); setOpen(true); setCur(0); }}
          onBlur={() => setTimeout(() => setOpen(false), 150)} onFocus={() => setOpen(true)}
          onKeyDown={(e) => { if (e.key === "ArrowDown") { e.preventDefault(); setCur((c) => Math.min(hits.length - 1, c + 1)); } else if (e.key === "ArrowUp") { e.preventDefault(); setCur((c) => Math.max(0, c - 1)); } else if (e.key === "Enter") { e.preventDefault(); submit(); } else if (e.key === "Escape") setOpen(false); }} />
        {open && hits.length > 0 && <div className="pm-sug" id="pz-sug" role="listbox">{hits.map((h, i) => <button key={h.symbol} type="button" role="option" aria-selected={i === cur} className={i === cur ? "on" : ""} onMouseDown={(e) => e.preventDefault()} onClick={() => go(h.symbol)}><b>{h.symbol}</b><small>{h.name}</small></button>)}</div>}
      </div>
      <label className="pz-lbl">Statement basis<StatementSwitch value={statement} set={setStatement} /></label>
    </div>
  );
}

/** Browse by sector, as the old page did: pick a sector, then a company. */
function Browse({ statement }: { statement: Statement }) {
  const [on, setOn] = useState(false), [sector, setSector] = useState<string | null>(null);
  const u = useUniverse(on);
  const sectors = useMemo(() => { const m = new Map<string, number>(); (u.data?.rows || []).forEach((r) => r.sector && m.set(r.sector, (m.get(r.sector) || 0) + 1)); return [...m].sort((a, b) => a[0].localeCompare(b[0])); }, [u.data]);
  const list = useMemo(() => (u.data?.rows || []).filter((r) => r.sector === sector).sort((a, b) => (a.name || a.symbol).localeCompare(b.name || b.symbol)), [u.data, sector]);
  const q = statement === "standalone" ? "?statement=standalone" : "";
  return (
    <section className="pz-browse" aria-label="Browse companies">
      <div className="pz-browse-h"><h3 className="pz-h">Browse companies</h3><button type="button" className="pz-link" aria-expanded={on} onClick={() => setOn(!on)}>{on ? "Hide sectors" : "Show sectors"}</button></div>
      {on && (u.isLoading ? <div className="skeleton" style={{ height: 80 }} aria-busy="true" /> : u.isError ? <p className="pz-empty">The sector list is not available right now. Search by name or symbol instead.</p> : <>
        <div className="pz-chipsrow" role="group" aria-label="Sectors">{sectors.map(([s, n]) => <button type="button" key={s} className={"fchip" + (s === sector ? " on" : "")} aria-pressed={s === sector} onClick={() => setSector(s === sector ? null : s)}>{s} <small>{n}</small></button>)}</div>
        {sector && <ul className="pz-co-list" aria-label={`Companies in ${sector}`}>{list.slice(0, 60).map((r) => <li key={r.symbol}><Link to={`/prism/${r.symbol}${q}`}><b>{r.symbol}</b><small>{r.name}</small></Link></li>)}</ul>}
        {sector && list.length > 60 && <p className="pz-sm">Showing 60 of {list.length}. Use the search box to find another.</p>}
      </>)}
    </section>
  );
}

function Landing() {
  useDocTitle(PRISM_NAME, "FinLit Prism: a company's financial health in four parts, with a PDF. For Gold members.");
  const [statement, setStatement] = useState<Statement>("consolidated");
  const recent = readPrismRecent();
  return (
    <>
      <Head />
      <div className="wrap pz-land" style={{ paddingBottom: 56 }}>
        <Picker statement={statement} setStatement={setStatement} />
        {recent.length > 0 && <div className="pm-recent" aria-label="Recently opened"><span className="faint">Recent</span>{recent.map((x) => <Link key={x} className="fchip" to={`/prism/${x}`}>{x}</Link>)}</div>}
        <div className="pz-how">
          <div className="card pz-card"><h3 className="pz-h">What you get</h3><ul className="pz-what">{WHAT.map((w) => <li key={w}><Icon name="check" />{w}</li>)}</ul></div>
          <div className="card pz-card"><h3 className="pz-h">How it works</h3><p className="pz-sub">Choose a company. If a rating was calculated recently it opens at once; otherwise Prism calculates it from the latest filings and prices, which can take up to two minutes. Each member can calculate 20 a day.</p><p className="pz-note-line">{PRISM_NOTE}</p></div>
        </div>
        <Browse statement={statement} />
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ one company */
const Problem_ = ({ p, onRetry, retryLabel = "Try again" }: { p: Problem; onRetry?: () => void; retryLabel?: string }) => (
  <div className={"pz-problem " + p.kind} role="alert"><Icon name="alert" /><div><b>{p.title}</b><p>{p.text}</p>{onRetry && <button type="button" className="btn" onClick={onRetry}>{retryLabel}</button>}</div></div>
);

function Working({ since }: { since: number }) {
  const [s, setS] = useState(0);
  useEffect(() => { const t = setInterval(() => setS(Math.round((Date.now() - since) / 1000)), 1000); return () => clearInterval(t); }, [since]);
  return (
    <div className="card pz-card pz-work" role="status" aria-live="polite">
      <span className="pz-spin" aria-hidden="true" />
      <div><b>Calculating the rating…</b><p>Reading financial statements and prices, and checking the inputs. This can take up to two minutes; keep this page open. {s > 0 && <span className="pz-sm">{s}s so far.</span>}</p></div>
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
      {down && <div className="pz-problem unavailable" role="note"><Icon name="alert" /><div><b>{PRISM_NAME} is not connected right now</b><p>{status.data?.reason || "The rating service is unavailable."} Stored ratings may still open.</p></div></div>}
      {latest.isLoading && <div className="skeleton" style={{ height: 360 }} aria-label="Loading the stored rating" />}
      {latest.isError && !busy && <Problem_ p={prismProblem(latest.error)} onRetry={() => latest.refetch()} />}
      {gen.isError && !busy && <Problem_ p={prismProblem(gen.error)} onRetry={prismProblem(gen.error).kind === "limit" ? undefined : () => run(!!report)} retryLabel="Calculate again" />}
      {pdfErr && !expired && <Problem_ p={pdfErr} />}
      {expired && <Problem_ p={pdfErr!} onRetry={() => run(true)} retryLabel="Recalculate" />}
      {busy && <Working since={started} />}
      {!latest.isLoading && !latest.isError && !report && !busy && (
        <div className="card pz-card pz-empty-card">
          <div className="pz-ico"><Icon name="prism" /></div>
          <h3>No {PRISM_NAME} rating for {symbol} yet</h3>
          <p>Calculate it from the company's latest filings and prices. It takes up to two minutes and counts as one of your 20 calculations today. {statementWord(statement)} statements.</p>
          <button type="button" className="btn primary lg" disabled={!!down} onClick={() => run(false)}><Icon name="prism" />Generate the Prism rating</button>
          <p className="pz-note-line">{PRISM_NOTE}</p>
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
      <div className="wrap pz-page" style={{ paddingBottom: 56 }}>
        <div className="pz-bar"><Picker statement={statement} setStatement={(s) => setSp(s === "standalone" ? { statement: s } : {}, { replace: true })} /></div>
        <CompanyView key={symbol + statement} symbol={symbol} statement={statement} />
      </div>
    </>
  );
}
