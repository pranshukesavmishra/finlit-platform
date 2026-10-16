import { useState } from "react";
import { Icon } from "../lib/icons";
import { Donut, Spark } from "../charts/Small";
import { LineChart } from "../charts/LineChart";
import { cr, dateIN, initials, nf, num, pct, signed } from "../lib/format";
import type { Events, Ownership, Ratios, Segments, Summary } from "../lib/api";
import { OWN_COLOR, ownershipSlices, PILLAR_COLOR } from "./derive";
import { SectionHead } from "./Sections";
import { Plain } from "../components/Plain";

const v = (n: string) => `var(${n})`;

/* ---------------- Ownership ---------------- */
export function OwnershipSection({ o }: { o?: Ownership }) {
  if (!o) return <section className="block"><SectionHead id="ownership" no="05 · Ownership" icon="pie" tier="basic" title="Who owns the company" color="--p-balance" /><div className="skeleton" style={{ height: 260 }} /></section>;
  const prom = o.latest.find((l) => l.key === "promoters"), fii = o.latest.find((l) => l.key === "fii"), n = o.periods.length;
  const move = [...o.latest].filter((l) => l.change1yPts != null).sort((a, b) => Math.abs(b.change1yPts!) - Math.abs(a.change1yPts!))[0];
  const trendKeys = o.latest.filter((l) => (l.value ?? 0) >= 1).map((l) => l.key);
  return (
    <section className="block" style={{ "--sc": "var(--p-balance)" } as React.CSSProperties}>
      <SectionHead id="ownership" no="05 · Ownership" icon="pie" tier="basic" title="Who owns the company" sub={`Shareholding pattern, ${o.asOf}${o.comparedWith ? `, with the change since ${o.comparedWith}` : ""}.`} color="--p-balance" />
      {prom?.value != null && <Plain>{prom.value >= 50 ? "The founders and their group hold more than half the shares, so they control big decisions." : prom.value >= 30 ? "The founders hold a large share but not outright control." : "The founders hold a small share; the company is run more by professional managers and outside investors."} {fii?.change1yPts != null && fii.change1yPts < 0 ? "Foreign funds have been selling a little, which can weigh on the price." : fii?.change1yPts != null && fii.change1yPts > 0 ? "Foreign funds have been buying, which is a vote of confidence." : ""}</Plain>}
      <div className="own2">
        <div className="card acc own-main" style={{ "--ac": "var(--p-balance)" } as React.CSSProperties}>
          <div className="own-donut"><Donut slices={ownershipSlices(o.latest)} centerValue={prom?.value == null ? "—" : nf(prom.value) + "%"} centerLabel="PROMOTER HOLDING" /></div>
          <div className="own-story">
            <div className="eyebrow">The picture</div>
            <p>{prom?.value != null && <><b>Promoters hold {nf(prom.value, 1)}%</b>{prom.value >= 50 ? ", a controlling stake." : "."} </>}{fii?.value != null && <>Foreign institutions own {nf(fii.value, 1)}%. </>}{move && <>The biggest move in a year: <b>{move.label}</b> {move.change1yPts! >= 0 ? "up" : "down"} {nf(Math.abs(move.change1yPts!), 2)} points.</>}</p>
            <div className="olegend">{o.latest.map((l) => <span key={l.key}><i style={{ background: v(OWN_COLOR[l.key] || "--faint") }} />{l.label.replace(/\s*\(.*\)/, "")}</span>)}</div>
          </div>
        </div>
        <div className="otiles2">{o.latest.map((l) => {
          const col = v(OWN_COLOR[l.key] || "--faint");
          return (
            <div className="ot" key={l.key} style={{ "--oc": col } as React.CSSProperties}>
              <div className="ot-h"><span className="label">{l.label}</span>{l.change1yPts == null ? <span className="chip ghost">Balance</span> : <span className={"chip " + (l.change1yPts >= 0 ? "up" : "down")}>{signed(l.change1yPts, 2, " pts")}</span>}</div>
              <div className="ot-v">{pct(l.value)}</div>
              <Spark values={o.series[l.key] || []} color={col} w={180} h={40} />
              <div className="ot-bar"><b style={{ width: `${Math.min(100, l.value ?? 0)}%` }} /></div>
            </div>
          );
        })}</div>
        <div className="card acc own-trend" style={{ "--ac": "var(--p-balance)" } as React.CSSProperties}>
          <div className="card-h"><h3><span className="ci"><Icon name="line" /></span>How ownership has moved</h3><span className="s">{o.periods[0]} to {o.periods[n - 1]} · hover for each quarter</span></div>
          <LineChart periods={o.periods.map((p) => p.replace(/^(\w{3})\s?(\d{2})(\d{2})$/, "$1 $3"))} series={trendKeys.map((k) => ({ key: k, label: o.latest.find((l) => l.key === k)!.label.replace(/\s*\(.*\)/, ""), color: v(OWN_COLOR[k] || "--faint"), values: o.series[k] || [] }))} fmt={(x) => nf(x, 0) + "%"} height={280} domain={[0, Math.ceil(Math.max(...trendKeys.flatMap((k) => o.series[k] || []).filter((x): x is number => x != null)) / 10) * 10]} />
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
export function DividendsSection({ e, price }: { e?: Events; price?: number | null }) {
  const [shares, setShares] = useState(100);
  if (!e) return null;
  const divs = e.actions.filter((a) => a.type.endsWith("dividend")).slice(0, 6);
  const fy = e.dividendsByFY, max = Math.max(...fy.dps, 1), avg = fy.dps.reduce((a, b) => a + b, 0) / Math.max(1, fy.dps.length);
  const growth = fy.dps.length > 1 && fy.dps[0] > 0 ? (Math.pow(fy.dps[fy.dps.length - 1] / fy.dps[0], 1 / (fy.dps.length - 1)) - 1) * 100 : null;
  const R = 46, C = 2 * Math.PI * R, yld = Math.min(100, ((e.dividendYieldTtm ?? 0) / 5) * 100);
  return (
    <section className="block" style={{ "--sc": "var(--gold-deep)" } as React.CSSProperties}>
      <SectionHead id="dividends" no="09 · Dividends & events" icon="coins" tier="basic" title="Cash returned to shareholders" sub={`Amounts are adjusted for splits and bonuses.`} color="--gold-deep" />
      {e.dividendYieldTtm != null && <Plain>For every ₹100 invested at today's price, this company pays about ₹{nf(e.dividendYieldTtm, 2)} a year in dividends. {growth != null && growth > 0 ? `The payout has grown about ${nf(growth, 1)}% a year, so shareholders are getting a rising share of profit.` : "The payout has not been growing."} {e.dividendYieldTtm < 1 ? "That is low, so this is a company to own for growth rather than income." : ""}</Plain>}
      <div className="div2">
        <div className="card acc dv-yield" style={{ "--ac": "var(--gold)" } as React.CSSProperties}>
          <div className="dv-ring"><svg viewBox="0 0 120 120" aria-hidden="true"><circle cx="60" cy="60" r={R} fill="none" stroke="var(--s3)" strokeWidth="11" /><circle className="ring-in" cx="60" cy="60" r={R} fill="none" stroke="var(--gold)" strokeWidth="11" strokeLinecap="round" strokeDasharray={`${(C * yld) / 100} ${C}`} transform="rotate(-90 60 60)" /></svg>
          <div className="dv-c"><b>{pct(e.dividendYieldTtm)}</b><span>dividend yield</span></div></div>
          <p className="faint" style={{ fontSize: 12, margin: 0 }}>Ring shows yield against a 5% scale.</p>
          <div className="dv-facts"><div><span className="label">Average per share</span><b>₹{nf(avg, 2)}</b></div>{growth != null && <div><span className="label">Yearly growth</span><b className={growth >= 0 ? "pos" : "neg"}>{signed(growth, 1)}</b></div>}</div>
        </div>
        <div className="card acc dv-chart" style={{ "--ac": "var(--gold)" } as React.CSSProperties}>
          <div className="card-h"><h3><span className="ci"><Icon name="bars" /></span>Dividend per share</h3><span className="s">₹ per financial year</span></div>
          <div className="dbars" style={{ "--avg": `${(avg / max) * 150}px` } as React.CSSProperties}>
            {fy.periods.map((p, i) => { const prv = fy.dps[i - 1], g = i && prv ? ((fy.dps[i] - prv) / prv) * 100 : null; return <div className="dcol" key={p}>{g != null && <b className={"yoy " + (g >= 0 ? "up" : "down")}>{g >= 0 ? "▲" : "▼"}{nf(Math.abs(g), 0)}%</b>}<span>₹{nf(fy.dps[i], 2)}</span><i style={{ height: Math.max(6, (fy.dps[i] / max) * 150), animationDelay: `${i * 90}ms` }} /><em>{p}</em></div>; })}
            <u className="avgline"><b>average</b></u>
          </div>
          <p className="faint" style={{ fontSize: 12, margin: "14px 0 0" }}>{fy.basis}.</p>
        </div>
        <div className="card acc dv-calc" style={{ "--ac": "var(--gold)" } as React.CSSProperties}>
          <div className="card-h"><h3><span className="ci"><Icon name="wallet" /></span>What would it pay you?</h3><span className="s">Try your own number</span></div>
          <label className="dv-in"><span>If you owned</span><input type="number" min={1} max={1000000} value={shares} onChange={(ev) => setShares(Math.max(1, Math.min(1000000, Math.round(Number(ev.target.value) || 1))))} aria-label="Number of shares" /><span>shares</span></label>
          <div className="dv-out">
            {price != null && <div><span className="label">You would invest</span><b>₹{nf(shares * price, 0)}</b></div>}
            <div className="hl"><span className="label">Dividends for {fy.periods[fy.periods.length - 1]}</span><b>₹{nf(shares * fy.dps[fy.dps.length - 1], 0)}</b></div>
            {price != null && <div><span className="label">Return on that money</span><b>{pct((fy.dps[fy.dps.length - 1] / price) * 100)}</b></div>}
          </div>
          <p className="faint" style={{ fontSize: 12, margin: "12px 0 0" }}>Based on the latest declared dividend per share and today's price, before tax. Past dividends do not guarantee future ones.</p>
        </div>
        <div className="card acc dv-coins" style={{ "--ac": "var(--gold)" } as React.CSSProperties}>
          <div className="card-h"><h3><span className="ci"><Icon name="coins" /></span>Recent payouts</h3><span className="s">Newest first</span></div>
          <div className="payouts">{divs.map((d, i) => <div className="pay" key={d.date + d.amount} style={{ animationDelay: `${i * 70}ms` }}><div className="pc">₹{nf(d.amount ?? 0, d.amount && d.amount % 1 ? 2 : 0)}</div><div><b>{d.type === "interim_dividend" ? "Interim" : d.type === "special_dividend" ? "Special" : "Final"}</b><span>{dateIN(d.date)}</span></div></div>)}</div>
        </div>
        <div className="card acc dv-news" style={{ "--ac": "var(--info)" } as React.CSSProperties}>
          <div className="card-h"><h3><span className="ci"><Icon name="notes" /></span>Exchange announcements</h3><span className="s">Routine filings hidden</span></div>
          <ol className="tl">{e.announcements.slice(0, 6).map((a) => {
            const ok = a.link && /^https?:\/\//.test(a.link);
            const Tag = ok ? "a" : "div";
            return <li key={a.date + a.description.slice(0, 30)}><span className="tl-d">{dateIN(a.date, { day: "numeric", month: "short" })}</span><Tag className="tl-b" {...(ok ? { href: a.link!, target: "_blank", rel: "noopener noreferrer" } : {})}><span className="chip ghost">{a.category}</span><span className="tl-t">{a.description}</span>{ok && <span className="tl-go" aria-hidden="true">↗</span>}</Tag></li>;
          })}{!e.announcements.length && <li><span className="muted">No recent announcements.</span></li>}</ol>
        </div>
      </div>
    </section>
  );
}

/* ---------------- How the score works ---------------- */
export function MethodSection({ s, r }: { s: Summary; r?: Ratios }) {
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
        <div className="pin-grid">{(r?.score.pillars || []).map((p) => {
          const col = v(PILLAR_COLOR[p.key] || "--gold");
          return (
            <div className="pin" key={p.key} style={{ "--pc": col } as React.CSSProperties}>
              <div className="pin-h"><span className="pin-i"><Icon name={({ quality: "quality", growth: "growth", profitability: "profit", balance: "balance", technical: "tech" } as Record<string, string>)[p.key] || "info"} /></span><b>{p.label}</b><span className="pin-s">{p.score ?? "—"}</span></div>
              <div className="pin-bar"><b style={{ width: `${p.score ?? 0}%` }} /></div>
              <ul>{p.inputs.map((i) => <li key={i.label}><span>{i.label}</span><b>{i.value == null ? "n/a" : num(i.value)}</b></li>)}</ul>
            </div>
          );
        })}</div>
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
  const total = latest.reduce((a, x) => a + (x.sharePct || 0), 0) || 1;
  return (
    <div className="card acc" style={{ "--ac": "var(--p-profit)" } as React.CSSProperties}>
      <div className="card-h"><h3><span className="ci"><Icon name="pie" /></span>Revenue segmentation</h3><span className="s">{seg?.periods[seg.periods.length - 1] || ""}</span></div>
      {latest.length ? (
        <div className="segv">
          <div className="seg-donut"><Donut slices={latest.map((x, i) => ({ v: ((x.sharePct || 0) / total) * 100, color: `--c${(i % 5) + 1}` }))} centerValue={pct(latest[0].sharePct)} centerLabel={latest[0].name.length > 16 ? latest[0].name.slice(0, 15) + "…" : latest[0].name} /></div>
          <ul className="seg-l">{latest.map((x, i) => (
            <li key={x.name} style={{ "--bc": `var(--c${(i % 5) + 1})` } as React.CSSProperties}>
              <i /><div><b>{x.name}{x.includes?.length ? <span className="faint" title={x.includes.join(", ")}> (incl. {x.includes.length})</span> : null}</b><span>₹{cr(x.revenue)} Cr · <span className={x.growthPct == null ? "" : x.growthPct >= 0 ? "pos" : "neg"}>{signed(x.growthPct, 1)}</span></span></div><em>{pct(x.sharePct)}</em>
            </li>))}</ul>
        </div>
      ) : <p className="muted">This company does not report revenue by segment.</p>}
    </div>
  );
}
