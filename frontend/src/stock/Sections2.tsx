import { useState } from "react";
import { Icon } from "../lib/icons";
import { arcPath } from "../lib/svg";

import { LineChart } from "../charts/LineChart";
import { cr, dateIN, initials, nf, num, pct, signed } from "../lib/format";
import type { Events, Ownership, Ratios, Segments, Summary } from "../lib/api";
import { OWN_COLOR, PILLAR_COLOR } from "./derive";
import { SectionHead } from "./Sections";
import { Plain } from "../components/Plain";
import { ChartHelp } from "../components/ChartHelp";
import { PrismMethod } from "./PrismCompare";

const v = (n: string) => `var(${n})`;

/* ---------------- Ownership ---------------- */
const OWN_WORDS: Record<string, string> = { promoters: "Founders and their group", fii: "Foreign funds", dii: "Indian mutual funds, insurers and banks", public: "Everyday investors and others", government: "Government" };

/** Gradient donut with a gap between slices; hover or focus a slice to read it in the centre. */
function OwnDonut({ items, hl, setHl }: { items: { key: string; label: string; value: number }[]; hl: string | null; setHl: (k: string | null) => void }) {
  if (!items.length) return null;
  const tot = items.reduce((a, i) => a + i.value, 0) || 1, R = 92, W = 30, C = 130;
  let ang = 0;
  const arcs = items.map((i) => { const sweep = (i.value / tot) * 360, a0 = ang + 1.6, a1 = ang + sweep - 1.6; ang += sweep; return { ...i, a0, a1: Math.max(a1, a0 + 0.5) }; });
  const cur = items.find((i) => i.key === hl) || items[0];
  return (
    <div className="odn">
      <svg viewBox="0 0 260 260" role="img" aria-label="Who owns the company">
        <defs>
          {items.map((i) => { const col = v(OWN_COLOR[i.key] || "--faint"); return <linearGradient key={i.key} id={`og-${i.key}`} x1="0" y1="0" x2="1" y2="1"><stop offset="0" style={{ stopColor: `color-mix(in srgb, ${col} 55%, #fff)` }} /><stop offset="1" style={{ stopColor: `color-mix(in srgb, ${col} 82%, #000)` }} /></linearGradient>; })}
          <filter id="og-glow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="6" /></filter>
        </defs>
        <circle cx={C} cy={C} r={R + W / 2 + 14} fill="none" stroke="var(--border)" strokeDasharray="1 6" />
        <circle cx={C} cy={C} r={R - W / 2 - 12} fill="none" stroke="var(--border)" />
        {arcs.map((a) => {
          const on = !hl || hl === a.key, big = hl === a.key;
          return (
            <g key={a.key} opacity={on ? 1 : 0.25} style={{ transition: "opacity .25s" }}>
              {big && <path d={arcPath(C, C, R, a.a0, a.a1)} fill="none" stroke={`url(#og-${a.key})`} strokeWidth={W} strokeLinecap="round" filter="url(#og-glow)" opacity=".55" />}
              <path className="odn-a" d={arcPath(C, C, R, a.a0, a.a1)} fill="none" stroke={`url(#og-${a.key})`} strokeWidth={big ? W + 8 : W} strokeLinecap="round" tabIndex={0} role="button" aria-label={`${a.label} ${nf(a.value, 1)}%`} onMouseEnter={() => setHl(a.key)} onMouseLeave={() => setHl(null)} onFocus={() => setHl(a.key)} onBlur={() => setHl(null)} style={{ cursor: "pointer", transition: "stroke-width .2s", outline: "none" }} />
            </g>
          );
        })}
        <text x={C} y={C - 12} textAnchor="middle" fontSize="11" letterSpacing="2" fill="var(--faint)" fontFamily="IBM Plex Sans, sans-serif" fontWeight="600">{cur.label.replace(/\s*\(.*\)/, "").toUpperCase().slice(0, 22)}</text>
        <text x={C} y={C + 28} textAnchor="middle" fontSize="50" fontFamily="Newsreader Variable, Newsreader, Georgia, serif" fill="var(--text)">{nf(cur.value, 1)}<tspan fontSize="24" fill="var(--muted)">%</tspan></text>
        <text x={C} y={C + 50} textAnchor="middle" fontSize="11" fill="var(--faint)" fontFamily="IBM Plex Sans, sans-serif">of all shares</text>
      </svg>
    </div>
  );
}

export function OwnershipSection({ o }: { o?: Ownership }) {
  const [hl, setHl] = useState<string | null>(null);
  if (!o) return <section className="block"><SectionHead id="ownership" no="08 · Ownership" icon="pie" tier="basic" title="Who owns the company" color="--p-balance" /><div className="skeleton" style={{ height: 260 }} /></section>;
  if (!o.latest?.length) return <section className="block"><SectionHead id="ownership" no="08 · Ownership" icon="pie" tier="basic" title="Who owns the company" color="--p-balance" /><p className="faint">Shareholding data for this company has not been loaded yet.</p></section>;
  const prom = o.latest.find((l) => l.key === "promoters"), fii = o.latest.find((l) => l.key === "fii"), n = o.periods.length;
  const items = o.latest.filter((l) => (l.value ?? 0) >= 1).map((l) => ({ key: l.key, label: l.label, value: l.value as number }));
  const label = (l: { label: string }) => l.label.replace(/\s*\(.*\)/, "");
  const rows = o.latest.filter((l) => (l.value ?? 0) >= 0.5).map((l) => { const st = (o.series[l.key] || []).find((x) => x != null) ?? null; return { ...l, start: st as number | null }; });
  const scale = Math.max(...rows.flatMap((r) => [r.value ?? 0, r.start ?? 0]), 1);
  const then = o.periods[0], now = o.periods[n - 1];
  return (
    <section className="block" style={{ "--sc": "var(--p-balance)" } as React.CSSProperties}>
      <SectionHead id="ownership" no="08 · Ownership" icon="pie" tier="basic" title="Who owns the company" sub={`Shareholding pattern, ${o.asOf}${o.comparedWith ? `, with the change since ${o.comparedWith}` : ""}.`} color="--p-balance" />
      {prom?.value != null && <Plain>{prom.value >= 50 ? "The founders and their group hold more than half the shares, so they control big decisions." : prom.value >= 30 ? "The founders hold a large share but not outright control." : "The founders hold a small share; the company is run more by professional managers and outside investors."} {fii?.change1yPts != null && fii.change1yPts < 0 ? "Foreign funds have been selling a little, which can weigh on the price." : fii?.change1yPts != null && fii.change1yPts > 0 ? "Foreign funds have been buying, which is a vote of confidence." : ""}</Plain>}
      <div className="own4">
        <div className="card acc own-d" style={{ "--ac": "var(--p-balance)" } as React.CSSProperties}>
          <div className="card-h"><h3><span className="ci"><Icon name="pie" /></span>Owners today<ChartHelp id="own-donut" /></h3><span className="s">Hover a slice</span></div>
          <OwnDonut items={items} hl={hl} setHl={setHl} />
          <div className="odl">{o.latest.map((l) => { const c = v(OWN_COLOR[l.key] || "--faint"); return (
            <button key={l.key} className={"odl-r" + (hl === l.key ? " on" : "")} style={{ "--oc": c } as React.CSSProperties} onMouseEnter={() => setHl(l.key)} onMouseLeave={() => setHl(null)} onFocus={() => setHl(l.key)} onBlur={() => setHl(null)}>
              <i /><span><b>{label(l)}</b><small>{OWN_WORDS[l.key] || ""}</small></span><em>{pct(l.value, 1)}</em>
            </button>); })}</div>
        </div>
        <div className="card acc own-c" style={{ "--ac": "var(--p-balance)" } as React.CSSProperties}>
          <div className="card-h"><h3><span className="ci"><Icon name="growth" /></span>Who bought and who sold<ChartHelp id="own-bought-sold" /></h3><span className="s">{then} compared with {now}</span></div>
          <div className="cmpk"><span><i className="k-then" />{then}</span><span><i className="k-now" />{now}</span></div>
          <div className="cmpl">{rows.map((r) => {
            const c = v(OWN_COLOR[r.key] || "--faint"), d = r.start == null ? 0 : (r.value as number) - r.start, flat = Math.abs(d) < 0.05;
            return (
              <div className="cmp-r" key={r.key} style={{ "--oc": c } as React.CSSProperties}>
                <div className="cr-h"><b>{label(r)}</b><span className={"cmp-d " + (flat ? "" : d > 0 ? "up" : "down")}>{flat ? "Unchanged" : d > 0 ? `▲ Bought ${nf(d, 1)} pts` : `▼ Sold ${nf(Math.abs(d), 1)} pts`}</span></div>
                <div className="cmp-b"><span className="cmp-lbl">{then}</span><div className="cmp-trk"><i className="cmp-fill then" style={{ width: `${((r.start ?? 0) / scale) * 100}%` }} /></div><span className="cmp-val">{nf(r.start ?? 0, 1)}%</span></div>
                <div className="cmp-b now"><span className="cmp-lbl">{now}</span><div className="cmp-trk"><i className="cmp-fill" style={{ width: `${((r.value ?? 0) / scale) * 100}%` }} /></div><span className="cmp-val">{nf(r.value ?? 0, 1)}%</span></div>
              </div>
            );
          })}</div>
        </div>
      </div>
    </section>
  );
}

/* ---------------- Company ---------------- */
export function BusinessSection({ s }: { s: Summary }) {
  const p = s.profile, [more, setMore] = useState(false);
  const desc = (p.description || "No description available.").replace(/\s+/g, " ");
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
            {p.website && /^[\w.-]+\.[a-z]{2,}/i.test(p.website) && <a className="chip gold" href={`https://${p.website.replace(/^https?:\/\//, "")}`} target="_blank" rel="noopener noreferrer">{p.website} ↗</a>}</div>
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
      <SectionHead id="dividends" no="11 · Dividends & events" icon="coins" tier="basic" title="Cash returned to shareholders" sub="Amounts are adjusted for splits and bonuses." color="--gold-deep" />
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
          <div className="dbars" style={{ "--avg": `${(avg / max) * 150}px` } as React.CSSProperties}>
            {fy.periods.map((p, i) => { const prv = fy.dps[i - 1], g = i && prv ? ((fy.dps[i] - prv) / prv) * 100 : null; return <div className="dcol" key={p}>{g != null && <b className={"yoy " + (g >= 0 ? "up" : "down")}>{g >= 0 ? "▲" : "▼"}{nf(Math.abs(g), 0)}%</b>}<span>₹{nf(fy.dps[i], 2)}</span><i style={{ height: Math.max(6, (fy.dps[i] / max) * 150), animationDelay: `${i * 90}ms` }} /><em>{p}</em></div>; })}
            <u className="avgline"><b>average</b></u>
          </div>
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
      <div className="card acc dv-news" style={{ "--ac": "var(--info)", marginTop: 16 } as React.CSSProperties}>
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
export function MethodSection({ s, r }: { s: Summary; r?: Ratios }) {
  const [tab, setTab] = useState(0);
  const dq = s.dataQuality, ck = dq.checks;
  const passPct = ck.total ? (ck.passed / ck.total) * 100 : 100;
  return (
    <section className="block" style={{ "--sc": "var(--info)" } as React.CSSProperties}>
      <SectionHead id="method" no="12 · Pros, cons & data" icon="info" title="Pros and cons" sub="What is strong and what needs care, overall and in each of the five areas." color="--info" />
      <div className="pc-g pc-all">
        <div className="pcb pro"><h4><Icon name="check" /> Pros <span className="chip up">{s.strengths.length}</span></h4>{s.strengths.length ? <ul>{s.strengths.map((n) => <li key={n.key}><b>{n.title}</b><small>{n.text}</small></li>)}</ul> : <p className="faint">Nothing stands out as a clear strength.</p>}</div>
        <div className="pcb con"><h4><Icon name="alert" /> Cons <span className="chip down">{s.watchouts.length}</span></h4>{s.watchouts.length ? <ul>{s.watchouts.map((n) => <li key={n.key}><b>{n.title}</b><small>{n.text}</small></li>)}</ul> : <p className="faint">No clear weakness stands out.</p>}</div>
      </div>
      <div className="mth">
        {(() => {
          const pls = r?.score.pillars || [], cur = pls[Math.min(tab, pls.length - 1)];
          if (!cur) return null;
          const col = v(PILLAR_COLOR[cur.key] || "--gold"), scored = cur.inputs.filter((i) => i.score != null);
          return (
            <div className="card acc mp" style={{ "--ac": col, "--pc": col } as React.CSSProperties}>
              <div className="card-h"><h3><span className="ci"><Icon name="gauge" /></span>Pros and cons by area</h3><span className="s">Pick a pillar</span></div>
              <div className="mp-tabs" role="tablist">{pls.map((p, i) => <button key={p.key} role="tab" aria-selected={i === tab} className={i === tab ? "on" : ""} style={{ "--pc": v(PILLAR_COLOR[p.key] || "--gold") } as React.CSSProperties} onClick={() => setTab(i)}><b>{p.score ?? "—"}</b><span>{p.label}</span></button>)}</div>
              {(() => {
                const say = (i: (typeof cur.inputs)[number]) => <li key={i.key}><b>{i.label}</b> <span className="mono">{i.value == null ? "n/a" : num(i.value)}</span><small>{i.lowerIsBetter ? "lower is better" : "higher is better"} · {i.score} points</small></li>;
                const pro = scored.filter((i) => (i.score as number) >= 76).sort((x, y) => (y.score as number) - (x.score as number)), con = scored.filter((i) => (i.score as number) <= 38).sort((x, y) => (x.score as number) - (y.score as number));
                const mid = scored.length - pro.length - con.length, missing = cur.inputs.length - scored.length;
                return (<>
                  <div className="pc-g">
                    <div className="pcb pro"><h4><Icon name="check" /> Pros</h4>{pro.length ? <ul>{pro.map(say)}</ul> : <p className="faint">Nothing stands out as strong here.</p>}</div>
                    <div className="pcb con"><h4><Icon name="alert" /> Cons</h4>{con.length ? <ul>{con.map(say)}</ul> : <p className="faint">Nothing stands out as weak here.</p>}</div>
                  </div>
                  <p className="faint" style={{ fontSize: 12.5, margin: "12px 0 0" }}>{cur.label}: {pro.length} strong, {con.length} weak{mid > 0 ? `, ${mid} in between` : ""}{missing > 0 ? `, ${missing} not available for this company` : ""}. Each input is scored 18 to 92 against fixed thresholds and averaged into the area score. Information only, not investment advice.</p>
                </>);
              })()}
            </div>
          );
        })()}
        <div className="card acc mth-dq" style={{ "--ac": ck.status === "ok" ? "var(--gain)" : "var(--warn)" } as React.CSSProperties}>
          <div className="card-h"><h3><span className="ci"><Icon name={ck.status === "ok" ? "check" : "alert"} /></span>Data checks before publishing</h3><span className="s">{ck.passed} of {ck.total} passed</span></div>
          <div className="dq-bar"><b style={{ width: `${passPct}%` }} /></div>
          <ul className="dq2">
            {ck.issues.map((i) => <li className="warn" key={i.key}><span className="w"><Icon name="alert" /></span><span>{i.message}</span></li>)}
            {dq.notes.map((n) => <li key={n}><span className="w"><Icon name="info" /></span><span>{n}</span></li>)}
            {dq.provisionalLastBar && <li><span className="w"><Icon name="info" /></span><span>The newest price point is the live quote; the daily file for that day is not published yet.</span></li>}
            <li><span className="w"><Icon name="check" /></span><span>Statements: {dq.statement}. Prices to {dq.priceAsOf ? dateIN(dq.priceAsOf) : "n/a"}. Latest results {dq.fundamentalsAsOf}. {dq.removedBadTicks.length ? `${dq.removedBadTicks.length} bad price point${dq.removedBadTicks.length > 1 ? "s" : ""} removed.` : ""}</span></li>
          </ul>
          <p className="faint" style={{ fontSize: 12, margin: "12px 0 0" }}>Reports that fail a critical check are held back.</p>
        </div>
      </div>
      <PrismMethod symbol={s.meta.symbol} statement={s.meta.statement} />
    </section>
  );
}

/* ---------------- Revenue segmentation (used in Gold insights) ---------------- */
export function SegmentCard({ seg }: { seg?: Segments }) {
  const latest = seg?.latest || [];
  const top = latest[0], conc = top?.sharePct ?? 0;
  return (
    <div className="card acc" style={{ "--ac": "var(--p-profit)" } as React.CSSProperties}>
      <div className="card-h"><h3><span className="ci"><Icon name="pie" /></span>Where the revenue comes from<ChartHelp id="segments" /></h3><span className="s">{seg?.periods[seg.periods.length - 1] || ""}</span></div>
      {latest.length ? (
        <>
          <div className="rib" role="img" aria-label="Revenue share by segment">{latest.map((x, i) => <span key={x.name} title={`${x.name}: ${pct(x.sharePct)}`} style={{ flex: Math.max(x.sharePct || 0, 7), background: `var(--c${(i % 5) + 1})` }}><b className={(x.sharePct || 0) < 9 ? "sm" : ""}>{(x.sharePct || 0) >= 10 ? pct(x.sharePct, 0) : pct(x.sharePct, 1)}</b></span>)}</div>
          <ul className="seg-l2">{latest.map((x, i) => (
            <li key={x.name} style={{ "--bc": `var(--c${(i % 5) + 1})` } as React.CSSProperties}>
              <div className="sl-h"><i /><b>{x.name}</b><em>{pct(x.sharePct)}</em></div>
              <div className="sl-bar"><span style={{ width: `${Math.min(100, x.sharePct || 0)}%` }} /></div>
              <div className="sl-m"><span>₹{cr(x.revenue)} Cr revenue</span><span className={x.growthPct == null ? "" : x.growthPct >= 0 ? "pos" : "neg"}>{signed(x.growthPct, 1)} vs last year</span>{x.ebit != null && x.revenue ? <span>{nf((x.ebit / x.revenue) * 100, 1)}% margin</span> : null}</div>
              {x.includes?.length ? <div className="sl-i">Includes {x.includes.join(", ")}</div> : null}
            </li>))}</ul>
          <div className={"seg-note " + (conc >= 70 ? "warn" : "")}>{conc >= 70 ? `${top.name} brings in ${nf(conc, 0)}% of revenue, so the business depends mostly on one segment.` : "Revenue is spread across several segments, which spreads the risk."}</div>
        </>
      ) : <p className="muted">This company does not report revenue by segment.</p>}
    </div>
  );
}
