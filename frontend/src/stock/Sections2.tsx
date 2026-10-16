import { useState } from "react";
import { Icon } from "../lib/icons";
import { Spark } from "../charts/Small";
import { LineChart } from "../charts/LineChart";
import { cr, dateIN, initials, nf, num, pct, signed } from "../lib/format";
import type { Events, Ownership, Ratios, Segments, Summary } from "../lib/api";
import { OWN_COLOR, PILLAR_COLOR } from "./derive";
import { SectionHead } from "./Sections";
import { Plain } from "../components/Plain";

const v = (n: string) => `var(${n})`;

/* ---------------- Ownership ---------------- */
/** Splits 100 squares between holders (largest-remainder), so "1 square = 1% of the company". */
function waffle(latest: { key: string; value: number | null }[]) {
  const items = latest.filter((l) => (l.value ?? 0) > 0), tot = items.reduce((a, l) => a + (l.value as number), 0) || 1;
  const raw = items.map((l) => ({ key: l.key, x: ((l.value as number) / tot) * 100 }));
  const base = raw.map((r) => ({ ...r, n: Math.floor(r.x) }));
  let left = 100 - base.reduce((a, r) => a + r.n, 0);
  [...base].sort((a, b) => (b.x - Math.floor(b.x)) - (a.x - Math.floor(a.x))).forEach((r) => { if (left > 0) { r.n++; left--; } });
  return base.flatMap((r) => Array.from({ length: r.n }, () => r.key));
}

export function OwnershipSection({ o }: { o?: Ownership }) {
  const [hl, setHl] = useState<string | null>(null);
  if (!o) return <section className="block"><SectionHead id="ownership" no="05 · Ownership" icon="pie" tier="basic" title="Who owns the company" color="--p-balance" /><div className="skeleton" style={{ height: 260 }} /></section>;
  const prom = o.latest.find((l) => l.key === "promoters"), fii = o.latest.find((l) => l.key === "fii"), n = o.periods.length;
  const move = [...o.latest].filter((l) => l.change1yPts != null).sort((a, b) => Math.abs(b.change1yPts!) - Math.abs(a.change1yPts!))[0];
  const cells = waffle(o.latest);
  const rows = o.latest.filter((l) => (l.value ?? 0) >= 0.5).map((l) => { const sv = (o.series[l.key] || []).find((x) => x != null) ?? null; return { ...l, start: sv as number | null }; });
  const axis = Math.max(10, Math.ceil(Math.max(...rows.flatMap((r) => [r.value ?? 0, r.start ?? 0])) / 10) * 10);
  const label = (l: { label: string }) => l.label.replace(/\s*\(.*\)/, "");
  const hold = hl ? o.latest.find((l) => l.key === hl) : prom;
  return (
    <section className="block" style={{ "--sc": "var(--p-balance)" } as React.CSSProperties}>
      <SectionHead id="ownership" no="05 · Ownership" icon="pie" tier="basic" title="Who owns the company" sub={`Shareholding pattern, ${o.asOf}${o.comparedWith ? `, with the change since ${o.comparedWith}` : ""}.`} color="--p-balance" />
      {prom?.value != null && <Plain>{prom.value >= 50 ? "The founders and their group hold more than half the shares, so they control big decisions." : prom.value >= 30 ? "The founders hold a large share but not outright control." : "The founders hold a small share; the company is run more by professional managers and outside investors."} {fii?.change1yPts != null && fii.change1yPts < 0 ? "Foreign funds have been selling a little, which can weigh on the price." : fii?.change1yPts != null && fii.change1yPts > 0 ? "Foreign funds have been buying, which is a vote of confidence." : ""}</Plain>}
      <div className="own3">
        <div className="card acc own-wf" style={{ "--ac": "var(--p-balance)" } as React.CSSProperties}>
          <div className="wf-head"><div className="eyebrow">If the company were 100 shares</div><p><b>{hold?.value != null ? nf(hold.value, 0) : "—"}</b> {hold ? `belong to ${label(hold).toLowerCase()}` : ""}</p></div>
          <div className="wf" onMouseLeave={() => setHl(null)}>{cells.map((k, i) => <i key={i} className={hl && hl !== k ? "dim" : ""} style={{ background: v(OWN_COLOR[k] || "--faint"), animationDelay: `${i * 9}ms` }} onMouseEnter={() => setHl(k)} />)}</div>
          <div className="wf-leg">{o.latest.map((l) => <button key={l.key} className={hl === l.key ? "on" : ""} onMouseEnter={() => setHl(l.key)} onFocus={() => setHl(l.key)} onMouseLeave={() => setHl(null)}><i style={{ background: v(OWN_COLOR[l.key] || "--faint") }} />{label(l)}<b>{pct(l.value, 1)}</b></button>)}</div>
        </div>
        <div className="card acc own-db" style={{ "--ac": "var(--p-balance)" } as React.CSSProperties}>
          <div className="card-h"><h3><span className="ci"><Icon name="line" /></span>Then and now</h3><span className="s">{o.periods[0]} → {o.periods[n - 1]}</span></div>
          <div className="db">{rows.map((r) => {
            const col = v(OWN_COLOR[r.key] || "--faint"), d = r.start == null ? 0 : (r.value as number) - r.start, a = ((r.start ?? 0) / axis) * 100, b = ((r.value ?? 0) / axis) * 100;
            return (
              <div className="db-r" key={r.key} style={{ "--oc": col } as React.CSSProperties}>
                <span className="db-l">{label(r)}</span>
                <div className="db-t"><i className="db-bar" style={{ left: `${Math.min(a, b)}%`, width: `${Math.abs(b - a)}%` }} /><i className="db-s" style={{ left: `${a}%` }} title={`${o.periods[0]}: ${nf(r.start ?? 0, 1)}%`} /><i className="db-e" style={{ left: `${b}%` }} title={`${o.periods[n - 1]}: ${nf(r.value ?? 0, 1)}%`} /></div>
                <span className={"db-d " + (Math.abs(d) < 0.05 ? "" : d > 0 ? "up" : "down")}>{Math.abs(d) < 0.05 ? "no change" : `${d > 0 ? "▲ +" : "▼ −"}${nf(Math.abs(d), 1)} pts`}</span>
              </div>
            );
          })}</div>
          <div className="db-axis"><span>0%</span><span>{axis / 2}%</span><span>{axis}%</span></div>
          <p className="faint" style={{ fontSize: 12, margin: "10px 0 0" }}>○ {o.periods[0]} &nbsp; ● {o.periods[n - 1]}{move ? ` · biggest move in a year: ${label(move)}` : ""}</p>
        </div>
      </div>
      <div className="otiles2">{o.latest.map((l) => {
        const col = v(OWN_COLOR[l.key] || "--faint");
        return (
          <div className="ot" key={l.key} style={{ "--oc": col } as React.CSSProperties}>
            <div className="ot-h"><span className="label">{l.label}</span>{l.change1yPts == null ? <span className="chip ghost">Balance</span> : <span className={"chip " + (l.change1yPts >= 0 ? "up" : "down")}>{signed(l.change1yPts, 2, " pts")} 1Y</span>}</div>
            <div className="ot-v">{pct(l.value)}</div>
            <Spark values={o.series[l.key] || []} color={col} w={180} h={34} />
          </div>
        );
      })}</div>
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
      <SectionHead id="business" no="08 · Company overview" icon="building" tier="basic" title={`What ${p.name.split(" ")[0]} does`} color="--p-growth" />
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
      <SectionHead id="dividends" no="09 · Dividends & events" icon="coins" tier="basic" title="Cash returned to shareholders" sub="Amounts are adjusted for splits and bonuses." color="--gold-deep" />
      {e.dividendYieldTtm != null && <Plain tone={streak >= 5 && rising >= 3 ? "good" : "info"}>For every ₹100 invested at today's price, this company pays about ₹{nf(e.dividendYieldTtm, 2)} a year. It has paid a dividend for {streak} year{streak === 1 ? "" : "s"} running{rising >= 2 ? ` and raised it ${rising} years in a row` : ""}.{payout != null ? ` It keeps about ${nf(100 - payout, 0)}% of its profit to grow the business.` : ""} {e.dividendYieldTtm < 1 ? "A low yield suggests owning it for growth rather than income." : ""}</Plain>}
      <div className="dvk">
        <div className="dk" style={{ "--dc": "var(--gold)" } as React.CSSProperties}>
          <div className="dk-ring"><svg viewBox="0 0 120 120" aria-hidden="true"><circle cx="60" cy="60" r={R} fill="none" stroke="var(--s3)" strokeWidth="10" /><circle className="ring-in" cx="60" cy="60" r={R} fill="none" stroke="var(--gold)" strokeWidth="10" strokeLinecap="round" strokeDasharray={`${(C * yld) / 100} ${C}`} transform="rotate(-90 60 60)" /></svg><b>{pct(e.dividendYieldTtm)}</b></div>
          <div><span className="label">Dividend yield</span><p>Yearly cash per ₹100 invested. Ring: against a 5% scale.</p></div>
        </div>
        <div className="dk" style={{ "--dc": "var(--c2)" } as React.CSSProperties}>
          <span className="dk-i"><Icon name="percent" /></span>
          <div><span className="label">Share of profit paid out</span><b className="dk-v">{payout == null ? "—" : nf(payout, 0) + "%"}</b>{safe && <span className={"dk-tag " + safe[1]}>{safe[0]}</span>}<p>{payout == null ? "" : payout < 40 ? "Plenty of room to keep paying." : payout < 70 ? "A balanced split between owners and growth." : "Little left over; the dividend could be harder to sustain."}</p></div>
        </div>
        <div className="dk" style={{ "--dc": "var(--gain)" } as React.CSSProperties}>
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
          <div className="card-h"><h3><span className="ci"><Icon name="bars" /></span>Dividend per share</h3><span className="s">₹ per financial year</span></div>
          <div className="dbars" style={{ "--avg": `${(avg / max) * 150}px` } as React.CSSProperties}>
            {fy.periods.map((p, i) => { const prv = fy.dps[i - 1], g = i && prv ? ((fy.dps[i] - prv) / prv) * 100 : null; return <div className="dcol" key={p}>{g != null && <b className={"yoy " + (g >= 0 ? "up" : "down")}>{g >= 0 ? "▲" : "▼"}{nf(Math.abs(g), 0)}%</b>}<span>₹{nf(fy.dps[i], 2)}</span><i style={{ height: Math.max(6, (fy.dps[i] / max) * 150), animationDelay: `${i * 90}ms` }} /><em>{p}</em></div>; })}
            <u className="avgline"><b>average</b></u>
          </div>
          <p className="faint" style={{ fontSize: 12, margin: "14px 0 0" }}>{fy.basis}.</p>
        </div>
        <div className="card acc" style={{ "--ac": "var(--c2)" } as React.CSSProperties}>
          <div className="card-h"><h3><span className="ci"><Icon name="percent" /></span>Payout ratio over time</h3><span className="s">% of profit paid as dividends</span></div>
          {payHist.filter((x) => x != null).length > 1 ? <LineChart periods={r!.history.periods} series={[{ key: "payout", label: "Payout", color: "var(--c2)", values: payHist }]} fmt={(x) => nf(x, 0) + "%"} area height={300} /> : <p className="muted">Not enough history to chart.</p>}
        </div>
      </div>
      <div className="div3">
        <div className="card acc dv-calc" style={{ "--ac": "var(--gold)" } as React.CSSProperties}>
          <div className="card-h"><h3><span className="ci"><Icon name="wallet" /></span>What would it pay you?</h3><span className="s">Drag or type</span></div>
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
          <div className="card-h"><h3><span className="ci"><Icon name="coins" /></span>When it usually pays</h3><span className="s">Months with past payouts</span></div>
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
  const dq = s.dataQuality, ck = dq.checks, ps = s.score.pillars, overall = s.score.overall ?? 0;
  const R = 54, C = 2 * Math.PI * R;
  const passPct = ck.total ? (ck.passed / ck.total) * 100 : 100;
  const bands = [["Watch", 0, 45, "--v-weak"], ["Mixed", 45, 62, "--v-mixed"], ["Healthy", 62, 78, "--v-healthy"], ["Strong", 78, 100, "--v-strong"]] as const;
  return (
    <section className="block" style={{ "--sc": "var(--info)" } as React.CSSProperties}>
      <SectionHead id="method" no="10 · Method & data" icon="info" title="How the score works" sub="Open, simple and checkable: you can redo the sum yourself." color="--info" />
      <Plain tone={overall >= 62 ? "good" : overall < 45 ? "warn" : "info"}>Think of it as five report cards averaged into one mark. A score of {overall} is "{overall >= 78 ? "strong" : overall >= 62 ? "healthy" : overall >= 45 ? "mixed" : "watch"}": {overall >= 62 ? "most areas look solid." : overall >= 45 ? "some areas are good and some need care." : "several areas need care."} It describes the business today. It is not a buy or sell call.</Plain>
      <div className="mth">
        <div className="card acc mth-eq" style={{ "--ac": "var(--info)" } as React.CSSProperties}>
          <div className="steps3">
            <div className="st"><span className="stn">1</span><b>Score every input</b><span>Each ratio is mapped to 18, 38, 58, 76 or 92 using four thresholds.</span></div>
            <div className="st"><span className="stn">2</span><b>Average into pillars</b><span>A pillar is the average of the inputs available for it.</span></div>
            <div className="st"><span className="stn">3</span><b>Average the pillars</b><span>The research score is the plain average of the five pillars.</span></div>
          </div>
          <div className="eq">
            {ps.map((p, i) => <><div className="eq-p" key={p.key} style={{ "--pc": v(PILLAR_COLOR[p.key]), animationDelay: `${i * 90}ms` } as React.CSSProperties}><b>{p.score ?? "—"}</b><span>{p.label}</span></div>{i < ps.length - 1 && <span className="eq-op" key={"o" + i}>+</span>}</>)}
            <span className="eq-op">÷ {ps.filter((p) => p.score != null).length}</span><span className="eq-op">=</span>
            <div className="eq-ring"><svg viewBox="0 0 130 130" aria-hidden="true"><circle cx="65" cy="65" r={R} fill="none" stroke="var(--s3)" strokeWidth="10" /><circle className="ring-in" cx="65" cy="65" r={R} fill="none" stroke="url(#eqg)" strokeWidth="10" strokeLinecap="round" strokeDasharray={`${(C * overall) / 100} ${C}`} transform="rotate(-90 65 65)" /><defs><linearGradient id="eqg"><stop offset="0" stopColor="var(--gold-2)" /><stop offset="1" stopColor="var(--gold-deep)" /></linearGradient></defs></svg><b>{s.score.overall ?? "—"}</b></div>
          </div>
          <div className="mscale" role="img" aria-label={`Score ${overall} on a scale from 0 to 100`}>
            <div className="mscale-bar">{bands.map(([l, a, b, c]) => <span key={l} style={{ left: `${a}%`, width: `${b - a}%`, background: v(c) }}><em>{l}</em></span>)}<i className="marker" style={{ left: `${overall}%` }}><b>{overall}</b></i></div>
            <div className="mscale-n"><span>0</span><span style={{ left: "45%" }}>45</span><span style={{ left: "62%" }}>62</span><span style={{ left: "78%" }}>78</span><span style={{ left: "100%" }}>100</span></div>
          </div>
        </div>
        {(() => {
          const pls = r?.score.pillars || [], cur = pls[Math.min(tab, pls.length - 1)];
          if (!cur) return null;
          const col = v(PILLAR_COLOR[cur.key] || "--gold"), scored = cur.inputs.filter((i) => i.score != null);
          return (
            <div className="card acc mp" style={{ "--ac": col, "--pc": col } as React.CSSProperties}>
              <div className="card-h"><h3><span className="ci"><Icon name="gauge" /></span>See how each input was scored</h3><span className="s">Pick a pillar</span></div>
              <div className="mp-tabs" role="tablist">{pls.map((p, i) => <button key={p.key} role="tab" aria-selected={i === tab} className={i === tab ? "on" : ""} style={{ "--pc": v(PILLAR_COLOR[p.key] || "--gold") } as React.CSSProperties} onClick={() => setTab(i)}><b>{p.score ?? "—"}</b><span>{p.label}</span></button>)}</div>
              <div className="mp-sum">{scored.length > 1 ? <>({scored.map((i) => i.score).join(" + ")}) ÷ {scored.length} = <b>{cur.score}</b></> : <>Score <b>{cur.score}</b></>}<span className="faint"> · {cur.label} is the average of its inputs</span></div>
              <div className="mp-rows">{cur.inputs.map((i) => {
                const SC = [18, 38, 58, 76, 92], idx = i.score == null ? -1 : SC.indexOf(i.score), th = i.lowerIsBetter ? [...i.thresholds].reverse() : i.thresholds;
                return (
                  <div className="mp-r" key={i.key}>
                    <div className="mp-n"><b>{i.label}</b><span>{i.value == null ? "n/a" : num(i.value)}</span><em>{i.lowerIsBetter ? "lower is better" : "higher is better"}</em></div>
                    <div className="lad" role="img" aria-label={`${i.label} ${i.value == null ? "not available" : num(i.value)}, scored ${i.score ?? "n/a"}`}>
                      {SC.map((sc, k) => <span key={sc} className={"z" + k + (k === idx ? " hit" : "")}>{k === idx && <i><b>{num(i.value ?? 0)}</b></i>}<em>{sc}</em></span>)}
                      <div className="lad-th">{th.map((t, k) => <span key={k} style={{ left: `${(k + 1) * 20}%` }}>{i.lowerIsBetter ? "≤" : "≥"}{t}</span>)}</div>
                    </div>
                    <div className="mp-p">{i.score ?? "—"}<small>points</small></div>
                  </div>
                );
              })}</div>
              <p className="faint" style={{ fontSize: 12, margin: "14px 0 0" }}>Each bar runs from the weakest band (left, 18 points) to the strongest (right, 92 points). The bright band is where this company's number lands.</p>
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
    </section>
  );
}

/* ---------------- Revenue segmentation (used in Gold insights) ---------------- */
export function SegmentCard({ seg }: { seg?: Segments }) {
  const latest = seg?.latest || [];
  const top = latest[0], conc = top?.sharePct ?? 0;
  return (
    <div className="card acc" style={{ "--ac": "var(--p-profit)" } as React.CSSProperties}>
      <div className="card-h"><h3><span className="ci"><Icon name="pie" /></span>Where the revenue comes from</h3><span className="s">{seg?.periods[seg.periods.length - 1] || ""}</span></div>
      {latest.length ? (
        <>
          <div className="rib" role="img" aria-label="Revenue share by segment">{latest.map((x, i) => <span key={x.name} style={{ flex: Math.max(x.sharePct || 0, 4), background: `var(--c${(i % 5) + 1})` }}><b>{(x.sharePct || 0) >= 12 ? pct(x.sharePct, 0) : ""}</b></span>)}</div>
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
