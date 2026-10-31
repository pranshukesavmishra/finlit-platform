import { useMemo, useState, type ReactNode } from "react";
import { LineChart } from "../charts/LineChart";
import { HScroll } from "../components/HScroll";
import { usePremium, qs } from "../lib/premium";
import classes from "../data/companyClassifications.json";
import {
  DASH, GROWTH_METRICS, assetQualitySentence, assetQualityTable, buildGrowth, fallbackSources, fmt, fmtPct, fmtSignedPct, growthSentence, sectionName,
  signedSentence, snapshotSentence, valuationSentence, type DataFlag, type Factor, type GrowthPoint, type Panels, type Row,
} from "../lib/fundamentalsLogic";

/** "Show as table" switch under a chart; the table carries the same numbers as the picture. */
export function WithTable({ caption, head, rows, children }: { caption: string; head: string[]; rows: ReactNode[][]; children: ReactNode }) {
  const [on, setOn] = useState(false);
  return (
    <div className="fx-wt">
      {children}
      <div className="fx-foot"><button type="button" className="alx-link" aria-pressed={on} onClick={() => setOn(!on)}>{on ? "Hide table" : "Show as table"}</button></div>
      {on && <HScroll className="" label="table"><table className="pm-t fx-table"><caption>{caption}</caption><thead><tr>{head.map((h, i) => <th key={i} className={i ? "n" : ""}>{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j} className={j ? "n" : ""}>{c}</td>)}</tr>)}</tbody></table></HScroll>}
    </div>
  );
}

/** Horizontal bars. "vs" draws company and benchmark on each row's own scale; "signed" shares one scale around zero. */
function Bars({ rows, mode, label }: { rows: Factor[]; mode: "vs" | "signed"; label: string }) {
  const ok = rows.filter((r) => r.value != null);
  const max = Math.max(...ok.map((r) => Math.abs(r.value as number)), 1e-9);
  return (
    <div className="fx-bars" role="img" aria-label={label}>
      {rows.map((r) => {
        const v = r.value, b = r.bench ?? null, own = Math.max(Math.abs(v ?? 0), Math.abs(b ?? 0), 1e-9), scale = mode === "vs" ? own : max;
        return (
          <div className="fx-br" key={r.label}>
            <span className="fx-bl">{r.label}</span>
            <span className="fx-track">
              {v == null ? <i className="fx-na">{DASH}</i> : mode === "signed"
                ? <><s className="fx-zero" /><i className={"fx-bar " + (v < 0 ? "neg" : "pos")} style={v < 0 ? { right: "50%", width: `${(Math.abs(v) / scale) * 50}%` } : { left: "50%", width: `${(v / scale) * 50}%` }} /></>
                : b == null ? <i className="fx-na">no industry figure</i> : <><i className="fx-bar co" style={{ left: 0, width: `${(Math.abs(v) / scale) * 100}%` }} /><i className="fx-bar se" style={{ left: 0, width: `${(Math.abs(b) / scale) * 100}%` }} /></>}
            </span>
            <b className="fx-bv">{r.text}{mode === "vs" && r.benchText && r.benchText !== DASH ? <small> vs {r.benchText}</small> : null}</b>
          </div>);
      })}
    </div>
  );
}

function Panel({ kicker, title, sentence, rows, mode, foot }: { kicker: string; title: string; sentence: string; rows: Factor[]; mode: "vs" | "signed"; foot?: string }) {
  if (!rows.some((r) => r.value != null)) return (
    <div className="pm-chart card fx-panel"><div className="pm-chart-h"><div><small>{kicker}</small><b>{title}</b></div></div><p className="faint">None of these figures were reported for this company.</p></div>);
  const vs = mode === "vs";
  return (
    <div className="pm-chart card fx-panel">
      <div className="pm-chart-h"><div><small>{kicker}</small><b>{title}</b></div>{foot && <span className="faint">{foot}</span>}</div>
      <WithTable caption={sentence} head={vs ? ["Measure", "Company", "Industry"] : ["Measure", "Value", "Basis"]}
        rows={rows.map((r) => (vs ? [r.label, r.text, r.benchText ?? DASH] : [r.label, r.text, r.note ?? DASH]))}>
        <Bars rows={rows} mode={mode} label={sentence} />
      </WithTable>
    </div>
  );
}

export function KeyFactors({ p, unitNote }: { p: Panels; unitNote?: string }) {
  const valRows = p.valuation.filter((r) => r.bench != null || !/yield/i.test(r.label));
  const quality = p.quality.filter((r) => !/EBIT to interest|Net debt/.test(r.label)), multiples = p.quality.filter((r) => /EBIT to interest|Net debt/.test(r.label) && r.value != null);
  const tech = p.technicals.filter((r) => !/RSI/.test(r.label));
  const snap = p.snapshot.filter((s) => s.change != null).map((s) => ({ label: s.label, value: s.change, text: s.changeText }));
  return (
    <>
      <div className="pm-chart card fx-panel">
        <div className="pm-chart-h"><div><small>Stock DNA</small><b>The company at a glance</b></div></div>
        <dl className="fx-dna">{p.dna.map((d) => <div key={d.label}><dt>{d.label}</dt><dd>{d.text}</dd></div>)}</dl>
      </div>
      <div className="pm-two">
        <Panel kicker="Valuation" title="Valuation key factors" sentence={valuationSentence(p.valuation)} rows={valRows} mode="vs" foot="Company against its industry" />
        <Panel kicker="Quality" title="Quality key factors" sentence={signedSentence("Quality", quality)} rows={quality} mode="signed" foot="Percent" />
      </div>
      {multiples.length > 0 && <p className="pm-meta">{multiples.map((r) => `${r.label}: ${r.text}×`).join(" · ")} (average of up to 5 years)</p>}
      <div className="pm-two">
        <Panel kicker="Technicals" title="Technicals key factors" sentence={signedSentence("Technicals", tech)} rows={tech} mode="signed" foot={`RSI (14): ${p.technicals.find((r) => /RSI/.test(r.label))?.text ?? DASH}`} />
        <div className="pm-chart card fx-panel">
          <div className="pm-chart-h"><div><small>Financial snapshot</small><b>Latest period and change</b></div>{unitNote && <span className="faint">{unitNote}</span>}</div>
          <WithTable caption={snapshotSentence(p.snapshot)} head={["Line", "Latest", "Change"]} rows={p.snapshot.map((s) => [s.label, s.text, s.changeText])}>
            {snap.length ? <Bars label={snapshotSentence(p.snapshot)} mode="signed" rows={snap} /> : <p className="faint">No period-on-period changes were reported.</p>}
          </WithTable>
          {snap.length > 0 && snap.length < p.snapshot.length && <p className="faint fx-sm">Lines with no reported change are in the table only.</p>}
        </div>
      </div>
    </>
  );
}

export function GrowthPanel({ rows, period }: { rows: Row[]; period: "yearly" | "quarterly" }) {
  const [basis, setBasis] = useState<"yoy" | "qoq">("yoy");
  const b = period === "yearly" ? "yoy" : basis;
  const data: GrowthPoint[] = useMemo(() => buildGrowth(rows, period, b), [rows, period, b]);
  const last = data[data.length - 1];
  const bl = period === "yearly" ? "against the previous year" : b === "qoq" ? "against the previous quarter" : "against the same quarter last year";
  const has = data.some((d) => GROWTH_METRICS.some((m) => d[m.key] != null));
  const sentence = growthSentence(data, bl);
  const vals = data.flatMap((d) => GROWTH_METRICS.map((m) => d[m.key]).filter((v): v is number => v != null)).concat(0);
  const lo = Math.min(...vals), hi = Math.max(...vals), pad = Math.max(2, (hi - lo) * 0.1);
  return (
    <div className="pm-chart card fx-panel">
      <div className="pm-chart-h"><div><small>Growth</small><b>Profit and loss growth, {bl}</b></div>
        {period === "quarterly" && <div className="pm-seg" role="group" aria-label="Growth basis">{(["yoy", "qoq"] as const).map((x) => <button key={x} aria-pressed={basis === x} onClick={() => setBasis(x)}>{x === "yoy" ? "Year on year" : "Quarter on quarter"}</button>)}</div>}</div>
      {!has ? <p className="faint">Not enough comparable periods to work out growth for this company.</p> : (
        <WithTable caption={sentence} head={["Period", ...GROWTH_METRICS.map((m) => m.label)]} rows={data.map((d) => [d.period, ...GROWTH_METRICS.map((m) => fmtSignedPct(d[m.key], 1))])}>
          <div className="fx-tiles">{GROWTH_METRICS.map((m) => <div key={m.key}><small>{m.label}</small><b className={last?.[m.key] == null ? "" : (last[m.key] as number) < 0 ? "neg" : "pos"}>{fmtSignedPct(last?.[m.key] ?? null, 1)}</b>
            <span>{last?.period}{last?.reasons[m.key] ? ` · ${last.reasons[m.key]}` : ""}</span></div>)}</div>
          <div role="img" aria-label={sentence}>
            <LineChart periods={data.map((d) => d.period)} series={GROWTH_METRICS.map((m) => ({ key: m.key, label: m.label.replace(" growth", ""), color: m.color, values: data.map((d) => d[m.key]) }))}
              fmt={(x) => Math.round(x) + "%"} height={240} domain={[lo - pad, hi + pad]} />
          </div>
        </WithTable>)}
      <p className="faint fx-sm">Growth = (current − comparison) ÷ comparison × 100. A dash means the value or the comparison period is missing, or the comparison is zero or negative. Nothing is filled in.</p>
    </div>
  );
}

export function AssetQuality({ rows, basis }: { rows?: Row[]; basis?: string }) {
  const t = useMemo(() => assetQualityTable(rows), [rows]);
  if (!t.rows.length) return null;
  const asc = [...t.periods].reverse(), sentence = assetQualitySentence(t);
  const note = basis === "standalone" ? "Based on the bank's standalone disclosures, because consolidated ratios were not reported." : "Based on the consolidated disclosures.";
  return (
    <div className="pm-sec"><h2>Bank asset quality</h2>
      <div className="pm-chart card fx-panel">
        <div className="pm-chart-h"><div><small>Gross and net NPA, CET1 capital</small><b>{sentence}</b></div><span className="faint">Percent</span></div>
        <WithTable caption={sentence} head={["Measure", ...t.periods]} rows={t.rows.map((r) => [r.label, ...r.values.map((v) => fmtPct(v, 2))])}>
          <div role="img" aria-label={sentence}>
            <LineChart periods={asc} series={t.rows.map((r, i) => ({ key: r.category, label: r.label.replace(" %", ""), color: ["var(--loss)", "var(--c3)", "var(--gold)"][i % 3], values: [...r.values].reverse() }))} fmt={(x) => fmt(x, 1) + "%"} height={220} />
          </div>
        </WithTable>
        <p className="faint fx-sm">{note} Gross NPA is bad loans before provisions, net NPA after provisions, CET1 the bank's core capital against its risk-weighted assets. A dash means the period was not disclosed.</p>
      </div>
    </div>
  );
}

export function DataNotes({ flags, sources }: { flags?: DataFlag[]; sources?: Record<string, string> }) {
  const fl = (flags || []).filter((f) => f.message), fb = fallbackSources(sources);
  if (!fl.length && !fb.length) return null;
  return (
    <details className="fx-notes"><summary>Data notes ({fl.length + fb.length})</summary>
      <p className="faint">FinEdge is the main source. A backup provider is used only where FinEdge had nothing usable, and disagreements between the two are flagged here.</p>
      {fb.length > 0 && <ul>{fb.map((s) => <li key={s.section}><b>{s.section}</b> came from {s.source}.</li>)}</ul>}
      <ul>{fl.map((f, i) => <li key={i}><b>{[sectionName(f.section), f.metric].filter(Boolean).join(" / ")}</b> {f.message}
        {f.periods?.length ? <HScroll className="" label="table"><table className="pm-t fx-table"><thead><tr><th>Period</th><th className="n">FinEdge</th><th className="n">Backup check</th><th className="n">Difference</th></tr></thead>
          <tbody>{f.periods.map((p) => <tr key={p.period}><td>{p.period}</td><td className="n">{fmt(Number(p.finedge))}</td><td className="n">{fmt(Number(p.fallbackProvider))}</td><td className="n">{fmtPct(Number(p.differencePercent))}</td></tr>)}</tbody></table></HScroll> : null}</li>)}</ul>
    </details>
  );
}

type Hit = { symbol: string; name?: string };
const PAGE = 20;
export function CompanyBrowser({ profile, onOpen }: { profile?: { sector?: string; industry?: string }; onOpen: (symbol: string) => void }) {
  const [group, setGroup] = useState<"sector" | "industry">("sector"), [text, setText] = useState(""), [asked, setAsked] = useState<{ group: string; value: string } | null>(null);
  const [filter, setFilter] = useState(""), [page, setPage] = useState(0);
  const res = usePremium<{ items: Hit[]; total: number; value: string }>(`/fundamentals/browse${qs({ group: asked?.group, value: asked?.value })}`, !!asked);
  const options = [...new Set([...((classes as unknown as Record<string, string[]>)[group] || []), profile?.[group] || ""].filter(Boolean))].sort();
  const items = (res.data?.items || []).filter((i) => `${i.name || ""} ${i.symbol}`.toLowerCase().includes(filter.trim().toLowerCase()));
  const pages = Math.max(1, Math.ceil(items.length / PAGE)), cur = Math.min(page, pages - 1);
  const go = (g: "sector" | "industry", v: string) => { if (!v.trim()) return; setGroup(g); setText(v); setAsked({ group: g, value: v.trim() }); setFilter(""); setPage(0); };
  return (
    <details className="fx-browser"><summary>Browse companies by sector or industry</summary>
      <div className="fx-bwrap">
        {(profile?.sector || profile?.industry) && <p className="fx-sm">This company: {(["sector", "industry"] as const).filter((k) => profile?.[k]).map((k) => <button key={k} className="fchip" onClick={() => go(k, profile![k]!)}>{k === "sector" ? "Sector" : "Industry"}: {profile![k]}</button>)}</p>}
        <div className="pm-seg" role="group" aria-label="Classification type">{(["sector", "industry"] as const).map((k) => <button key={k} aria-pressed={group === k} onClick={() => { setGroup(k); setText(""); setAsked(null); }}>{k === "sector" ? "Sector" : "Industry"}</button>)}</div>
        <form className="pm-bar" onSubmit={(e) => { e.preventDefault(); go(group, text); }}>
          <label>{group === "sector" ? "Sector name" : "Industry name"}<input list={"fx-opts-" + group} value={text} maxLength={120} onChange={(e) => setText(e.target.value)} placeholder={group === "sector" ? "e.g. Private Sector Bank" : "e.g. Petroleum Products"} /></label>
          <datalist id={"fx-opts-" + group}>{options.map((o) => <option key={o} value={o} />)}</datalist>
          <button className="btn" disabled={!text.trim() || res.isFetching}>{res.isFetching ? "Searching…" : "Find companies"}</button>
        </form>
        <p className="faint fx-sm">Pick a suggestion or type an exact classification name; the list is not exhaustive.</p>
        {res.isError && <p role="alert" className="fx-err">Companies could not be loaded. Check the name and try again.</p>}
        {res.data && <div aria-live="polite">
          <p>{res.data.total} {res.data.total === 1 ? "company" : "companies"} in {res.data.value}</p>
          {res.data.items.length ? <>
            <div className="pm-bar"><label>Search within results<input value={filter} onChange={(e) => { setFilter(e.target.value); setPage(0); }} placeholder="Company name or symbol" /></label></div>
            {items.length ? <HScroll className="" label="table"><table className="pm-t"><thead><tr><th>Company</th><th>Symbol</th><th>Open</th></tr></thead>
              <tbody>{items.slice(cur * PAGE, (cur + 1) * PAGE).map((i) => <tr key={i.symbol}><td>{i.name || i.symbol}</td><td>{i.symbol}</td><td><button className="alx-link" aria-label={`Open ${i.name || i.symbol}`} onClick={() => onOpen(i.symbol)}>Open</button></td></tr>)}</tbody></table></HScroll> : <p className="faint">No companies match your filter.</p>}
            {items.length > PAGE && <div className="pm-pager"><button className="btn" disabled={cur === 0} onClick={() => setPage(cur - 1)}>Previous</button><span>Page {cur + 1} of {pages}</span><button className="btn" disabled={cur + 1 >= pages} onClick={() => setPage(cur + 1)}>Next</button></div>}
          </> : <p className="faint">No companies were found. Check the spelling or choose a suggestion.</p>}
        </div>}
      </div>
    </details>
  );
}
