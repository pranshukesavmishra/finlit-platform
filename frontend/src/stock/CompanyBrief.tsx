// COMPANY BRIEF on every company page: what the company does, how the group is held, each business with its latest figures, where the money comes from, recent
// developments and what is missing, every line cited to the company's own filings. Shows the PUBLISHED brief only; with none it says why. Describes, never advises.
import { useState } from "react";
import { dateIN } from "../lib/format";
import { AUTO_NOTE, COMPLIANCE, PART_NAMES, citeUrl, citedPages, crore, shares, shortName, useCompanyBrief, type Brief, type BriefReply, type Cite, type Doc, type MixSide } from "../lib/companyBrief";
import "../styles/company-brief.css";

type Chips = Record<string, string>;
const day = (s?: string | null) => (s ? dateIN(s) : "");

/** One citation chip: the document's short label and the PDF page; it opens the filing at that page. */
export function CiteChips({ cites, docs, chips }: { cites?: Cite[]; docs: Record<string, Doc>; chips: Chips }) {
  const [copied, setCopied] = useState<string | null>(null);
  const seen = new Set<string>();
  const list = (cites ?? []).filter((c) => { const k = `${c.doc}:${c.page ?? ""}`; if (seen.has(k)) return false; seen.add(k); return true; });
  if (!list.length) return null;
  return (
    <span className="cb-cites">
      {list.map((c) => {
        const d = docs[c.doc], href = citeUrl(d, c.page), key = `${c.doc}:${c.page ?? ""}`;
        const label = `${chips[c.doc] || c.doc}${c.page ? " p." + c.page : ""}`;
        const title = `${d?.title ?? "Filing"}${d?.date ? " (" + day(d.date) + ")" : ""}${c.page ? ", page " + c.page : ""}`;
        return href
          ? <span className="cb-cite-w" key={key}>
              <a className="cb-cite" href={href} target="_blank" rel="noopener noreferrer" title={title} aria-label={`Open ${title}`}>[{label}]</a>
              <button type="button" className="cb-copy" aria-label={`Copy the link to ${title}`} title="Copy link" onClick={() => { navigator.clipboard?.writeText(href).then(() => { setCopied(key); setTimeout(() => setCopied(null), 1500); }).catch(() => undefined); }}>{copied === key ? "Copied" : "Copy"}</button>
            </span>
          : <span className="cb-cite off" key={key} title={`${title}: the address is not on file`}>[{label}]</span>;
      })}
    </span>
  );
}

function Bars({ title, side, period }: { title: string; side?: MixSide; period?: string }) {
  const rows = shares(side);
  if (!rows.length) return null;
  return (
    <div className="cb-mixcol">
      <h4>{title}{period ? <span className="cb-faint"> · {period}</span> : null}</h4>
      <ul className="cb-bars">
        {rows.map((r) => (
          <li key={r.name}>
            <span className="cb-bn">{r.name}</span>
            <span className="cb-bv">{crore(r.value)} <b>{r.pct.toFixed(1)}%</b></span>
            <span className="cb-bt" role="img" aria-label={`${r.name}: ${r.pct.toFixed(1)} percent`}><i style={{ width: `${Math.min(100, Math.max(0, r.pct))}%` }} /></span>
          </li>
        ))}
      </ul>
      {side?.basis ? <p className="cb-faint cb-note">{side.basis}</p> : null}
    </div>
  );
}

export function BriefBody({ r }: { r: Extract<BriefReply, { state: "published" }> }) {
  const b: Brief = r.brief, docs = b.docs ?? {}, chips = r.chips ?? {};
  const cited = citedPages(b);
  const name = shortName(b.name || r.name || r.symbol);
  const ch = r.changes;
  const mix = b.mix;
  return (
    <>
      <div className="cb-head">
        <div>
          <div className="cb-eyebrow">Company brief</div>
          <h2 id="cb-title">About {b.name || r.name}, from its own filings</h2>
        </div>
        <div className="cb-meta">
          {r.publishMode === "auto"
            ? <span className="cb-badge auto" title="No person has read this brief. A program confirmed that every quoted number and name is on the filing page it cites, and found nothing that needs a reader's care.">Checked automatically</span>
            : <span className="cb-badge" title="A person at FinLit read this brief and its citation check before it was shown">Reviewed{r.reviewedAt ? ` ${day(r.reviewedAt)}` : ""}</span>}
          <span className="cb-faint">Filings to <b>{day(r.asOf)}</b></span>
        </div>
      </div>
      {r.publishMode === "auto" && <p className="cb-note-i" role="note">{AUTO_NOTE}</p>}
      {r.stale && <p className="cb-warn" role="status">No newer filing has been read for over four months, so this brief may be behind. Check the dates on each line.</p>}
      {r.waiting && <p className="cb-note-i" role="status">A newer draft is waiting for review. This is the last reviewed version.</p>}
      {ch && ch.parts.length > 0 && <p className="cb-note-i" role="status">Updated{ch.now ? ` to ${day(ch.now)}` : ""}{ch.since ? ` (was ${day(ch.since)})` : ""}: {ch.parts.map((p) => PART_NAMES[p] ?? p).join(", ")} rewritten from newer filings.</p>}

      <div className="cb-about">{b.about.map((a, i) => <p key={i}>{a.text} <CiteChips cites={a.cites} docs={docs} chips={chips} /></p>)}</div>

      {!!b.key_figures?.length && (
        <section aria-label="Key figures" className="cb-sec">
          <h3>Key figures</h3>
          <div className="cb-tiles">
            {b.key_figures.map((k, i) => (
              <div className="cb-tile" key={i}>
                <span className="cb-tl">{k.label}</span>
                <b className="cb-tv">{k.value}</b>
                {k.note ? <span className="cb-tn">{k.note}</span> : null}
                <CiteChips cites={k.cites} docs={docs} chips={chips} />
              </div>
            ))}
          </div>
        </section>
      )}

      {!!b.group?.rows?.length && (
        <section aria-label="How the group is held" className="cb-sec">
          <h3>How the group is held{b.group.as_of ? <span className="cb-faint"> · as of {b.group.as_of}</span> : null}</h3>
          <div className="cb-tw">
            <table className="cb-table">
              <thead><tr><th scope="col">Company</th><th scope="col">What it does</th><th scope="col" className="num">{name}&rsquo;s share of each company</th></tr></thead>
              <tbody>
                {b.group.rows.map((g, i) => (
                  <tr key={i}>
                    <th scope="row" data-l="Company">{g.name}</th>
                    <td data-l="What it does">{g.what}{g.note ? <span className="cb-faint cb-block">{g.note}</span> : null} <CiteChips cites={g.cites} docs={docs} chips={chips} /></td>
                    <td className="num" data-l="Share"><b>{g.stake.toFixed(2)}%</b><span className="cb-bt sm" aria-hidden="true"><i style={{ width: `${Math.min(100, g.stake)}%` }} /></span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section aria-label="The businesses" className="cb-sec">
        <h3>The businesses and their latest figures</h3>
        <div className="cb-segs">
          {b.segments.map((s, i) => (
            <article className="cb-seg" key={i}>
              <h4>{s.name}</h4>
              <p className="cb-what">{s.what} <CiteChips cites={s.what_cites} docs={docs} chips={chips} /></p>
              {!!s.points?.length && <ul>{s.points.map((p, j) => <li key={j}>{p.text} <CiteChips cites={p.cites} docs={docs} chips={chips} /></li>)}</ul>}
            </article>
          ))}
        </div>
      </section>

      {(mix?.ebitda?.rows?.length || mix?.revenue?.rows?.length) ? (
        <section aria-label="Where the money comes from" className="cb-sec">
          <h3>Where the money comes from</h3>
          <div className="cb-mix">
            <div><Bars title="Share of EBITDA" side={mix.ebitda} period={mix.period} /><CiteChips cites={mix.ebitda?.cites} docs={docs} chips={chips} /></div>
            <div><Bars title="Share of revenue" side={mix.revenue} period={mix.period} /><CiteChips cites={mix.revenue?.cites} docs={docs} chips={chips} /></div>
          </div>
        </section>
      ) : null}

      <section aria-label="Recent developments" className="cb-sec">
        <h3>Recent developments</h3>
        <ol className="cb-time">
          {b.recent.map((x, i) => (
            <li key={i}><time dateTime={x.date}>{day(x.date)}</time><div><b>{x.title}</b><p>{x.text} <CiteChips cites={x.cites} docs={docs} chips={chips} /></p></div></li>
          ))}
        </ol>
      </section>

      <section aria-label="What is missing" className="cb-sec">
        <h3>What is missing</h3>
        {b.gaps?.length ? <ul className="cb-gaps">{b.gaps.map((g, i) => <li key={i}>{g}</li>)}</ul> : <p className="cb-faint">The writer listed nothing as missing. The checks below say how many citations were confirmed.</p>}
      </section>

      <details className="cb-det">
        <summary>Sources and checks</summary>
        <div className="cb-detb">
          <p className="cb-checks"><b>{r.checks.passed} of {r.checks.citations}</b> quoted citations were found on the page they cite{r.checks.date ? ` (checked ${day(r.checks.date)})` : ""}.{r.checks.unchecked ? ` ${r.checks.unchecked} point to FinLit's own data or to a document that could not be read, and were not checked against a page.` : ""}{r.checks.fixed?.length ? ` ${r.checks.fixed.join(" ")}` : ""}</p>
          {r.checks.method ? <p className="cb-faint">{r.checks.method}</p> : null}
          <ul className="cb-src">
            {cited.map(({ key, doc, pages }) => {
              const href = citeUrl(doc);
              return (
                <li key={key}>
                  <span className="cb-sk">{chips[key] || key}</span>
                  <span className="cb-st">{href ? <a href={href} target="_blank" rel="noopener noreferrer">{doc.title}</a> : doc.title}<span className="cb-faint"> · {doc.kind}{doc.date ? ` · ${day(doc.date)}` : ""}</span></span>
                  {pages.length > 0 && <span className="cb-sp">Pages cited: {pages.map((p, i) => { const h = citeUrl(doc, p); return <span key={p}>{i ? ", " : ""}{h ? <a href={h} target="_blank" rel="noopener noreferrer">{p}</a> : p}</span>; })}</span>}
                </li>
              );
            })}
          </ul>
        </div>
      </details>

      <p className="cb-disc">{r.disclaimer || b.disclaimer}</p>
      <p className="cb-disc">{r.compliance || COMPLIANCE}</p>
    </>
  );
}

export function CompanyBriefSection({ symbol }: { symbol: string }) {
  const q = useCompanyBrief(symbol);
  return (
    <section className="block cb" id="company-brief" aria-labelledby="cb-title" aria-busy={q.isLoading}>
      {q.isLoading && <div className="cb-skel" role="status" aria-label="Loading the company brief"><i /><i /><i /><i /></div>}
      {q.isError && (
        <div className="cb-empty" role="status">
          <div className="cb-eyebrow">Company brief</div><h2 id="cb-title">About this company, from its own filings</h2>
          <p>The company brief could not be loaded just now. Try again in a moment.</p>
          <button type="button" className="cb-btn" onClick={() => q.refetch()}>Try again</button>
        </div>
      )}
      {q.data?.state === "empty" && (
        <div className="cb-empty">
          <div className="cb-eyebrow">Company brief</div><h2 id="cb-title">About this company, from its own filings</h2>
          <p>{q.data.reason}</p>
          <p className="cb-disc">{q.data.compliance || COMPLIANCE}</p>
        </div>
      )}
      {q.data?.state === "published" && <BriefBody r={q.data} />}
    </section>
  );
}
