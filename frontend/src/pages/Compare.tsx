import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { Icon } from "../lib/icons";
import { PageArt } from "../components/PageArt";
import { Plain } from "../components/Plain";
import { Gate } from "../components/Gate";
import { useUI } from "../lib/ui";
import { useDocTitle } from "../lib/title";
import { nf } from "../lib/format";
import { Radar } from "../charts/Radar";
import { CompareBar } from "../components/CompareBar";
import { BAND_LABEL, METRICS, distOf, fmt, percentile, useUniverse, type Dist, type NumKey, type Row } from "../lib/screener";

type TabDef = { id: string; label: string; model?: boolean; blurb: string; groups: { title: string; keys: NumKey[] }[] };
const TABS: TabDef[] = [
  { id: "overview", label: "Overview", blurb: "Who they are and how the FinLit model scores them.", groups: [] },
  { id: "fundamentals", label: "Fundamentals", blurb: "Size, profit margin, returns on money and debt.", groups: [{ title: "Size and market", keys: ["market_cap", "price"] }, { title: "Profitability", keys: ["roe", "roce", "operating_margin"] }, { title: "Solvency and financial strength", keys: ["debt_to_equity"] }, { title: "Income for shareholders", keys: ["dividend_yield"] }] },
  { id: "spider", label: "Spider", blurb: "Eight fundamentals on one chart. Further from the centre is better.", groups: [] },
  { id: "valuation", label: "Valuation", blurb: "How much the market is paying for each company.", groups: [{ title: "Price against earnings and assets", keys: ["pe", "pb"] }, { title: "Cash return on the price", keys: ["dividend_yield"] }] },
  { id: "quality", label: "Quality & Risk", model: true, blurb: "How well the business earns, and how much debt it carries.", groups: [{ title: "Returns on money", keys: ["roe", "roce"] }, { title: "Safety", keys: ["debt_to_equity", "pillar_balance"] }, { title: "FinLit quality", keys: ["pillar_quality"] }] },
  { id: "growth", label: "Growth", model: true, blurb: "How fast sales and profit have grown.", groups: [{ title: "Business growth", keys: ["sales_cagr", "profit_cagr", "pillar_growth"] }, { title: "The market's verdict", keys: ["return_1y"] }] },
  { id: "technical", label: "Technical", model: true, blurb: "How the share price has been behaving.", groups: [{ title: "Price moves", keys: ["change_pct", "return_1m", "return_1y"] }, { title: "FinLit technical", keys: ["pillar_technical"] }] },
  { id: "custom", label: "Build your own", model: true, blurb: "Pick any measures you like.", groups: [] },
];
const SPIDER: { label: string; key: NumKey }[] = [{ label: "ROE", key: "roe" }, { label: "ROCE", key: "roce" }, { label: "Margin", key: "operating_margin" }, { label: "Sales growth", key: "sales_cagr" }, { label: "Profit growth", key: "profit_cagr" }, { label: "Low debt", key: "debt_to_equity" }, { label: "Low P/E", key: "pe" }, { label: "Dividend", key: "dividend_yield" }];
const PILLARS: NumKey[] = ["pillar_quality", "pillar_growth", "pillar_profitability", "pillar_balance", "pillar_technical"];
const ALL = Object.keys(METRICS) as NumKey[];
const LETTER = ["A", "B", "C", "D"];

function Ring({ v, band }: { v: number | null; band: string | null }) {
  const C = 2 * Math.PI * 34;
  return <div className={"cr " + (band || "")}><svg viewBox="0 0 84 84" aria-hidden="true"><circle cx="42" cy="42" r="34" fill="none" stroke="var(--s3)" strokeWidth="8" /><circle className="ring-in" cx="42" cy="42" r="34" fill="none" stroke="var(--gold)" strokeWidth="8" strokeLinecap="round" strokeDasharray={`${(C * (v ?? 0)) / 100} ${C}`} transform="rotate(-90 42 42)" /></svg><b>{v ?? "—"}</b></div>;
}

export function Compare() {
  useDocTitle("Compare companies", "Put companies side by side on size, valuation, quality, growth and price behaviour. Choose exactly which measures to compare.");
  const { has, upgrade, toast } = useUI();
  const { data, isLoading, isError } = useUniverse();
  const [sp, setSp] = useSearchParams();
  const [tab, setTab] = useState("overview");
  const [custom, setCustom] = useState<NumKey[]>(["pe", "roe", "debt_to_equity", "sales_cagr"]);
  const [off, setOff] = useState<Record<string, NumKey[]>>({});
  const rows = data?.rows || [];
  const max = has("gold") ? 4 : 2;
  const bySym = useMemo(() => new Map(rows.map((r) => [r.symbol, r])), [rows]);
  const ids = useMemo(() => (sp.get("c") || "").split(",").filter((s) => bySym.has(s)).slice(0, max), [sp, bySym, max]);

  // sensible default: Reliance against the best-scoring company in its sector
  useEffect(() => {
    if (!rows.length || sp.has("c")) return;   // only when the page is opened with nothing chosen; a member who clears or removes keeps their choice
    const a = bySym.get(ids[0] || "RELIANCE") || rows[0];
    const b = [...rows].filter((r) => r.symbol !== a.symbol && r.sector === a.sector).sort((x, y) => (y.overall ?? 0) - (x.overall ?? 0))[0] || rows.find((r) => r.symbol !== a.symbol);
    if (b) setSp({ c: [a.symbol, b.symbol].join(",") }, { replace: true });
  }, [rows, sp, bySym, setSp]);

  const picked = ids.map((s) => bySym.get(s)!).filter(Boolean);
  const setIds = (n: string[]) => setSp({ c: n.join(",") }, { replace: true });
  const T = TABS.find((t) => t.id === tab)!;
  const locked = T.model && !has("silver");
  const dists = useMemo(() => { const m = new Map<NumKey, Dist | null>(); (Object.keys(METRICS) as NumKey[]).forEach((k) => m.set(k, distOf(rows, k))); return m; }, [rows]);
  const off0 = off[tab] || [];
  const groups = tab === "custom" ? [{ title: "Your measures", keys: custom }] : T.groups.map((g) => ({ ...g, keys: g.keys.filter((k) => !off0.includes(k)) })).filter((g) => g.keys.length);
  const keys: NumKey[] = groups.flatMap((g) => g.keys);
  const pool: NumKey[] = tab === "custom" ? ALL.filter((k) => has("silver") || !METRICS[k].model) : T.groups.flatMap((g) => g.keys);
  const toggleKey = (k: NumKey) => (tab === "custom" ? setCustom((c) => (c.includes(k) ? c.filter((x) => x !== k) : [...c, k])) : setOff((o) => ({ ...o, [tab]: (o[tab] || []).includes(k) ? (o[tab] || []).filter((x) => x !== k) : [...(o[tab] || []), k] })));
  const win = (k: NumKey): string | null => {
    const m = METRICS[k]; if (m.better === "none") return null;
    const v = picked.map((r) => r[k]); if (v.filter((x) => x != null).length < 2) return null;
    const best = m.better === "higher" ? Math.max(...(v.filter((x) => x != null) as number[])) : Math.min(...(v.filter((x) => x != null) as number[]));
    const w = picked.filter((r) => r[k] === best); return w.length === 1 ? w[0].symbol : null;
  };
  const tally = picked.map((r) => keys.filter((k) => win(k) === r.symbol).length);
  const scored = keys.filter((k) => METRICS[k].better !== "none" && win(k)).length;
  const pc = (r: Row, k: NumKey) => percentile(dists.get(k) || null, k, r[k]);
  const dot = (p: number | null) => (p == null ? "" : p >= 67 ? "good" : p <= 33 ? "poor" : "mid");

  if (isError) return <div className="wrap state"><h2>Comparison is unavailable right now</h2><p>Please try again in a moment.</p></div>;
  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><PageArt kind="portfolio" />
        <div className="eyebrow">Company comparison</div><h1>Companies, side by side.</h1>
        <p>Compare size, valuation, quality, growth and price behaviour across listed Indian companies, and choose exactly what to compare.</p></div></section>
      <div className="wrap cmpw">
        {data?.sample && <div className="sample-note" role="note"><Icon name="info" /><span><b>Sample data.</b> Reliance is a real report; the other companies in this demo are fictional (symbols start with SMP-). The live site compares any listed companies.</span></div>}
        <div className="card cmp-setup">
          <div className="card-h"><h3><span className="ci"><Icon name="layers" /></span>Choose companies</h3>
            {picked.length >= 2 && <div className="cmp-acts"><button className="btn" onClick={() => setIds([ids[1], ids[0], ...ids.slice(2)])}><Icon name="arrow" />Swap first two</button><button className="btn" onClick={() => { navigator.clipboard?.writeText(location.href).then(() => toast("Link to this comparison copied."), () => toast(location.href)); }}><Icon name="spark" />Copy link</button></div>}</div>
          {isLoading ? <div className="skeleton" style={{ height: 90 }} /> : (
            <>
              <CompareBar rows={rows} ids={ids} max={max} onChange={setIds} onLimit={() => { if (!has("gold")) upgrade("gold", "Comparing up to four companies comes with the Gold plan."); else toast("You are comparing the most companies this page can show."); }} />
              {!has("gold") && <p className="cb-gold"><Icon name="lock" /> Compare up to 4 companies at once with <button className="alx-link" onClick={() => upgrade("gold", "Comparing up to four companies comes with the Gold plan.")}>Gold</button>.</p>}
            </>)}
        </div>

        <div className="cmp-tabs" role="tablist" aria-label="Comparison areas">{TABS.map((t) => <button key={t.id} role="tab" aria-selected={tab === t.id} className={tab === t.id ? "on" : ""} onClick={() => setTab(t.id)}>{t.label}{t.model && !has("silver") && <Icon name="lock" />}</button>)}</div>
        <p className="cmp-blurb">{T.blurb}</p>

        {picked.length >= 2 && !locked && tab !== "overview" && scored > 0 && (
          <Plain tone="info">{picked.map((r, i) => `${r.name} leads on ${tally[i]}`).join(" · ")} of {scored} measures. “Leads” means the better value: lower for P/E and debt, higher for returns and growth.</Plain>
        )}

        {picked.length < 2 && !isLoading && <div className="pm-empty" style={{ margin: "18px 0" }}><b>Pick at least two companies to compare.</b><p>Use the search box above: open it to browse every company, or try a popular comparison.</p></div>}
        {picked.length >= 2 && tab === "overview" && (
          <>
            <div className={"cmp-cards n" + picked.length}>{picked.map((r, i) => (
              <div className="cc" key={r.symbol}>
                <div className="cc-h"><span className="av" aria-hidden="true">{(r.name || r.symbol).slice(0, 2).toUpperCase()}</span><div><span className="tk">Company {LETTER[i]} · {r.symbol}</span><b>{r.name}</b><small>{r.sector}</small></div></div>
                <div className="cc-p"><b>{fmt(METRICS.price, r.price)}</b><span className={(r.change_pct ?? 0) >= 0 ? "pos" : "neg"}>{fmt(METRICS.change_pct, r.change_pct)}</span></div>
                <div className="cc-g"><div><span>Market cap</span><b>{fmt(METRICS.market_cap, r.market_cap)}</b></div><div><span>P/E</span><b>{fmt(METRICS.pe, r.pe)}</b></div><div><span>ROE</span><b>{fmt(METRICS.roe, r.roe)}</b></div><div><span>Debt/Equity</span><b>{fmt(METRICS.debt_to_equity, r.debt_to_equity)}</b></div></div>
                <Gate tier="silver" title="See the FinLit score" points={["Overall research score", "Five-pillar scorecard"]}>
                  <div className="cc-s"><Ring v={r.overall} band={r.band} /><div><span className="label">FinLit score</span><b>{r.overall ?? "—"}<small>/100</small></b>{r.band && <span className={"vd " + r.band}>{BAND_LABEL[r.band]}</span>}</div></div>
                </Gate>
              </div>))}</div>
            <Gate tier="silver" title="Compare the five FinLit pillars" points={["Quality, Growth, Profitability, Balance sheet, Technical", "See where each company is stronger"]}>
              <div className="card cmp-pil"><div className="card-h"><h3><span className="ci"><Icon name="quality" /></span>The five FinLit pillars</h3><span className="s">0–100, higher is better</span></div>
                <div className="pil-grid">
                  <Radar axes={PILLARS.map((k) => METRICS[k].short)} series={picked.map((r, i) => ({ key: r.symbol, label: r.name || r.symbol, cls: "k" + i, values: PILLARS.map((k) => r[k]) }))} />
                  <div>{PILLARS.map((k) => { const w = win(k); return (
                    <div className="pil-r" key={k}><span className="pil-l">{METRICS[k].short}</span>
                      <div className="pil-bars">{picked.map((r, i) => <div key={r.symbol} className={"pb k" + i + (w === r.symbol ? " win" : "")}><i style={{ width: `${r[k] ?? 0}%` }} /><b>{r[k] ?? "—"}</b></div>)}</div></div>); })}</div>
                </div>
                <div className="pil-key">{picked.map((r, i) => <span key={r.symbol}><i className={"mk k" + i} />{r.name}</span>)}</div>
              </div>
            </Gate>
          </>
        )}

        {picked.length >= 2 && tab === "spider" && (
          <div className="card cmp-pil"><div className="card-h"><h3><span className="ci"><Icon name="gauge" /></span>Eight fundamentals, against every company</h3><span className="s">Each axis: % of all companies beaten</span></div>
            <div className="pil-grid">
              <Radar axes={SPIDER.map((x) => x.label)} series={picked.map((r, i) => ({ key: r.symbol, label: r.name || r.symbol, cls: "k" + i, values: SPIDER.map((x) => pc(r, x.key)) }))} />
              <div className="sp-t" style={{ "--n": picked.length } as React.CSSProperties}><div className="sp-h" role="row"><span />{picked.map((r, i) => <span key={r.symbol} title={r.name || r.symbol}><i className={"mk k" + i} /><b>{r.symbol}</b><small>{r.name}</small></span>)}</div>{SPIDER.map((x) => (
                <div className="sp-r" key={x.key}><span className="pil-l">{x.label}</span>{picked.map((r, i) => { const p = pc(r, x.key); return <span key={r.symbol} className={"sp-v k" + i}><i className={"dt " + dot(p)} />{fmt(METRICS[x.key], r[x.key])}<small>{p == null ? "" : `beats ${p}%`}</small></span>; })}</div>))}</div>
            </div>
            <div className="pil-key">{picked.map((r, i) => <span key={r.symbol}><i className={"mk k" + i} />{r.name}</span>)}</div>
            <p className="faint cmp-foot">“Beats 82%” means the company's value is better than 82% of companies in the list, where better is lower for debt and P/E and higher for everything else.</p>
          </div>
        )}
        {picked.length >= 2 && !["overview", "spider"].includes(tab) && (
          <Gate tier="silver" title={`Unlock ${T.label}`} points={["Model-based pillar scores", "Quality, growth and price behaviour side by side", "Build your own comparison"]}>
            <div className="card cmp-t">
              <div className="cmp-pick"><span className="label">Compare on</span>{pool.map((k) => <button key={k} className={"mchip" + (keys.includes(k) ? " on" : "")} aria-pressed={keys.includes(k)} onClick={() => toggleKey(k)}>{METRICS[k].short}</button>)}</div>
              {!keys.length ? <p className="muted" style={{ padding: 16 }}>Pick at least one measure above.</p> : (
                <div className="mt" style={{ "--n": picked.length } as React.CSSProperties}>
                  <div className="mt-h"><span />{picked.map((r, i) => <span key={r.symbol}><i className={"mk k" + i} />{r.name}</span>)}</div>
                  {groups.map((g) => (
                    <div className="mt-g" key={g.title}>
                      <h4>{g.title}</h4>
                      {g.keys.map((k) => { const m = METRICS[k], w = win(k), d = dists.get(k) || null;
                        const vals = picked.map((r) => r[k]).filter((x): x is number => x != null);
                        const lo = d ? Math.min(d.p10, ...vals) : 0, hi = d ? Math.max(d.p90, ...vals) : 1, sp = hi - lo || 1, at = (v: number) => Math.max(0, Math.min(100, ((v - lo) / sp) * 100));
                        return (
                          <div className="mt-r" key={k}>
                            <div className="mt-n"><b>{m.label}</b><small>{m.say}</small>{m.better !== "none" && <em>{m.better === "higher" ? "Higher is better" : "Lower is better"}</em>}</div>
                            {picked.map((r, i) => { const v = r[k], p = pc(r, k); return (
                              <div key={r.symbol} className={"mt-c k" + i + (w === r.symbol ? " win" : "")}>
                                <b>{p != null && <i className={"dt " + dot(p)} title={`Beats ${p}% of companies`} />}{fmt(m, v)}</b>
                                {w === r.symbol ? <span className="bt-badge">Better</span> : null}
                                {p != null && <small>beats {p}% of companies</small>}
                              </div>); })}
                            {d && (
                              <div className="strip" role="img" aria-label={`Where each company sits among all companies on ${m.label}`}>
                                <span className="st-band" style={{ left: `${at(d.p10)}%`, width: `${at(d.p90) - at(d.p10)}%` }} /><span className="st-med" style={{ left: `${at(d.p50)}%` }} title={`Typical: ${fmt(m, d.p50)}`} />
                                {picked.map((r, i) => r[k] != null && <span key={r.symbol} className={"st-m k" + i} style={{ left: `${at(r[k] as number)}%` }}><i className={"mk k" + i} /></span>)}
                                <em className="st-l" style={{ left: 0 }}>{fmt(m, lo)}</em><em className="st-l mid" style={{ left: `${at(d.p50)}%` }}>typical {fmt(m, d.p50)}</em><em className="st-l" style={{ right: 0 }}>{fmt(m, hi)}</em>
                              </div>)}
                          </div>); })}
                    </div>))}
                  <div className="mt-key"><span><i className="dt good" />Better than most companies</span><span><i className="dt mid" />Around the middle</span><span><i className="dt poor" />Weaker than most</span><span><i className="st-sw" />Range most companies fall in</span></div>
                </div>)}
              {picked.length === 2 && keys.length > 0 && <p className="faint cmp-foot">Gap shown as A minus B: {keys.slice(0, 3).map((k) => { const a = picked[0][k], b = picked[1][k]; return a != null && b != null ? `${METRICS[k].short} ${a - b >= 0 ? "+" : "−"}${nf(Math.abs(a - b), METRICS[k].digits ?? 2)}` : null; }).filter(Boolean).join(" · ")}</p>}
            </div>
          </Gate>
        )}
        <p className="faint cmp-foot">A comparison shows differences; it is not advice to buy or sell. For the full story behind any number, open the company's report{picked[0] && !picked[0].sample ? <> — start with <Link to={`/stocks/${picked[0].symbol}`}>{picked[0].name}</Link></> : null}.</p>
      </div>
    </>
  );
}
