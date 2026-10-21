// "What it invests in": donut of the major holdings, concentration, sector and asset split, month-on-month change, and every small holding in a table.
// Shared by mutual funds and ETFs. Takes the portfolio JSON of finlit.disclosure.get_portfolio (or its { unavailable } reason). Numbers are shown exactly as published.
import { useId, useMemo, useState } from "react";
import { Link } from "react-router";
import { dateIN, nf } from "../lib/format";
import { arcPath, assetRows, classifyChanges, groupHoldings, SMALL_BELOW_PCT, sectorRows, sliceFractions, sliceList, sortHoldings, topNPct, type ChangeKind, type SortDir } from "./logic";
import { isPortfolio, type Holding, type PortfolioResult } from "./types";
import "./holdings.css";

const pct = (v: number | null | undefined, d = 2) => (v == null ? "—" : nf(v, d) + "%");
const pp = (v: number | null | undefined) => (v == null ? "—" : (v > 0 ? "+" : v < 0 ? "−" : "") + nf(Math.abs(v), 2) + " pp");
const KIND_TEXT: Record<ChangeKind, string> = { new: "New", exited: "Exited", increased: "Increased", decreased: "Decreased", unchanged: "Unchanged" };
const PATTERNS = ["", "stripe", "dots", "cross"] as const;

function NameCell({ h }: { h: { name: string; stockSymbol?: string | null } }) {
  return h.stockSymbol ? <Link to={`/stocks/${encodeURIComponent(h.stockSymbol)}`} title={`Open ${h.stockSymbol} on FinLit`}>{h.name}</Link> : <>{h.name}</>;
}

function Donut({ slices }: { slices: ReturnType<typeof sliceList> }) {
  const uid = useId().replace(/[^a-zA-Z0-9]/g, "");
  const [active, setActive] = useState<number | null>(null);
  const fr = sliceFractions(slices.map((s) => s.pct));
  const cur = active == null ? null : slices[active];
  const fillOf = (i: number, other: boolean) => (other ? "var(--hd-other)" : `var(--hd-${i % 8})`);
  return (
    <div className="hd-donut">
      <svg viewBox="0 0 220 220" role="group" aria-label="Share of each major holding in the portfolio. Use Tab to move between slices.">
        <defs>
          {PATTERNS.slice(1).map((p) => (
            <pattern key={p} id={`${uid}-${p}`} width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              {p === "stripe" && <rect width="3" height="8" fill="var(--hd-ink)" opacity=".5" />}
              {p === "dots" && <circle cx="4" cy="4" r="1.6" fill="var(--hd-ink)" opacity=".55" />}
              {p === "cross" && <><rect width="2" height="8" fill="var(--hd-ink)" opacity=".5" /><rect width="8" height="2" fill="var(--hd-ink)" opacity=".5" /></>}
            </pattern>))}
        </defs>
        {slices.map((s, i) => {
          const d = arcPath(110, 110, 100, 58, fr[i][0], fr[i][1]);
          const pat = s.other ? "stripe" : PATTERNS[Math.floor(i / 8) % 4];
          return (
            <g key={s.key} tabIndex={0} role="img" className={"hd-slice" + (active === i ? " on" : "")}
              aria-label={`${s.label}, ${nf(s.pct, 2)} percent${s.sector ? `, ${s.sector}` : ""}`}
              onMouseEnter={() => setActive(i)} onMouseLeave={() => setActive((a) => (a === i ? null : a))} onFocus={() => setActive(i)} onBlur={() => setActive((a) => (a === i ? null : a))}>
              <path d={d} fill={fillOf(i, s.other)} />
              {pat && <path d={d} fill={`url(#${uid}-${pat})`} />}
              <path d={d} fill="none" className="hd-edge" />
            </g>);
        })}
        <text x="110" y="104" textAnchor="middle" className="hd-ct1">{cur ? nf(cur.pct, 2) + "%" : slices.length}</text>
        <text x="110" y="124" textAnchor="middle" className="hd-ct2">{cur ? "of the portfolio" : slices.length === 1 ? "slice" : "slices"}</text>
      </svg>
      <div className="hd-tip" role="status" aria-live="polite">
        {cur ? <><b>{cur.label}</b><span>{nf(cur.pct, 2)}%{cur.sector ? ` · ${cur.sector}` : ""}</span></> : <span className="hd-hint">Hover or focus a slice for its name, share and sector.</span>}
      </div>
    </div>
  );
}

function SmallTable({ rows }: { rows: Holding[] }) {
  const [key, setKey] = useState<"name" | "sector" | "pct" | "qty" | "valueLakh">("pct");
  const [dir, setDir] = useState<SortDir>("desc");
  const sorted = useMemo(() => sortHoldings(rows, key, dir), [rows, key, dir]);
  const head = (k: typeof key, label: string, num = false) => (
    <th scope="col" className={num ? "num" : ""} aria-sort={key === k ? (dir === "asc" ? "ascending" : "descending") : "none"}>
      <button type="button" className="hd-sort" onClick={() => { if (key === k) setDir(dir === "asc" ? "desc" : "asc"); else { setKey(k); setDir(k === "name" || k === "sector" ? "asc" : "desc"); } }}>
        {label}{key === k && <i aria-hidden="true">{dir === "asc" ? "▲" : "▼"}</i>}
      </button>
    </th>);
  return (
    <div className="hd-scroll" tabIndex={0} role="region" aria-label={`All ${rows.length} holdings below ${SMALL_BELOW_PCT} percent`}>
      <table className="hd-table">
        <caption className="sr-only">Every holding below {SMALL_BELOW_PCT}% of the portfolio. Use the column buttons to sort.</caption>
        <thead><tr>{head("name", "Holding")}{head("sector", "Sector")}{head("pct", "Share", true)}{head("qty", "Quantity", true)}{head("valueLakh", "Value (₹ lakh)", true)}</tr></thead>
        <tbody>{sorted.map((h, i) => (
          <tr key={`${h.isin || h.name}-${i}`}><th scope="row"><NameCell h={h} /></th><td>{h.sector || "—"}</td><td className="num">{pct(h.pct)}</td>
            <td className="num">{h.qty == null ? "—" : nf(h.qty, 0)}</td><td className="num">{h.valueLakh == null ? "—" : nf(h.valueLakh, 2)}</td></tr>))}</tbody>
      </table>
    </div>
  );
}

export function HoldingsSection({ portfolio, title = "What it invests in", unit = "fund" }: { portfolio: PortfolioResult | null | undefined; title?: string; unit?: string }) {
  const p = isPortfolio(portfolio) ? portfolio : null;
  const g = useMemo(() => (p ? groupHoldings(p.holdings) : null), [p]);
  const slices = useMemo(() => (g ? sliceList(g) : []), [g]);
  const changes = useMemo(() => (p ? classifyChanges(p) : null), [p]);
  const sectors = useMemo(() => (p ? sectorRows(p) : []), [p]);
  const [showAll, setShowAll] = useState(false);

  if (!p || !g) {
    return (
      <section className="card hd" aria-labelledby="hd-h">
        <h3 id="hd-h">{title}</h3>
        <p className="hd-none"><span className="hd-dash" aria-hidden="true">—</span> {portfolio && "unavailable" in portfolio ? portfolio.unavailable : "The portfolio of this " + unit + " is not loaded."}</p>
      </section>);
  }
  const top10 = p.summary.top10Pct ?? topNPct(p.holdings, 10);
  const count = p.summary.count || p.holdings.length;
  const maxSector = Math.max(1, ...sectors.map((s) => s.pct));
  const moved = (changes || []).filter((c) => c.kind !== "unchanged");
  const shownChanges = showAll ? changes || [] : moved;
  return (
    <section className="card hd" aria-labelledby="hd-h">
      <div className="card-h"><h3 id="hd-h">{title}</h3><span className="s">{p.asOf ? `as of ${dateIN(p.asOf)}` : "date not published"}</span></div>

      <dl className="hd-kpis">
        <div><dt>Holdings</dt><dd>{nf(count, 0)}</dd></div>
        <div><dt>Top 10 together</dt><dd>{pct(top10)}</dd></div>
        <div><dt>Shown in the chart</dt><dd>{g.major.length} at {SMALL_BELOW_PCT}% or more</dd></div>
        <div><dt>Small holdings</dt><dd>{g.otherCount} below {SMALL_BELOW_PCT}%, {pct(g.otherPct)} together</dd></div>
      </dl>

      <div className="hd-grid">
        <Donut slices={slices} />
        <ol className="hd-legend" aria-label="Major holdings">
          {slices.map((s, i) => (
            <li key={s.key}>
              <span className={"hd-sw" + (s.other ? " other" : "")} style={{ backgroundColor: s.other ? "var(--hd-other)" : `var(--hd-${i % 8})` }} data-pat={s.other ? "stripe" : PATTERNS[Math.floor(i / 8) % 4]} aria-hidden="true" />
              <span className="hd-ln">{s.holding ? <NameCell h={s.holding} /> : s.label}{s.sector && <small>{s.sector}</small>}</span>
              <b>{pct(s.pct)}</b>
            </li>))}
        </ol>
      </div>

      <h4 className="hd-h4">All holdings below {SMALL_BELOW_PCT}% ({g.otherCount})</h4>
      {g.otherCount ? <SmallTable rows={g.small} /> : <p className="hd-none">Every holding is at {SMALL_BELOW_PCT}% or more, so none are grouped.</p>}

      <div className="hd-two">
        <div>
          <h4 className="hd-h4">By sector</h4>
          {sectors.length ? (
            <ul className="hd-bars">{sectors.map((s) => (
              <li key={s.sector}><span className="hd-bl">{s.sector}</span><span className="hd-bt" aria-hidden="true"><i style={{ width: `${(s.pct / maxSector) * 100}%` }} /></span><b>{pct(s.pct)}</b></li>))}</ul>
          ) : <p className="hd-none">— No sector split is published for this {unit}.</p>}
        </div>
        <div>
          <h4 className="hd-h4">By asset type</h4>
          <ul className="hd-bars">{assetRows(p.summary.assetSplit).map((a) => (
            <li key={a.key}><span className="hd-bl">{a.label}</span><span className="hd-bt" aria-hidden="true"><i style={{ width: `${Math.min(100, a.pct ?? 0)}%` }} /></span>
              <b>{a.pct == null ? <span title="Not published in the source rows">—</span> : pct(a.pct)}</b></li>))}</ul>
          <p className="hd-fine">Only classes present in the published rows are shown; a dash means the source does not give that class.</p>
        </div>
      </div>

      <h4 className="hd-h4">Change since {p.previousAsOf ? dateIN(p.previousAsOf) : "last month"}</h4>
      {changes == null ? <p className="hd-none">— Only one month of portfolio is on file, so no change can be shown yet.</p> : (
        <>
          <label className="hd-chk"><input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} /> Include unchanged holdings</label>
          {shownChanges.length === 0 ? <p className="hd-none">No holding moved between the two months.</p> : (
            <div className="hd-scroll" tabIndex={0} role="region" aria-label="Change in holdings since the previous month">
              <table className="hd-table">
                <caption className="sr-only">Holdings that are new, exited, increased or decreased against the previous month, in percentage points of the portfolio.</caption>
                <thead><tr><th scope="col">Holding</th><th scope="col">Move</th><th scope="col" className="num">Now</th><th scope="col" className="num">Before</th><th scope="col" className="num">Change</th></tr></thead>
                <tbody>{shownChanges.map((c, i) => (
                  <tr key={`${c.isin || c.name}-${i}`}><th scope="row"><NameCell h={c} /></th><td><span className={`hd-chip ${c.kind}`}>{KIND_TEXT[c.kind]}</span></td>
                    <td className="num">{pct(c.pct)}</td><td className="num">{c.kind === "new" ? "—" : pct(c.prevPct)}</td>
                    <td className={"num " + (c.change == null || c.change === 0 ? "" : c.change > 0 ? "pos" : "neg")}>{pp(c.change)}</td></tr>))}</tbody>
              </table>
            </div>)}
        </>)}

      <p className="hd-src">Source: {p.sourceUrl ? <a href={p.sourceUrl} target="_blank" rel="noopener noreferrer">{p.source}</a> : p.source}. As of {p.asOf ? dateIN(p.asOf) : "—"}{p.previousAsOf ? `; compared with ${dateIN(p.previousAsOf)}` : ""}. Shares are as published by the fund house and may not add up to exactly 100%.</p>
    </section>
  );
}
