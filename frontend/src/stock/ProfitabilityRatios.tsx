import { useMemo, useState } from "react";
import { HScroll } from "../components/HScroll";
import { LineChart } from "../charts/LineChart";
import { MINUS, nf } from "../lib/format";

/** Profitability over the years, three ways to read the same eight years: a table coloured against each row's own median (with the unusual
 *  years marked), lines you can switch on and off, and a then-versus-now comparison of any two years. Ends with a reading in plain words. */

type Series = (number | null)[];
type Def = { key: string; label: string; group: "Margins" | "Tax" | "Returns"; say: string };
const DEFS: Def[] = [
  { key: "gross_margin", label: "Gross margin", group: "Margins", say: "Profit left from each ₹100 of sales after the direct cost of making or buying what was sold." },
  { key: "operating_margin", label: "Operating margin", group: "Margins", say: "Profit from the core business, after running costs and depreciation, per ₹100 of sales." },
  { key: "ebitda_margin", label: "EBITDA margin", group: "Margins", say: "Operating profit before depreciation and interest, per ₹100 of sales." },
  { key: "ebit_margin", label: "EBIT margin", group: "Margins", say: "Profit before interest and tax, per ₹100 of sales." },
  { key: "pretax_margin", label: "Pre-tax margin", group: "Margins", say: "Profit before tax, per ₹100 of sales." },
  { key: "net_margin", label: "Net margin", group: "Margins", say: "What is finally left for shareholders out of each ₹100 of sales." },
  { key: "effective_tax_rate", label: "Effective tax rate", group: "Tax", say: "The share of pre-tax profit actually paid as tax." },
  { key: "roe", label: "Return on equity", group: "Returns", say: "Net profit per ₹100 of shareholders' money in the business." },
  { key: "roce", label: "Return on capital", group: "Returns", say: "Operating profit per ₹100 of all the capital (shareholders' and lenders') in use." },
  { key: "roa", label: "Return on assets", group: "Returns", say: "Net profit per ₹100 of everything the company owns." },
  { key: "rota", label: "Return on tangible assets", group: "Returns", say: "Net profit per ₹100 of physical assets, leaving out goodwill and other intangibles." },
];
const LINE_COLORS = ["#4C8DF6", "#E8743B", "#2FB57E", "#B589F0", "#E0B341", "#E25D91", "#7BC4C4"];
const monthLabel = (p: string) => (/^FY\d{2}$/.test(p) ? `Mar 20${p.slice(2)}` : p);

const median = (v: number[]) => { const s = [...v].sort((a, b) => a - b), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
const pp = (v: number, d = 2) => (v > 0 ? "+" : v < 0 ? MINUS : "") + nf(Math.abs(v), d);

/** How far each year sits from the row's usual level, and which years are far enough from the others to be called unusual. */
function analyse(vals: Series) {
  const have = vals.filter((x): x is number => x != null);
  if (have.length < 4) return { med: null as number | null, lo: have.length ? Math.min(...have) : 0, hi: have.length ? Math.max(...have) : 0, odd: new Set<number>(), spread: 0 };   // too few years for a median, but the bars still need the real range
  const med = median(have), mad = median(have.map((x) => Math.abs(x - med))) * 1.4826 || Math.max(Math.abs(med) * 0.05, 0.01);
  const odd = new Set<number>();
  vals.forEach((x, i) => { if (x != null && Math.abs(x - med) / mad > 2.5 && Math.abs(x - med) > Math.abs(med) * 0.15) odd.add(i); });
  return { med, lo: Math.min(...have), hi: Math.max(...have), odd, spread: Math.max(...have.map((x) => Math.abs(x - med)), 1e-9) };
}

/** A calm, factual reading of the eight years, from the numbers only. */
function reading(periods: string[], rows: Record<string, Series>): { head: string; lines: [string, string][] } | null {
  const first = 0, last = periods.length - 1;
  const at = (k: string, i: number) => rows[k]?.[i] ?? null;
  const d = (k: string) => (at(k, last) != null && at(k, first) != null ? (at(k, last) as number) - (at(k, first) as number) : null);
  const m = { ebitda: d("ebitda_margin"), op: d("operating_margin"), net: d("net_margin"), roe: d("roe") };
  const lines: [string, string][] = [];
  const p0 = periods[first];
  if (m.ebitda != null && m.net != null) {
    const dep = m.ebitda != null && m.op != null ? m.ebitda - m.op : null;
    lines.push(["Margins", `EBITDA margin is ${pp(m.ebitda, 1)} pts since ${p0} at ${nf(at("ebitda_margin", last) as number, 1)}%${m.op != null ? `, operating margin ${pp(m.op, 1)} pts` : ""} and net margin ${pp(m.net, 1)} pts.${dep != null && dep > 0.3 && m.ebitda > 0 ? ` Depreciation took ${nf(dep, 1)} pts of the EBITDA gain; interest, tax and minorities took most of the rest.` : ""}`]);
  }
  const roeV = rows.roe?.filter((x): x is number => x != null) || [];
  if (m.roe != null && roeV.length >= 4) {
    const low = Math.min(...roeV), lowI = (rows.roe as Series).indexOf(low);
    lines.push(["Returns", `Return on equity is ${nf(at("roe", last) as number, 1)}%, ${m.roe >= 0 ? "above" : "below"} ${p0}'s ${nf(at("roe", first) as number, 1)}%${m.net != null && m.net > 0 && m.roe < 0 ? " even though margins are higher: the capital base has grown faster than profit" : ""}. Its lowest was ${nf(low, 1)}% in ${periods[lowI]} (${roeV.length}-year median ${nf(median(roeV), 1)}%).`]);
  }
  const tax = rows.effective_tax_rate, ta = tax ? analyse(tax) : null;
  if (tax && ta && ta.med != null) for (const i of ta.odd) {
    const net = rows.net_margin?.[i], nm = rows.net_margin ? analyse(rows.net_margin).med : null;
    if (tax[i] != null && net != null && nm != null && net > nm) lines.push(["One-off", `${periods[i]}'s tax rate of ${nf(tax[i] as number, 1)}% (usually about ${nf(ta.med, 1)}%) lifted that year's net margin to ${nf(net, 1)}%, so leave ${periods[i]} out when judging the trend.`]);
  }
  if (!lines.length) return null;
  const marginsUp = (m.net ?? 0) > 0.3 || (m.ebitda ?? 0) > 0.3, retDown = (m.roe ?? 0) < -0.3;
  const head = marginsUp && retDown ? "Margins up, returns down" : marginsUp ? "Margins and returns improving" : (m.net ?? 0) < -0.3 ? "Margins under pressure" : "Broadly steady";
  return { head, lines };
}

const HI = "76,141,246", LO = "232,116,59";   // blue above the median, orange below it
function heat(x: number | null, med: number | null, spread: number): React.CSSProperties {
  if (x == null || med == null) return {};
  const t = Math.min(1, Math.abs(x - med) / spread), rgb = x >= med ? HI : LO;
  return { background: `rgba(${rgb}, ${0.08 + t * 0.5})` };
}

function Heat({ periods, rows, defs }: { periods: string[]; rows: Record<string, Series>; defs: Def[] }) {
  const [sel, setSel] = useState(defs.find((d) => d.key === "roe")?.key || defs[0].key);
  const cur = defs.find((d) => d.key === sel) || defs[0], vals = rows[cur.key], an = analyse(vals);
  const last = periods.length - 1, now = vals[last];
  const slope = (() => { const pts = vals.map((v, i) => [i, v] as const).filter((p): p is [number, number] => p[1] != null); if (pts.length < 3) return null; const n = pts.length, sx = pts.reduce((a, p) => a + p[0], 0), sy = pts.reduce((a, p) => a + p[1], 0), sxy = pts.reduce((a, p) => a + p[0] * p[1], 0), sxx = pts.reduce((a, p) => a + p[0] * p[0], 0); return (n * sxy - sx * sy) / (n * sxx - sx * sx); })();
  const have = vals.map((v, i) => [v, i] as const).filter((p): p is [number, number] => p[0] != null);
  const best = have.length ? have.reduce((a, b) => (b[0] > a[0] ? b : a)) : null, worst = have.length ? have.reduce((a, b) => (b[0] < a[0] ? b : a)) : null;
  const groups = ["Margins", "Tax", "Returns"] as const;
  return (
    <>
      <p className="pr-key"><span>Below median</span><i className="lo" /><i className="lo2" /><i className="mid" /><i className="hi2" /><i className="hi" /><span>Above median</span><span className="pr-odd-k"><b className="pr-odd" />Unusual year (far from the other years)</span></p>
      <HScroll className="" label="profitability table">
        <table className="pr-t"><thead><tr><th>Metric</th>{periods.map((p) => <th key={p}>{monthLabel(p)}</th>)}</tr></thead>
          <tbody>{groups.flatMap((g) => { const ds = defs.filter((d) => d.group === g); return ds.length ? [<tr key={g} className="pr-g"><td colSpan={periods.length + 1}>{g}</td></tr>, ...ds.map((d) => { const a = analyse(rows[d.key]); return (
            <tr key={d.key} className={d.key === sel ? "on" : ""} onClick={() => setSel(d.key)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && setSel(d.key)} aria-selected={d.key === sel}>
              <td title={d.say}>{d.label}</td>{rows[d.key].map((x, i) => <td key={i} style={heat(x, a.med, a.spread)}>{x == null ? MINUS : <>{a.odd.has(i) && <b className="pr-odd" title="Unusual year" />}{nf(x, 2)}%</>}</td>)}</tr>); })] : []; })}</tbody></table>
      </HScroll>
      <div className="pr-sel">
        <div className="card pr-chart"><div className="pr-ch"><b>{cur.label}</b>{an.med != null && <span><i className="pr-med" />{periods.length}-year median {nf(an.med, 2)}%</span>}</div><p className="muted" style={{ margin: "2px 0 10px", fontSize: 13 }}>{cur.say}</p>
          <div className="pr-bars" role="img" aria-label={`${cur.label} by year`}>{vals.map((x, i) => { const hi = Math.max(an.hi, 0.01), lo = Math.min(an.lo, 0), h = x == null ? 0 : Math.min(100, ((Math.max(x, 0) - 0) / (hi - lo || 1)) * 100);
            return <div key={i} className={"pr-bar" + (i === last ? " now" : "")} title={`${monthLabel(periods[i])}: ${x == null ? "—" : nf(x, 2) + "%"}`}><i style={{ height: `${h}%` }} /><span>{periods[i]}</span></div>; })}
            {an.med != null && <u className="pr-line" style={{ bottom: `calc(${(Math.max(an.med, 0) / (Math.max(an.hi, 0.01) - Math.min(an.lo, 0) || 1)) * 100}% * .86 + 22px)` }} />}</div></div>
        <div className="card pr-say">
          <span className={"chip " + (now != null && an.med != null ? (Math.abs(now - an.med) < an.spread * 0.15 ? "gold" : now > an.med ? "up" : "down") : "ghost")}>
            {now == null || an.med == null ? "Not enough years" : Math.abs(now - an.med) < an.spread * 0.15 ? "Close to its usual level" : now > an.med ? "Above its usual level" : "Below its usual level"}</span>
          {now != null && an.med != null && <p>Latest ({periods[last]}): {nf(now, 2)}%, {nf(Math.abs(now - an.med), 2)} pts {now >= an.med ? "above" : "below"} its {periods.length}-year median of {nf(an.med, 2)}%.</p>}
          {slope != null && <p>Trend: {Math.abs(slope) < 0.05 ? "flat" : slope > 0 ? "rising" : "falling"} ({pp(slope, 2)} pts a year on average).</p>}
          {best && worst && <p>Best {periods[best[1]]} at {nf(best[0], 2)}%, weakest {periods[worst[1]]} at {nf(worst[0], 2)}%.</p>}</div>
      </div>
    </>
  );
}

function Lines({ periods, rows, defs }: { periods: string[]; rows: Record<string, Series>; defs: Def[] }) {
  const on0 = new Set(["ebitda_margin", "operating_margin", "net_margin", "roe", "roce", "roa"]);
  const [on, setOn] = useState<Set<string>>(() => new Set(defs.filter((d) => on0.has(d.key)).map((d) => d.key)));
  const toggle = (k: string) => setOn((s) => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n; });
  const panel = (title: string, group: Def["group"][]) => {
    const ds = defs.filter((d) => group.includes(d.group)), shown = ds.filter((d) => on.has(d.key));
    return (
      <div className="pr-pan"><h4>{title}</h4>
        <div className="pr-chips" role="group" aria-label={`${title} to show`}>{ds.map((d, i) => { const c = LINE_COLORS[i % LINE_COLORS.length]; return <button key={d.key} type="button" className={"pr-chip" + (on.has(d.key) ? " on" : "")} aria-pressed={on.has(d.key)} style={{ "--lc": c } as React.CSSProperties} onClick={() => toggle(d.key)}><i />{d.label}</button>; })}</div>
        {shown.length ? <LineChart periods={periods.map(monthLabel)} fmt={(x) => nf(x, 1) + "%"} height={260}
          series={shown.map((d) => ({ key: d.key, label: d.label, color: LINE_COLORS[ds.indexOf(d) % LINE_COLORS.length], values: rows[d.key] }))} /> : <p className="muted" style={{ padding: "36px 0", textAlign: "center" }}>Tap a ratio above to show its line.</p>}
      </div>
    );
  };
  return <div className="pr-two">{panel("Margins", ["Margins", "Tax"])}{panel("Returns", ["Returns"])}</div>;
}

function ThenNow({ periods, rows, defs }: { periods: string[]; rows: Record<string, Series>; defs: Def[] }) {
  const [a, setA] = useState(0), [b, setB] = useState(periods.length - 1);
  const groups = ["Margins", "Returns", "Tax"] as const;
  return (
    <>
      {([["From", a, setA, (i: number) => i >= b], ["To", b, setB, (i: number) => i <= a]] as const).map(([lab, val, set, dis]) => (
        <div className="pr-pick" key={lab} role="group" aria-label={`${lab} year`}><span>{lab}</span>{periods.map((p, i) => <button key={p} type="button" className={val === i ? "on" : ""} disabled={dis(i)} aria-pressed={val === i} onClick={() => set(i)}>{p}</button>)}</div>))}
      <p className="pr-leg"><i className="from" />{monthLabel(periods[a])} (from) <i className="to" />{monthLabel(periods[b])} (to) <i className="range" />Lowest to highest, {monthLabel(periods[0])} to {monthLabel(periods[periods.length - 1])}</p>
      {groups.map((g) => { const ds = defs.filter((d) => d.group === g); return ds.length ? (
        <div key={g} className="pr-tn"><div className="pr-tn-h"><b>{g}</b><span>Change</span></div>
          {ds.map((d) => { const v = rows[d.key], have = v.filter((x): x is number => x != null), lo = Math.min(...have), hi = Math.max(...have), pos = (x: number) => (hi === lo ? 50 : ((x - lo) / (hi - lo)) * 100), x0 = v[a], x1 = v[b], ch = x0 != null && x1 != null ? x1 - x0 : null;
            return <div key={d.key} className="pr-tn-r"><span className="n">{d.label}</span>
              <div className="trk"><u style={{ left: 0, right: 0 }} />{x0 != null && <i className="from" style={{ left: `${pos(x0)}%` }} />}{x1 != null && <i className="to" style={{ left: `${pos(x1)}%` }} />}{x0 != null && x1 != null && <em style={{ left: `${Math.min(pos(x0), pos(x1))}%`, width: `${Math.abs(pos(x1) - pos(x0))}%` }} />}</div>
              <span className={"ch " + (ch == null || Math.abs(ch) < 0.005 ? "" : ch > 0 ? "up" : "down")}>{ch == null ? MINUS : <>{ch > 0 ? "▲ " : ch < 0 ? "▼ " : ""}{pp(ch)} pp<small>{x0 != null ? nf(x0, 2) : MINUS} → {x1 != null ? nf(x1, 2) : MINUS}</small></>}</span></div>; })}</div>) : null; })}
    </>
  );
}

export function ProfitabilityRatios({ periods, rows }: { periods: string[]; rows: Record<string, Series> }) {
  const [view, setView] = useState<"table" | "lines" | "change">("table");
  const defs = useMemo(() => DEFS.filter((d) => rows[d.key]?.some((x) => x != null)), [rows]);
  const read = useMemo(() => reading(periods, rows), [periods, rows]);
  if (periods.length < 2 || !defs.length) return <div className="pm-empty">Profitability ratios have not been reported for this company.</div>;
  return (
    <div className="pr">
      <div className="pr-top"><div className="pm-seg" role="tablist" aria-label="How to read it">
        {([["table", "Table"], ["lines", "Trend lines"], ["change", "Then vs now"]] as const).map(([k, l]) => <button key={k} role="tab" aria-selected={view === k} aria-pressed={view === k} onClick={() => setView(k)}>{l}</button>)}</div>
        <span className="faint">Annual · {monthLabel(periods[0])} – {monthLabel(periods[periods.length - 1])}{view === "table" ? " · tap a row to chart it" : view === "lines" ? " · tap a ratio to show or hide it" : " · pick any two years"}</span></div>
      {view === "table" ? <Heat periods={periods} rows={rows} defs={defs} /> : view === "lines" ? <Lines periods={periods} rows={rows} defs={defs} /> : <ThenNow periods={periods} rows={rows} defs={defs} />}
      {defs.length < DEFS.length && <p className="faint pr-miss">Not shown for this company: {DEFS.filter((d) => !defs.includes(d)).map((d) => d.label).join(", ")}. Banks and lenders are not measured on gross, EBITDA or EBIT margin (their interest is their trade, not a cost of making goods), and a ratio also stays out when the company's statements do not hold what it needs.</p>}
      {read && view !== "table" && <div className="card pr-read"><span className="chip gold">{read.head}</span>{read.lines.map(([k, t]) => <p key={k}><b>{k}:</b> {t}</p>)}</div>}
    </div>
  );
}
