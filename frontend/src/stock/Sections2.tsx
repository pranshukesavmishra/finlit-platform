import { useState } from "react";
import { Icon } from "../lib/icons";

import { LineChart } from "../charts/LineChart";
import { cr, dateIN, initials, nf, pct, signed } from "../lib/format";
import type { Events, Ratios, Segments, Summary } from "../lib/api";
import { SectionHead } from "./Sections";
import { Plain } from "../components/Plain";
import { ChartHelp } from "../components/ChartHelp";
import { ScoreMovesCard } from "./ScoreMoves";
import { SegmentHistory } from "./SegmentMix";
import { OTHERS_COLOR, segmentColors, segmentNames } from "../lib/segmentMix";
import { ChartZoom } from "../components/ChartZoom";

const v = (n: string) => `var(${n})`;

/* Ownership (section 11) lives in ./own/OwnershipSection.tsx */
export { OwnershipSection } from "./own/OwnershipSection";

/* ---------------- Company ---------------- */
export function BusinessSection({ s }: { s: Summary }) {
  const p = s.profile, [more, setMore] = useState(false);
  const desc = (p.description || "Neither of our data sources holds a description of this company yet. The sector, the exchange codes and the announcements below are still shown.").replace(/\s+/g, " ");
  const fromUpstox = !!p.description && s.dataQuality?.secondarySource?.profile === "upstox";
  const nseUrl = p.nse && /^[A-Z0-9&-]{1,20}$/.test(p.nse) ? `https://www.nseindia.com/get-quotes/equity?symbol=${encodeURIComponent(p.nse)}` : null;
  const bseUrl = p.bse && /^\d{6}$/.test(String(p.bse)) ? `https://www.bseindia.com/stock-share-price/x/x/${p.bse}/` : null;
  const long = desc.length > 330;
  const stats: [string, string, string, string][] = [
    ["cap", "Market cap", p.marketCapCr ? "₹" + cr(p.marketCapCr) + " Cr" : "—", "--p-growth"],
    ["users", "Employees", p.employees ? nf(p.employees, 0) : "—", "--p-quality"],
    ["id", "NSE code", p.nse || "—", "--gold"],
    ["tag", "BSE code", p.bse || "—", "--p-profit"],
  ];
  return (
    <section className="block" style={{ "--sc": "var(--p-growth)" } as React.CSSProperties}>
      <SectionHead id="business" no="01 · Company overview" icon="building" tier="basic" title={`What ${p.name.split(" ")[0]} does`} color="--p-growth" />
      <div className="biz2">
        <div className="card acc biz-main" style={{ "--ac": "var(--p-growth)" } as React.CSSProperties}>
          <svg className="skyline" viewBox="0 0 400 120" aria-hidden="true" preserveAspectRatio="xMaxYMax meet">
            {[[10, 60, 36], [52, 30, 30], [88, 74, 26], [120, 20, 40], [166, 52, 30], [202, 38, 34], [244, 70, 28], [278, 14, 36], [320, 48, 30], [356, 66, 30]].map(([x, y, w], i) => <g key={i}><rect x={x} y={y} width={w} height={120 - y} rx="3" fill="var(--p-growth)" opacity={0.1 + (i % 3) * 0.05} />{Array.from({ length: 4 }, (_, j) => <rect key={j} x={x + 6 + (j % 2) * 12} y={y + 8 + Math.floor(j / 2) * 14} width="5" height="6" rx="1" fill="var(--gold)" opacity=".5" className="win" style={{ animationDelay: `${(i * 4 + j) * 140}ms` }} />)}</g>)}
          </svg>
          <div className="biz-id"><span className="biz-av">{initials(p.name)}</span><div><b>{p.name}</b><div className="biz-tags">{p.sector && <span className="chip">{p.sector}</span>}{p.industry && <span className="chip">{p.industry}</span>}</div></div></div>
          <p className={"biz-desc" + (more ? " open" : "")}>{desc}</p>
          <div className="biz-actions">{long && <button className="btn" onClick={() => setMore(!more)}>{more ? "Show less" : "Read the full description"}</button>}
            {p.website && /^[\w.-]+\.[a-z]{2,}/i.test(p.website) && <a className="chip gold" href={`https://${p.website.replace(/^https?:\/\//, "")}`} target="_blank" rel="noopener noreferrer">{p.website} ↗</a>}
            {nseUrl && <a className="chip" href={nseUrl} target="_blank" rel="noopener noreferrer" title="This company's page on the National Stock Exchange">NSE: {p.nse} ↗</a>}
            {bseUrl && <a className="chip" href={bseUrl} target="_blank" rel="noopener noreferrer" title="This company's page on BSE, with its filings and announcements">BSE: {p.bse} ↗</a>}</div>
          {fromUpstox && <p className="faint biz-src">Description from the company profile at Upstox (our second data source).</p>}
        </div>
        <div className="bstats">{stats.map(([ic, k, val, c], i) => <div className="bs" key={k} style={{ "--bc": v(c), animationDelay: `${i * 80}ms` } as React.CSSProperties}><span className="bs-i"><Icon name={ic} /></span><div className="label">{k}</div><div className="bs-v">{val}</div></div>)}</div>
      </div>
    </section>
  );
}

/* ---------------- Dividends and announcements ---------------- */
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function DividendsSection({ e, price, r }: { e?: Events; price?: number | null; r?: Ratios }) {
  const [shares, setShares] = useState(100);
  if (!e) return null;
  const divs = e.actions.filter((a) => a.type.endsWith("dividend")), recent = divs.slice(0, 6);
  const fy = e.dividendsByFY, last = fy.dps[fy.dps.length - 1] ?? 0, max = Math.max(...fy.dps, 1), avg = fy.dps.reduce((a, b) => a + b, 0) / Math.max(1, fy.dps.length);
  const first = fy.dps.find((x) => x > 0) ?? 0, yrs = Math.max(1, fy.dps.length - 1);
  const cagr = first > 0 && last > 0 ? (Math.pow(last / first, 1 / yrs) - 1) * 100 : null;
  let streak = 0; for (let i = fy.dps.length - 1; i >= 0 && fy.dps[i] > 0; i--) streak++;
  let rising = 0; for (let i = fy.dps.length - 1; i > 0 && fy.dps[i] >= fy.dps[i - 1]; i--) rising++;
  const payout = r?.latest.dividend_payout?.value ?? null, payHist = r?.history.rows.dividend_payout || [];
  const safe = payout == null ? null : payout < 40 ? ["Comfortable", "good"] : payout < 70 ? ["Moderate", "mid"] : ["Stretched", "warn"];
  const R = 46, C = 2 * Math.PI * R, yld = Math.min(100, ((e.dividendYieldTtm ?? 0) / 5) * 100);
  const paidMonths = new Set(divs.map((d) => new Date(d.date).getMonth()));
  const monthly = (shares * last) / 12;
  return (
    <section className="block" style={{ "--sc": "var(--gold-deep)" } as React.CSSProperties}>
      <SectionHead id="dividends" no="14 · Dividends & events" icon="coins" tier="basic" title="Cash returned to shareholders" sub="Amounts are adjusted for splits and bonuses." color="--gold-deep" />
      {e.dividendYieldTtm != null && <Plain tone={streak >= 5 && rising >= 3 ? "good" : "info"}>For every ₹100 invested at today's price, this company pays about ₹{nf(e.dividendYieldTtm, 2)} a year. It has paid a dividend for {streak} year{streak === 1 ? "" : "s"} running{rising >= 2 ? ` and raised it ${rising} years in a row` : ""}.{payout != null ? ` It keeps about ${nf(100 - payout, 0)}% of its profit to grow the business.` : ""} {e.dividendYieldTtm < 1 ? "A low yield suggests owning it for growth rather than income." : ""}</Plain>}
      <div className="dvk">
        <div className="dk" style={{ "--dc": "var(--gold)" } as React.CSSProperties}>
          <div className="dk-ring"><svg viewBox="0 0 120 120" aria-hidden="true"><defs><linearGradient id="dvy" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="#F3E6BF" /><stop offset=".5" stopColor="var(--gold)" /><stop offset="1" stopColor="var(--gold-deep)" /></linearGradient></defs><circle cx="60" cy="60" r={R} fill="none" stroke="var(--s3)" strokeWidth="10" /><circle className="ring-in" cx="60" cy="60" r={R} fill="none" stroke="var(--gold)" strokeWidth="10" strokeLinecap="round" strokeDasharray={`${(C * yld) / 100} ${C}`} transform="rotate(-90 60 60)" /></svg><b>{pct(e.dividendYieldTtm)}</b></div>
          <div><span className="label">Dividend yield</span><p>Yearly cash per ₹100 invested. Ring: against a 5% scale.</p></div>
        </div>
        <div className="dk" style={{ "--dc": "var(--c2)" } as React.CSSProperties}>
          <span className="dk-i"><Icon name="percent" /></span>
          <div><span className="label">Share of profit paid out</span><b className="dk-v">{payout == null ? "—" : nf(payout, 0) + "%"}</b>{safe && <span className={"dk-tag " + safe[1]}>{safe[0]}</span>}<p>{payout == null ? "" : payout < 40 ? "Plenty of room to keep paying." : payout < 70 ? "A balanced split between owners and growth." : "Little left over; the dividend could be harder to sustain."}</p></div>
        </div>
        <div className="dk" style={{ "--dc": "var(--c3)" } as React.CSSProperties}>
          <span className="dk-i"><Icon name="growth" /></span>
          <div><span className="label">Dividend growth</span><b className="dk-v">{cagr == null ? "—" : (cagr >= 0 ? "+" : "−") + nf(Math.abs(cagr), 1) + "% a year"}</b><p>From ₹{nf(first, 2)} to ₹{nf(last, 2)} per share over {yrs} years.</p></div>
        </div>
        <div className="dk" style={{ "--dc": "var(--c4)" } as React.CSSProperties}>
          <span className="dk-i"><Icon name="check" /></span>
          <div><span className="label">Years paid in a row</span><b className="dk-v">{streak} of {fy.dps.length}</b><div className="dk-dots">{fy.dps.map((x, i) => <i key={i} className={x > 0 ? "on" : ""} title={`${fy.periods[i]}: ₹${nf(x, 2)}`} />)}</div></div>
        </div>
      </div>
      <div className="div3">
        <div className="card acc" style={{ "--ac": "var(--gold)" } as React.CSSProperties}>
          <div className="card-h"><h3><span className="ci"><Icon name="bars" /></span>Dividend per share<ChartHelp id="div-dps" /></h3><span className="s">₹ per financial year</span></div>
          <ChartZoom label="Dividend per share by year" className="cz-top">
          <div className="dbars" data-chart style={{ "--avg": `${(avg / max) * 150}px` } as React.CSSProperties}>
            {fy.periods.map((p, i) => { const prv = fy.dps[i - 1], g = i && prv ? ((fy.dps[i] - prv) / prv) * 100 : null; return <div className="dcol" key={p}>{g != null && <b className={"yoy " + (g >= 0 ? "up" : "down")}>{g >= 0 ? "▲" : "▼"}{nf(Math.abs(g), 0)}%</b>}<span>₹{nf(fy.dps[i], 2)}</span><i style={{ height: Math.max(6, (fy.dps[i] / max) * 150), animationDelay: `${i * 90}ms` }} /><em>{p}</em></div>; })}
            <u className="avgline"><b>average</b></u>
          </div>
          </ChartZoom>
          <p className="faint" style={{ fontSize: 12, margin: "14px 0 0" }}>{fy.basis}.</p>
        </div>
        <div className="card acc" style={{ "--ac": "var(--c2)" } as React.CSSProperties}>
          <div className="card-h"><h3><span className="ci"><Icon name="percent" /></span>Payout ratio over time<ChartHelp id="payout" /></h3><span className="s">% of profit paid as dividends</span></div>
          {payHist.filter((x) => x != null).length > 1 ? <LineChart periods={r!.history.periods} series={[{ key: "payout", label: "Payout", color: "var(--c2)", values: payHist }]} fmt={(x) => nf(x, 0) + "%"} area height={300} /> : <p className="muted">Not enough history to chart.</p>}
        </div>
      </div>
      <div className="div3">
        <div className="card acc dv-calc" style={{ "--ac": "var(--gold)" } as React.CSSProperties}>
          <div className="card-h"><h3><span className="ci"><Icon name="wallet" /></span>What would it pay you?<ChartHelp id="div-calc" /></h3><span className="s">Drag or type</span></div>
          <label className="dv-in"><span>If you owned</span><input type="number" min={1} max={1000000} value={shares} onChange={(ev) => setShares(Math.max(1, Math.min(1000000, Math.round(Number(ev.target.value) || 1))))} aria-label="Number of shares" /><span>shares</span></label>
          <input className="dv-rng" type="range" min={1} max={1000} value={Math.min(shares, 1000)} onChange={(ev) => setShares(Number(ev.target.value))} aria-label="Shares slider" />
          <div className="dv-out">
            {price != null && <div><span className="label">You would invest</span><b>₹{nf(shares * price, 0)}</b></div>}
            <div className="hl"><span className="label">Dividends for {fy.periods[fy.periods.length - 1]}</span><b>₹{nf(shares * last, 0)}</b><small>≈ ₹{nf(monthly, 0)} a month</small></div>
            {price != null && <div><span className="label">Return on that money</span><b>{pct((last / price) * 100)}</b></div>}
          </div>
          <p className="faint" style={{ fontSize: 12, margin: "12px 0 0" }}>Based on the latest declared dividend per share and today's price, before tax. Past dividends do not guarantee future ones.</p>
        </div>
        <div className="card acc" style={{ "--ac": "var(--gold)" } as React.CSSProperties}>
          <div className="card-h"><h3><span className="ci"><Icon name="coins" /></span>When it usually pays<ChartHelp id="div-months" /></h3><span className="s">Months with past payouts</span></div>
          <div className="cal">{MONTHS.map((m, i) => <span key={m} className={paidMonths.has(i) ? "on" : ""}>{m}</span>)}</div>
          <div className="payouts">{recent.map((d, i) => <div className="pay" key={d.date + d.amount} style={{ animationDelay: `${i * 70}ms` }}><div className="pc">₹{nf(d.amount ?? 0, d.amount && d.amount % 1 ? 2 : 0)}</div><div><b>{d.type === "interim_dividend" ? "Interim" : d.type === "special_dividend" ? "Special" : "Final"}</b><span>{dateIN(d.date)}</span></div></div>)}</div>
        </div>
      </div>
      <div className="card acc dv-news" id="announcements" style={{ "--ac": "var(--info)", marginTop: 16 } as React.CSSProperties}>
        <div className="card-h"><h3><span className="ci"><Icon name="notes" /></span>Exchange announcements</h3><span className="s">Routine filings hidden</span></div>
        <ol className="tl">{e.announcements.slice(0, 6).map((a) => {
          const ok = a.link && /^https?:\/\//.test(a.link);
          const Tag = ok ? "a" : "div";
          return <li key={a.date + a.description.slice(0, 30)}><span className="tl-d">{dateIN(a.date, { day: "numeric", month: "short" })}</span><Tag className="tl-b" {...(ok ? { href: a.link!, target: "_blank", rel: "noopener noreferrer" } : {})}><span className="chip ghost">{a.category}</span><span className="tl-t">{a.description}</span>{ok && <span className="tl-go" aria-hidden="true">↗</span>}</Tag></li>;
        })}{!e.announcements.length && <li><span className="muted">No recent announcements.</span></li>}</ol>
      </div>
    </section>
  );
}

/* ---------------- How the score works ---------------- */
export function MethodSection({ s }: { s: Summary }) {
  return (
    <section className="block" style={{ "--sc": "var(--info)" } as React.CSSProperties}>
      <SectionHead id="method" no="15 · Pros, cons & Prism history" icon="info" title="Pros and cons, and how the Prism score has moved" sub="What is strong and what needs care, overall, then how the Prism score has changed over time." color="--info" />
      <div className="pc-g pc-all">
        <div className="pcb pro"><h4><Icon name="check" /> Pros <span className="chip up">{s.strengths.length}</span></h4>{s.strengths.length ? <ul>{s.strengths.map((n) => <li key={n.key}><b>{n.title}</b><small>{n.text}</small></li>)}</ul> : <p className="faint">Nothing stands out as a clear strength.</p>}</div>
        <div className="pcb con"><h4><Icon name="alert" /> Cons <span className="chip down">{s.watchouts.length}</span></h4>{s.watchouts.length ? <ul>{s.watchouts.map((n) => <li key={n.key}><b>{n.title}</b><small>{n.text}</small></li>)}</ul> : <p className="faint">No clear weakness stands out.</p>}</div>
      </div>
      <ScoreMovesCard symbol={s.meta.symbol} statement={s.meta.statement} />
    </section>
  );
}

/* ---------------- Revenue segmentation (Section 14 of the report) ---------------- */
export function SegmentCard({ seg }: { seg?: Segments }) {
  const latest = seg?.latest || [];
  const top = latest[0], conc = top?.sharePct ?? 0;
  const colors = segmentColors(segmentNames(seg)).color;  // one colour per segment, shared by the strip, the tiles, the chart and the table
  const col = (name: string) => colors[name] ?? OTHERS_COLOR;
  return (
    <div className="card acc" style={{ "--ac": "var(--p-profit)" } as React.CSSProperties}>
      <div className="card-h"><h3 className="seg-title"><span className="ci"><Icon name="pie" /></span>Revenue by business segment<ChartHelp id="segments" /></h3><span className="s">{seg?.periods[seg.periods.length - 1] || ""}</span></div>
      {latest.length ? (
        <>
          <div className="rib" role="img" aria-label="Revenue share by segment">{latest.map((x) => <span key={x.name} title={`${x.name}: ${pct(x.sharePct)}`} style={{ flex: Math.max(x.sharePct || 0, 7), "--bc": col(x.name) } as React.CSSProperties}><b className={(x.sharePct || 0) < 9 ? "xs" : ""}>{(x.sharePct || 0) >= 10 ? pct(x.sharePct, 0) : pct(x.sharePct, 1)}</b></span>)}</div>
          <ul className="seg-l2">{latest.map((x) => (
            <li key={x.name} style={{ "--bc": col(x.name) } as React.CSSProperties}>
              <div className="sl-h"><i /><b>{x.name}</b><em>{pct(x.sharePct)}</em></div>
              <div className="sl-bar"><span style={{ width: `${Math.min(100, x.sharePct || 0)}%` }} /></div>
              <div className="sl-m"><span>₹{cr(x.revenue)} Cr revenue</span><span className={x.growthPct == null ? "" : x.growthPct >= 0 ? "pos" : "neg"}>{signed(x.growthPct, 1)} vs last year</span>{x.ebit != null && x.revenue ? <span>{nf((x.ebit / x.revenue) * 100, 1)}% margin</span> : null}</div>
              {x.includes?.length ? <div className="sl-i">Includes {x.includes.join(", ")}</div> : null}
            </li>))}</ul>
          <div className={"seg-note " + (conc >= 70 ? "warn" : "")}>{conc >= 70 ? `${top.name} brings in ${nf(conc, 0)}% of revenue, so the business depends mostly on one segment.` : "Revenue is spread across several segments, which spreads the risk."}</div>
          <SegmentHistory seg={seg} />
        </>
      ) : <p className="muted">{seg ? "Segment history is not available for this company." : "This company does not report revenue by segment."}</p>}
    </div>
  );
}
