// DCF calculator (Gold): intrinsic value from a two-stage, ten-year free cash flow model, in the order of the FinLit formula sheet, with the
// checks and analysis an analyst expects around it. All arithmetic lives in lib/dcf.ts (pure and tested); this page collects inputs, can
// load a listed company's figures from its stored report (Gold, enforced by the server), and shows every step of the working.
import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router";
import { apiGet, apiSend, useSearchIndex, type ApiError, type Glossary } from "../lib/api";
import { useAuth } from "../lib/auth";
import { DEMO } from "../lib/demo";
import { Icon } from "../lib/icons";
import { useUI } from "../lib/ui";
import { useDocTitle } from "../lib/title";
import { csvText, dateIN, nf } from "../lib/format";
import { Gate } from "../components/Gate";
import { Info } from "../components/Info";
import {
  GROWTH_PRESETS, INDIA_DEFAULTS, MOS_PRESETS, STATUS_TEXT, around, costOfCapital, defaultScenarios, impliedGrowth, impliedReturn, run, scenarios, sensitivity,
  type CostOfCapital, type DcfInputs, type DcfResult, type GrowthPreset, type Issue, type Scenario,
} from "../lib/dcf";
import "../styles/dcf.css";

// ------------------------------------------------------------------------------------------------------------- form state
type Form = {
  fcf0: string; r: string; g1Preset: GrowthPreset; g1: string; g2Preset: GrowthPreset; g2: string; gT: string; marketCap: string; price: string;
  netDebt: string; mos: string; midYear: boolean; tvMethod: "gordon" | "exit"; exitMultiple: string; shares: string; symbol: string;
};
const DEFAULT: Form = { fcf0: "100", r: "12", g1Preset: "moderate", g1: "10", g2Preset: "moderate", g2: "10", gT: "5", marketCap: "2000", price: "100",
  netDebt: "1000", mos: "20", midYear: false, tvMethod: "gordon", exitMultiple: "15", shares: "", symbol: "" };
const PARAM: Record<string, keyof Form> = { fcf: "fcf0", r: "r", g1: "g1", g2: "g2", gt: "gT", mc: "marketCap", p: "price", nd: "netDebt", mos: "mos", xm: "exitMultiple", sh: "shares", sym: "symbol" };

/** "1,23,456.5" or "₹ 2,000" -> number; empty or junk -> NaN (validation then names the field). */
export const parseNum = (s: string) => { const t = s.replace(/[,\s₹%]/g, ""); return t === "" || !/^[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?$/.test(t) ? NaN : Number(t); };
const presetOf = (v: number): GrowthPreset => (Object.entries(GROWTH_PRESETS).find(([, p]) => p.value === v)?.[0] as GrowthPreset) ?? "custom";

function fromParams(sp: URLSearchParams): Form {
  const f = { ...DEFAULT };
  for (const [k, field] of Object.entries(PARAM)) { const v = sp.get(k); if (v != null) (f as Record<string, unknown>)[field] = v.slice(0, 40); }
  if (sp.get("mid") === "1") f.midYear = true;
  if (sp.get("tv") === "exit") f.tvMethod = "exit";
  f.g1Preset = presetOf(parseNum(f.g1)); f.g2Preset = presetOf(parseNum(f.g2));
  return f;
}
function toParams(f: Form): URLSearchParams {
  const sp = new URLSearchParams();
  for (const [k, field] of Object.entries(PARAM)) { const v = String(f[field]); if (v !== "" && v !== String(DEFAULT[field])) sp.set(k, v); }
  if (f.midYear) sp.set("mid", "1");
  if (f.tvMethod === "exit") sp.set("tv", "exit");
  return sp;
}
function toInputs(f: Form): DcfInputs {
  const sh = f.shares.trim() === "" ? null : parseNum(f.shares);
  return { fcf0: parseNum(f.fcf0), r: parseNum(f.r), g1: parseNum(f.g1), g2: parseNum(f.g2), gT: parseNum(f.gT), marketCap: parseNum(f.marketCap), price: parseNum(f.price),
    netDebt: parseNum(f.netDebt), mos: parseNum(f.mos), midYear: f.midYear, tvMethod: f.tvMethod, exitMultiple: f.tvMethod === "exit" ? parseNum(f.exitMultiple) : null, shares: sh };
}

// ------------------------------------------------------------------------------------------------------------- formatting
const rs = (v: number | null | undefined, d = 2) => (v == null || !Number.isFinite(v) ? "—" : (v < 0 ? "−₹" : "₹") + nf(Math.abs(v), d));
const crs = (v: number | null | undefined, d = 2) => (v == null || !Number.isFinite(v) ? "—" : (v < 0 ? "−₹" : "₹") + nf(Math.abs(v), d) + " Cr");
const pc = (v: number | null | undefined, d = 2) => (v == null || !Number.isFinite(v) ? "—" : (v < 0 ? "−" : "") + nf(Math.abs(v), d) + "%");
const sgn = (v: number, d = 2) => (v > 0 ? "+" : v < 0 ? "−" : "") + nf(Math.abs(v), d) + "%";

// ------------------------------------------------------------------------------------------------------------- help text
const H = (key: string, label: string, what: string, formula?: string, read?: string): Glossary => ({ key, label, what, formula, read } as Glossary);
const HELP: Record<string, Glossary> = {
  fcf0: H("fcf0", "Initial FCF", "The free cash flow the projection starts from (FCF₀): cash from operations minus capital expenditure, in ₹ crore.", "FCF = Cash from operations − Capex",
    "Use a normal year. If cash flow jumps around, an average of the last 3 to 5 years is steadier."),
  r: H("r", "Discount rate", "The yearly return an investor needs for the risk of this business; every future cash flow is divided by (1 + r) for each year it is away.",
    "Cost of equity = Risk-free rate + β × Equity risk premium", "For listed Indian companies it is usually 11% to 14%. Use the builder below to work it out."),
  g1: H("g1", "Growth rate (years 1–5)", "How fast free cash flow grows each year for the next five years (g₁).", "FCF_t = FCF₀ × (1 + g₁)^t, t = 1…5"),
  g2: H("g2", "Growth rate (years 6–10)", "How fast free cash flow grows each year in years 6 to 10 (g₂); usually slower than the first five.", "FCF_t = FCF_{t−1} × (1 + g₂), t = 6…10"),
  gT: H("gT", "Terminal growth rate", "The growth of free cash flow every year after year 10, forever (g_T). It must be below the discount rate.", "TV₁₀ = FCF₁₀ × (1 + g_T) ÷ (r − g_T)",
    "Most analysts use 4% to 6% for India: no business can outgrow the economy forever."),
  marketCap: H("marketCap", "Market capitalisation", "The company's total market value: share price × shares outstanding, in ₹ crore.", "Shares = Market capitalisation ÷ Share price"),
  price: H("price", "Current share price", "Today's price of one share in ₹; the intrinsic value is compared with it."),
  netDebt: H("netDebt", "Net debt", "Borrowings minus cash and cash equivalents, in ₹ crore. Enter a negative number for net cash. It is taken off enterprise value to reach the value of the shares.",
    "Equity value = Enterprise value − Net debt", "Also take off minority interest and add non-operating assets (for example surplus investments) if they are material."),
  mos: H("mos", "Margin of safety", "A discount to the intrinsic value you insist on before buying, to allow for being wrong.", "Buy price = Intrinsic value × (1 − MOS ÷ 100)",
    "Common choices: 20% for steady businesses, 30–40% for less certain ones, 50% or more for very uncertain ones."),
  shares: H("shares", "Shares outstanding", "Number of shares in crore. Left empty, it is market capitalisation ÷ price. A diluted count (including options and convertibles) is more precise."),
  exitMultiple: H("exitMultiple", "Exit multiple", "Terminal value as a multiple of year-10 free cash flow (EV ÷ FCF), instead of the growth formula.", "TV₁₀ = Multiple × FCF₁₀"),
  midYear: H("midYear", "Mid-year convention", "Cash comes in through the year, not all on its last day, so each year's FCF is discounted half a year less.", "PV = FCF_t ÷ (1 + r)^(t − 0.5)"),
};

// ------------------------------------------------------------------------------------------------------------- company data (Gold)
type Company = {
  symbol: string; name: string | null; sector: string | null; statement: string; isBank: boolean; price: number | null; priceAsOf: string | null; marketCap: number | null;
  shares: { diluted: number | null; period: string | null; implied: number | null };
  fcf: { history: { period: string; fcf: number; operating: number | null; capex: number | null }[]; latest: { period: string; fcf: number } | null; avg3: number | null; avg5: number | null; cagr3: number | null; cagr5: number | null };
  netDebt: { value: number | null; borrowings: number | null; cash: number | null; investments: number | null; period: string | null }; notes: string[];
};

function CompanyLoader({ enabled, onLoad, loaded, initial }: { enabled: boolean; onLoad: (c: Company, basis: "latest" | "avg3" | "avg5") => void; loaded: Company | null; initial: string | null }) {
  const [q, setQ] = useState("");
  const [sym, setSym] = useState<string | null>(initial);   // opened from a stock page ("Value (DCF)"): that company loads at once
  const [basis, setBasis] = useState<"latest" | "avg3" | "avg5">("latest");
  const index = useSearchIndex(enabled && q.trim().length > 0);
  const hits = useMemo(() => {
    const t = q.trim().toUpperCase();
    if (!t || !index.data) return [];
    const starts = index.data.rows.filter((r) => r[0].startsWith(t) || r[1].toUpperCase().startsWith(t));
    const has = index.data.rows.filter((r) => !starts.includes(r) && r[1].toUpperCase().includes(t));
    return [...starts, ...has].slice(0, 8);
  }, [q, index.data]);
  const company = useQuery<Company, ApiError>({ queryKey: ["dcf-company", sym], queryFn: () => apiGet(`/api/dcf/company/${encodeURIComponent(sym as string)}`), enabled: enabled && !!sym, retry: false, staleTime: 300_000 });
  useEffect(() => { if (company.data && company.data.symbol === sym) onLoad(company.data, basis); }, [company.data]);   // eslint-disable-line react-hooks/exhaustive-deps
  const c = loaded;
  return (
    <section className="card dcf-co" aria-labelledby="dcf-co-h">
      <div className="dcf-co-h"><h2 id="dcf-co-h">Start from a listed company <span className="tier gold">Gold</span></h2>
        <p className="muted">Fills free cash flow, net debt, shares, price and market capitalisation from the company's latest reported figures. Every field stays editable.</p></div>
      <div className="dcf-co-row">
        <label className="dcf-search"><Icon name="search" /><span className="sr-only">Search a company</span>
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Company name or NSE symbol" autoComplete="off" spellCheck={false} maxLength={60}
            onKeyDown={(e) => { if (e.key === "Enter" && hits[0]) { e.preventDefault(); setSym(hits[0][0]); setQ(""); } }} /></label>
        <label className="dcf-basis">Starting FCF
          <select value={basis} onChange={(e) => { const b = e.target.value as typeof basis; setBasis(b); if (company.data) onLoad(company.data, b); }}>
            <option value="latest">Latest year</option><option value="avg3">Average of 3 years</option><option value="avg5">Average of 5 years</option>
          </select></label>
      </div>
      {q.trim() && hits.length > 0 && (
        <ul className="dcf-hits" aria-label="Matching companies">{hits.map((h) => <li key={h[0]}><button onClick={() => { setSym(h[0]); setQ(""); }}><b>{h[1]}</b><span className="mono faint">{h[0]}</span></button></li>)}</ul>)}
      {q.trim() && index.data && hits.length === 0 && <p className="faint">No listed company matches “{q.trim()}”.</p>}
      {company.isFetching && <p className="muted" aria-live="polite">Loading {sym}…</p>}
      {company.isError && <p className="formerr" role="alert">{(company.error?.body?.detail as string) || "Could not load this company's figures."}</p>}
      {c && !company.isFetching && (
        <div className="dcf-src">
          <p><b>{c.name ?? c.symbol}</b> <span className="mono faint">{c.symbol}</span>{c.sector ? ` · ${c.sector}` : ""} · {c.statement} statements</p>
          <ul>
            <li>Free cash flow ({c.fcf.latest?.period ?? "—"}): {crs(c.fcf.latest?.fcf)}; 3-year average {crs(c.fcf.avg3)}; 5-year average {crs(c.fcf.avg5)}{c.fcf.cagr5 != null ? `; 5-year growth ${pc(c.fcf.cagr5)} a year` : c.fcf.cagr3 != null ? `; 3-year growth ${pc(c.fcf.cagr3)} a year` : ""}.</li>
            <li>Net debt ({c.netDebt.period ?? "—"}): borrowings {crs(c.netDebt.borrowings)} − cash {crs(c.netDebt.cash)} = {crs(c.netDebt.value)}. Investments of {crs(c.netDebt.investments)} are not counted as cash; add the liquid part if you judge it surplus.</li>
            <li>Price {rs(c.price)}{c.priceAsOf ? ` (${dateIN(c.priceAsOf.slice(0, 10))})` : ""}; market capitalisation {crs(c.marketCap, 0)}; shares {c.shares.diluted != null ? `${nf(c.shares.diluted, 2)} crore diluted (${c.shares.period})` : `${nf(c.shares.implied ?? NaN, 2)} crore (market cap ÷ price)`}.</li>
          </ul>
          {c.fcf.history.length > 0 && <p className="faint dcf-hist">FCF history: {c.fcf.history.map((h) => `${h.period} ${crs(h.fcf, 0)}`).join(" · ")}</p>}
          {c.notes.map((n) => <p key={n} className="dcf-note" role="note"><Icon name="info" />{n}</p>)}
        </div>)}
    </section>
  );
}

// ------------------------------------------------------------------------------------------------------------- inputs
function Field({ id, label, help, value, onChange, unit, error, hint, disabled, required = true }: {
  id: keyof typeof HELP | string; label: string; help?: Glossary; value: string; onChange: (v: string) => void; unit?: string; error?: string; hint?: string; disabled?: boolean; required?: boolean;
}) {
  return (
    <div className={"dcf-f" + (error ? " has-err" : "")}>
      <label htmlFor={"dcf-" + id}>{label}{required && <span className="req" aria-hidden="true">*</span>}{help && <Info g={help} />}</label>
      <div className="dcf-in">
        <input id={"dcf-" + id} inputMode="decimal" value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)} aria-invalid={!!error}
          aria-describedby={error ? `dcf-${id}-err` : hint ? `dcf-${id}-hint` : undefined} autoComplete="off" spellCheck={false} maxLength={24} />
        {unit && <span className="unit">{unit}</span>}
      </div>
      {error ? <p className="dcf-err" id={`dcf-${id}-err`}>{error}</p> : hint ? <p className="dcf-hint faint" id={`dcf-${id}-hint`}>{hint}</p> : null}
    </div>
  );
}

function GrowthField({ id, label, help, preset, value, onPreset, onValue, error }: {
  id: "g1" | "g2"; label: string; help: Glossary; preset: GrowthPreset; value: string; onPreset: (p: GrowthPreset) => void; onValue: (v: string) => void; error?: string;
}) {
  return (
    <div className={"dcf-f" + (error ? " has-err" : "")}>
      <label htmlFor={`dcf-${id}-p`}>{label}<span className="req" aria-hidden="true">*</span><Info g={help} /></label>
      <select id={`dcf-${id}-p`} value={preset} onChange={(e) => onPreset(e.target.value as GrowthPreset)}>
        {Object.entries(GROWTH_PRESETS).map(([k, p]) => <option key={k} value={k}>{p.label} ({p.value}%)</option>)}
        <option value="custom">Custom</option>
      </select>
      <div className="dcf-in"><input id={`dcf-${id}`} aria-label={`${label}, % a year`} inputMode="decimal" value={value} readOnly={preset !== "custom"} className={preset !== "custom" ? "is-ro" : ""}
        onChange={(e) => onValue(e.target.value)} aria-invalid={!!error} autoComplete="off" maxLength={12} /><span className="unit">%</span></div>
      {error && <p className="dcf-err">{error}</p>}
    </div>
  );
}

function RateBuilder({ onUse }: { onUse: (r: number) => void }) {
  const [c, setC] = useState<CostOfCapital>(INDIA_DEFAULTS);
  const res = costOfCapital(c);
  const set = (k: keyof CostOfCapital) => (e: React.ChangeEvent<HTMLInputElement>) => setC({ ...c, [k]: parseNum(e.target.value) });
  const ok = Object.values(c).every(Number.isFinite) && c.debtWeight >= 0 && c.debtWeight < 100;
  return (
    <details className="dcf-adv"><summary>Work out the discount rate (CAPM and WACC)</summary>
      <div className="dcf-grid3">
        <label>Risk-free rate %<input inputMode="decimal" defaultValue={INDIA_DEFAULTS.rf} onChange={set("rf")} /><small className="faint">10-year government bond yield (about 6.7–6.9% in 2026; check RBI or CCIL on the day)</small></label>
        <label>Beta (β)<input inputMode="decimal" defaultValue={INDIA_DEFAULTS.beta} onChange={set("beta")} /><small className="faint">How much the stock moves with the market; 1 = like the market</small></label>
        <label>Equity risk premium %<input inputMode="decimal" defaultValue={INDIA_DEFAULTS.erp} onChange={set("erp")} /><small className="faint">Extra return for owning Indian equities over bonds (about 6.5–7.5%)</small></label>
        <label>Cost of debt % (pre-tax)<input inputMode="decimal" defaultValue={INDIA_DEFAULTS.kd} onChange={set("kd")} /></label>
        <label>Tax rate %<input inputMode="decimal" defaultValue={INDIA_DEFAULTS.tax} onChange={set("tax")} /><small className="faint">25.17% under section 115BAA</small></label>
        <label>Debt share of capital %<input inputMode="decimal" defaultValue={INDIA_DEFAULTS.debtWeight} onChange={set("debtWeight")} /><small className="faint">D ÷ (D + E) at market values; 0 for the cost of equity alone</small></label>
      </div>
      {ok ? <p className="dcf-capm">Cost of equity = {nf(c.rf, 2)}% + {nf(c.beta, 2)} × {nf(c.erp, 2)}% = <b>{nf(res.ke, 2)}%</b> · after-tax cost of debt {nf(res.kdAfterTax, 2)}% · WACC <b>{nf(res.wacc, 2)}%</b>
        <button className="btn sm" type="button" onClick={() => onUse(Math.round(res.wacc * 100) / 100)}>Use {nf(res.wacc, 2)}%</button></p>
        : <p className="dcf-err">Enter every figure as a number (debt share from 0 up to 100%).</p>}
      <p className="faint">With net debt taken off later, the matching rate is the WACC (cash flows to the whole firm). Using the cost of equity instead gives a more conservative value.</p>
    </details>
  );
}

// ------------------------------------------------------------------------------------------------------------- results
function Steps({ i, res }: { i: DcfInputs; res: DcfResult }) {
  const gordon = i.tvMethod !== "exit";
  const rows: [string, string, string][] = [
    ["2–3", "Present value of FCF, years 1–10", `Σ FCF_t ÷ (1 + ${nf(i.r, 2)}%)^${i.midYear ? "(t−0.5)" : "t"} = ${crs(res.sumPv)}`],
    ["4", "Terminal value at year 10", gordon ? `${crs(res.fcf11)} ÷ (${nf(i.r, 2)}% − ${nf(i.gT, 2)}%) = ${crs(res.tv)}` : `${nf(i.exitMultiple ?? NaN, 2)} × ${crs(res.years[9].fcf)} = ${crs(res.tv)}`],
    ["5", "Present value of terminal value", `${crs(res.tv)} ÷ (1 + ${nf(i.r, 2)}%)^${i.midYear && gordon ? "9.5" : "10"} = ${crs(res.pvTv)}`],
    ["6", "Enterprise value", `${crs(res.sumPv)} + ${crs(res.pvTv)} = ${crs(res.ev)}`],
    ["7", "Equity value", `${crs(res.ev)} − ${crs(i.netDebt)} net debt = ${crs(res.equity)}`],
    ["8", "Shares outstanding", i.shares ? `${nf(res.shares, 4)} crore (entered)` : `${crs(i.marketCap)} ÷ ${rs(i.price)} = ${nf(res.shares, 4)} crore`],
    ["9", "Intrinsic value per share", `${crs(res.equity)} ÷ ${nf(res.shares, 4)} crore = ${rs(res.iv)}`],
    ["10", "Upside / downside", `(${rs(res.iv)} ÷ ${rs(i.price)} − 1) × 100 = ${sgn(res.upside)}`],
    ["11", "Buy price with margin of safety", `${rs(res.iv)} × (1 − ${nf(i.mos, 2)}%) = ${rs(res.buyPrice)}`],
  ];
  return (
    <div className="tw"><table className="dcf-steps"><caption className="sr-only">How the intrinsic value is worked out, step by step</caption>
      <thead><tr><th scope="col">Step</th><th scope="col">What</th><th scope="col">Working</th></tr></thead>
      <tbody>{rows.map(([n, what, work]) => <tr key={n}><td className="mono">{n}</td><th scope="row">{what}</th><td className="mono">{work}</td></tr>)}</tbody></table></div>
  );
}

function YearTable({ res, i }: { res: DcfResult; i: DcfInputs }) {
  return (
    <div className="tw"><table className="dcf-years"><caption className="sr-only">Projected free cash flow and its present value, year by year</caption>
      <thead><tr><th scope="col">Year</th><th scope="col" className="num">Growth</th><th scope="col" className="num">FCF (₹ Cr)</th><th scope="col" className="num">Discount factor</th><th scope="col" className="num">Present value (₹ Cr)</th></tr></thead>
      <tbody>
        {res.years.map((y) => <tr key={y.t}><th scope="row">Year {y.t}</th><td className="num">{pc(y.growth)}</td><td className="num">{nf(y.fcf, 2)}</td><td className="num">{y.factor.toFixed(6)}</td><td className="num">{nf(y.pv, 2)}</td></tr>)}
        <tr className="dcf-tv"><th scope="row">Terminal value</th><td className="num">{i.tvMethod === "exit" ? `${nf(i.exitMultiple ?? NaN, 2)}×` : pc(i.gT)}</td><td className="num">{nf(res.tv, 2)}</td>
          <td className="num">{(res.pvTv / res.tv).toFixed(6)}</td><td className="num">{nf(res.pvTv, 2)}</td></tr>
      </tbody>
      <tfoot><tr><th scope="row" colSpan={4}>Enterprise value (sum of present values)</th><td className="num"><b>{nf(res.ev, 2)}</b></td></tr></tfoot>
    </table></div>
  );
}

function PvChart({ res }: { res: DcfResult }) {
  const bars = [...res.years.map((y) => ({ k: `Y${y.t}`, v: y.pv, tv: false })), { k: "TV", v: res.pvTv, tv: true }];
  const max = Math.max(...bars.map((b) => Math.abs(b.v)), 1);
  const W = 560, Hh = 200, bw = W / bars.length;
  return (
    <figure className="dcf-chart">
      <svg viewBox={`0 0 ${W} ${Hh + 24}`} role="img" aria-label={`Present value by year; the terminal value is ${nf(res.tvShare, 0)}% of enterprise value`}>
        {bars.map((b, k) => { const h = (Math.abs(b.v) / max) * (Hh - 10); return (
          <g key={b.k}><title>{`${b.k === "TV" ? "Terminal value" : "Year " + (k + 1)}: ₹${nf(b.v, 2)} Cr`}</title>
            <rect x={k * bw + 4} y={Hh - h} width={bw - 8} height={Math.max(h, 1)} rx={3} className={b.tv ? "bar-tv" : "bar-y"} />
            <text x={k * bw + bw / 2} y={Hh + 16} textAnchor="middle" className="ax">{b.k}</text></g>); })}
      </svg>
      <figcaption className="faint">Present value of each year's free cash flow, and of the terminal value (TV): {nf(res.tvShare, 1)}% of the enterprise value comes from beyond year 10.</figcaption>
    </figure>
  );
}

function Bridge({ res, i }: { res: DcfResult; i: DcfInputs }) {
  const items: [string, number, string][] = [["PV of FCF, years 1–10", res.sumPv, "pos"], ["PV of terminal value", res.pvTv, "pos"], ["Enterprise value", res.ev, "tot"],
    [i.netDebt >= 0 ? "Less net debt" : "Add net cash", -i.netDebt, i.netDebt >= 0 ? "neg" : "pos"], ["Equity value", res.equity, "tot"]];
  const max = Math.max(...items.map((x) => Math.abs(x[1])), 1);
  return (
    <ul className="dcf-bridge" aria-label="From enterprise value to equity value">
      {items.map(([label, v, kind]) => <li key={label} className={kind}><span>{label}</span><span className="bar"><i style={{ width: `${(Math.abs(v) / max) * 100}%` }} /></span><b className="mono">{crs(v)}</b></li>)}
    </ul>
  );
}

function Grid({ title, note, i, rowKey, rows, rowLabel, colKey, cols, colLabel }: {
  title: string; note: string; i: DcfInputs; rowKey: keyof DcfInputs; rows: number[]; rowLabel: string; colKey: keyof DcfInputs; cols: number[]; colLabel: string;
}) {
  const grid = sensitivity(i, rowKey, rows, colKey, cols);
  const buy = (v: number) => v * (1 - i.mos / 100);
  const cls = (v: number | null) => (v == null ? "na" : i.price <= buy(v) ? "s-buy" : i.price > v ? "s-over" : "s-fair");
  return (
    <div className="dcf-sens">
      <h4>{title}</h4>
      <div className="tw"><table><caption className="sr-only">{title}: intrinsic value per share for each {rowLabel} (rows) and {colLabel} (columns)</caption>
        <thead><tr><th scope="col">{rowLabel} ↓ · {colLabel} →</th>{cols.map((c) => <th key={c} scope="col" className={"num" + (c === i[colKey] ? " cur" : "")}>{nf(c, 2)}%</th>)}</tr></thead>
        <tbody>{rows.map((rv, a) => <tr key={rv}><th scope="row" className={rv === i[rowKey] ? "cur" : ""}>{nf(rv, 2)}%</th>
          {grid[a].map((v, b) => <td key={b} className={"num " + cls(v) + (rv === i[rowKey] && cols[b] === i[colKey] ? " base" : "")}>{v == null ? "—" : v <= 0 ? "N/M" : rs(v)}</td>)}</tr>)}</tbody></table></div>
      <p className="faint">{note}</p>
    </div>
  );
}

function Scenarios({ i }: { i: DcfInputs }) {
  const [cases, setCases] = useState<Scenario[]>(() => defaultScenarios(i));
  useEffect(() => { setCases(defaultScenarios(i)); }, [i.g1, i.g2, i.r]);   // eslint-disable-line react-hooks/exhaustive-deps
  const out = scenarios(i, cases);
  const set = (k: number, f: keyof Scenario) => (e: React.ChangeEvent<HTMLInputElement>) => setCases(cases.map((c, j) => (j === k ? { ...c, [f]: parseNum(e.target.value) } : c)));
  return (
    <div className="tw"><table className="dcf-scen"><caption className="sr-only">Bear, base and bull cases and their probability-weighted value</caption>
      <thead><tr><th scope="col">Case</th><th scope="col" className="num">Probability %</th><th scope="col" className="num">Growth 1–5 %</th><th scope="col" className="num">Growth 6–10 %</th><th scope="col" className="num">Discount rate %</th><th scope="col" className="num">Value per share</th><th scope="col" className="num">vs price</th></tr></thead>
      <tbody>{out.rows.map((row, k) => <tr key={row.s.key}><th scope="row">{row.s.label}</th>
        {(["probability", "g1", "g2", "r"] as const).map((f) => <td key={f} className="num"><input aria-label={`${row.s.label} ${f}`} inputMode="decimal" defaultValue={String(row.s[f])} key={`${f}-${row.s[f]}`} onBlur={set(k, f)} /></td>)}
        <td className="num">{row.iv == null ? "—" : rs(row.iv)}</td><td className="num">{row.upside == null ? "—" : sgn(row.upside, 1)}</td></tr>)}</tbody>
      <tfoot><tr><th scope="row" colSpan={5}>Probability-weighted value {Math.abs(out.probabilityTotal - 100) > 1e-9 ? <span className="dcf-err">(probabilities add up to {nf(out.probabilityTotal, 1)}%, not 100%)</span> : null}</th>
        <td className="num"><b>{out.weighted == null ? "—" : rs(out.weighted)}</b></td><td className="num">{out.weighted == null ? "—" : sgn((out.weighted / i.price - 1) * 100, 1)}</td></tr></tfoot>
    </table></div>
  );
}

function exportCsv(i: DcfInputs, res: DcfResult, symbol: string) {
  const lines: (string | number)[][] = [["FinLit DCF calculator", symbol || "custom inputs", new Date().toISOString().slice(0, 10)], [],
    ["Input", "Value"], ["Initial FCF (Rs Cr)", i.fcf0], ["Discount rate %", i.r], ["Growth years 1-5 %", i.g1], ["Growth years 6-10 %", i.g2],
    [i.tvMethod === "exit" ? "Exit multiple (x FCF10)" : "Terminal growth %", i.tvMethod === "exit" ? i.exitMultiple ?? "" : i.gT], ["Market capitalisation (Rs Cr)", i.marketCap],
    ["Current share price (Rs)", i.price], ["Net debt (Rs Cr)", i.netDebt], ["Margin of safety %", i.mos], ["Mid-year convention", i.midYear ? "yes" : "no"], ["Shares (crore)", res.shares], [],
    ["Year", "Growth %", "FCF (Rs Cr)", "Discount factor", "PV (Rs Cr)"], ...res.years.map((y) => [y.t, y.growth, y.fcf, y.factor, y.pv]), ["Terminal value", "", res.tv, res.pvTv / res.tv, res.pvTv], [],
    ["Result", "Value"], ["Enterprise value (Rs Cr)", res.ev], ["Equity value (Rs Cr)", res.equity], ["Intrinsic value per share (Rs)", res.iv], ["Upside %", res.upside],
    ["Buy price (Rs)", res.buyPrice], ["Status", STATUS_TEXT[res.status].label], ["Terminal value share of EV %", res.tvShare]];
  const csv = lines.map((r) => r.map((c) => { const s = csvText(String(c)); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; }).join(",")).join("\r\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
  a.download = `finlit-dcf-${symbol || "custom"}.csv`;
  a.click();
  URL.revokeObjectURL(a.href);
}

type Saved = { name: string; symbol: string | null; note: string | null; updatedAt: string; inputs: DcfInputs & { g1Preset?: GrowthPreset; g2Preset?: GrowthPreset } };
function SavedScenarios({ enabled, form, onOpen }: { enabled: boolean; form: Form; onOpen: (f: Form) => void }) {
  const qc = useQueryClient();
  const { toast } = useUI();
  const list = useQuery<{ scenarios: Saved[]; max: number }, ApiError>({ queryKey: ["dcf-scenarios"], queryFn: () => apiGet("/api/dcf/scenarios"), enabled, retry: false });
  const [name, setName] = useState("");
  const save = async () => {
    const n = name.trim() || (form.symbol ? `${form.symbol} ${new Date().toISOString().slice(0, 10)}` : "");
    if (!n) { toast("Give the scenario a name."); return; }
    const i = toInputs(form);
    try {
      await apiSend("PUT", `/api/dcf/scenarios/${encodeURIComponent(n)}`, { inputs: { ...i, shares: i.shares ?? null, exitMultiple: i.exitMultiple ?? null, g1Preset: form.g1Preset, g2Preset: form.g2Preset }, symbol: form.symbol || null });
      setName(""); toast(`Saved “${n}”.`); qc.invalidateQueries({ queryKey: ["dcf-scenarios"] });
    } catch (e) { toast((e as ApiError)?.body?.detail as string || "Could not save: check that every input is a number."); }
  };
  const remove = async (n: string) => { await apiSend("DELETE", `/api/dcf/scenarios/${encodeURIComponent(n)}`); qc.invalidateQueries({ queryKey: ["dcf-scenarios"] }); };
  const open = (s: Saved) => { const x = s.inputs; onOpen({ ...DEFAULT, fcf0: String(x.fcf0), r: String(x.r), g1: String(x.g1), g2: String(x.g2), gT: String(x.gT), marketCap: String(x.marketCap), price: String(x.price),
    netDebt: String(x.netDebt), mos: String(x.mos), midYear: !!x.midYear, tvMethod: x.tvMethod === "exit" ? "exit" : "gordon", exitMultiple: x.exitMultiple != null ? String(x.exitMultiple) : DEFAULT.exitMultiple,
    shares: x.shares != null ? String(x.shares) : "", symbol: s.symbol ?? "", g1Preset: x.g1Preset ?? presetOf(x.g1), g2Preset: x.g2Preset ?? presetOf(x.g2) }); };
  if (DEMO) return <p className="faint">Saving scenarios needs a FinLit account; the share link above keeps your inputs.</p>;
  return (
    <div className="dcf-saved">
      <div className="dcf-save-row"><input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name this scenario" maxLength={80} aria-label="Scenario name" />
        <button className="btn" type="button" onClick={save} disabled={!enabled}>Save scenario</button></div>
      {list.isError && <p className="formerr">{(list.error?.body?.detail as string) || "Saved scenarios could not be loaded."}</p>}
      {list.data && (list.data.scenarios.length ? (
        <ul>{list.data.scenarios.map((s) => <li key={s.name}><button className="link" onClick={() => open(s)}><b>{s.name}</b></button>
          <span className="faint">{s.symbol ? `${s.symbol} · ` : ""}{dateIN(s.updatedAt.slice(0, 10))}</span>
          <button className="alx-link" onClick={() => remove(s.name)} aria-label={`Delete ${s.name}`}>Delete</button></li>)}</ul>)
        : <p className="faint">No saved scenarios yet (up to {list.data.max}).</p>)}
    </div>
  );
}

// ------------------------------------------------------------------------------------------------------------- page
export function DcfPage() {
  useDocTitle("DCF calculator", "Discounted cash flow (DCF) calculator: intrinsic value per share, margin of safety, sensitivity and reverse DCF, with the working shown step by step.");
  const { has } = useUI();
  const { user } = useAuth();
  const gold = has("gold");
  const [sp, setSp] = useSearchParams();
  const [form, setForm] = useState<Form>(() => fromParams(sp));
  const [loaded, setLoaded] = useState<Company | null>(null);
  const { toast } = useUI();
  useEffect(() => { const h = window.setTimeout(() => setSp(toParams(form), { replace: true }), 300); return () => window.clearTimeout(h); }, [form]);   // eslint-disable-line react-hooks/exhaustive-deps

  const set = <K extends keyof Form>(k: K) => (v: Form[K]) => setForm((f) => ({ ...f, [k]: v }));
  const preset = (k: "g1" | "g2") => (p: GrowthPreset) => setForm((f) => ({ ...f, [`${k}Preset`]: p, [k]: p === "custom" ? f[k] : String(GROWTH_PRESETS[p].value) }));
  const inputs = useMemo(() => toInputs(form), [form]);
  const out = useMemo(() => run(inputs), [inputs]);
  const err = (k: string) => out.errors.find((e) => e.field === k)?.text;
  const res = out.result;
  const ig = useMemo(() => (res ? impliedGrowth(inputs) : null), [res, inputs]);
  const ir = useMemo(() => (res ? impliedReturn(inputs) : null), [res, inputs]);

  const onCompany = (c: Company, basis: "latest" | "avg3" | "avg5") => {
    const fcf = basis === "avg3" ? c.fcf.avg3 : basis === "avg5" ? c.fcf.avg5 : c.fcf.latest?.fcf;
    setLoaded(c);
    setForm((f) => ({ ...f, symbol: c.symbol, fcf0: fcf != null ? String(Math.round(fcf * 100) / 100) : "", price: c.price != null ? String(c.price) : f.price,
      marketCap: c.marketCap != null ? String(Math.round(c.marketCap * 100) / 100) : f.marketCap, netDebt: c.netDebt.value != null ? String(Math.round(c.netDebt.value * 100) / 100) : "",
      shares: c.shares.diluted != null ? String(c.shares.diluted) : "" }));
    if (fcf == null) toast("This company has no free cash flow figure for that choice; enter one by hand.");
  };

  const copyLink = async () => { try { await navigator.clipboard.writeText(location.href); toast("Link copied: it opens the calculator with these inputs."); } catch { toast("Copy the address from the browser bar."); } };

  return (
    <>
      <section className="pagehead"><div className="wrap"><div className="eyebrow">Gold tool</div><h1>DCF Calculator</h1>
        <p>Wish to calculate the intrinsic value of companies with ease? Here's our Discounted Cash Flow (DCF) calculator, so you don't have to break your head over complicated Excel sheets. Every step of the working is shown, with checks that stop impossible assumptions.</p></div></section>
      <div className="wrap dcf">
        <Gate tier="gold" title="DCF calculator" points={["Intrinsic value per share, margin of safety and buy price", "Load any listed company's cash flow, debt and shares", "Sensitivity grids, reverse DCF and bear/base/bull cases", "Save scenarios, share links and export to Excel (CSV)"]}>
          <CompanyLoader enabled={gold && !!user && !DEMO} onLoad={onCompany} loaded={loaded} initial={sp.get("load") === "1" && form.symbol ? form.symbol.toUpperCase() : null} />

          <section className="card dcf-form" aria-labelledby="dcf-in-h">
            <h2 id="dcf-in-h">Inputs <span className="faint">₹ crore unless stated</span></h2>
            <div className="dcf-grid">
              <Field id="fcf0" label="Initial FCF (₹ Cr)" help={HELP.fcf0} value={form.fcf0} onChange={set("fcf0")} error={err("fcf0")} />
              <Field id="r" label="Discount rate" help={HELP.r} value={form.r} onChange={set("r")} unit="%" error={err("r")} />
              <GrowthField id="g1" label="Growth rate (1 to 5 years)" help={HELP.g1} preset={form.g1Preset} value={form.g1} onPreset={preset("g1")} onValue={set("g1")} error={err("g1")} />
              <GrowthField id="g2" label="Growth rate (6 to 10 years)" help={HELP.g2} preset={form.g2Preset} value={form.g2} onPreset={preset("g2")} onValue={set("g2")} error={err("g2")} />
              {form.tvMethod === "gordon"
                ? <Field id="gT" label="Terminal growth rate" help={HELP.gT} value={form.gT} onChange={set("gT")} unit="%" error={err("gT")} hint={`Must be below the discount rate (${form.r || "—"}%).`} />
                : <Field id="exitMultiple" label="Exit multiple (× year-10 FCF)" help={HELP.exitMultiple} value={form.exitMultiple} onChange={set("exitMultiple")} unit="×" error={err("exitMultiple")} />}
              <Field id="marketCap" label="Market capitalisation (₹ Cr)" help={HELP.marketCap} value={form.marketCap} onChange={set("marketCap")} error={err("marketCap")} />
              <Field id="price" label="Current share price (₹)" help={HELP.price} value={form.price} onChange={set("price")} error={err("price")} />
              <Field id="netDebt" label="Net debt (₹ Cr)" help={HELP.netDebt} value={form.netDebt} onChange={set("netDebt")} error={err("netDebt")} hint="Negative for net cash." />
              <div className="dcf-f">
                <Field id="mos" label="Margin of safety" help={HELP.mos} value={form.mos} onChange={set("mos")} unit="%" error={err("mos")} />
                <div className="dcf-chips" role="group" aria-label="Margin of safety by uncertainty">{MOS_PRESETS.map((m) => <button type="button" key={m.value} className={"chip-b" + (form.mos === String(m.value) ? " on" : "")} aria-pressed={form.mos === String(m.value)} onClick={() => set("mos")(String(m.value))}>{m.label} {m.value}%</button>)}</div>
              </div>
              <Field id="shares" label="Shares outstanding (crore)" help={HELP.shares} value={form.shares} onChange={set("shares")} error={err("shares")} required={false}
                hint={form.shares.trim() ? "Diluted count used instead of market cap ÷ price." : "Optional: left empty, market capitalisation ÷ price."} />
            </div>
            <div className="dcf-opts">
              <label className="dcf-tog"><input type="checkbox" checked={form.midYear} onChange={(e) => set("midYear")(e.target.checked)} /> Mid-year convention <Info g={HELP.midYear} /></label>
              <label className="dcf-tog">Terminal value:
                <select value={form.tvMethod} onChange={(e) => set("tvMethod")(e.target.value as Form["tvMethod"])}><option value="gordon">Growth formula (Gordon)</option><option value="exit">Exit multiple</option></select></label>
              <button className="btn sm ghost" type="button" onClick={() => { setForm(DEFAULT); setLoaded(null); }}>Reset</button>
            </div>
            <RateBuilder onUse={(r) => set("r")(String(r))} />
          </section>

          {out.errors.length > 0 && (
            <section className="card dcf-errors" role="alert" aria-labelledby="dcf-err-h"><h2 id="dcf-err-h">Fix these to see the value</h2>
              <ul>{out.errors.map((e: Issue) => <li key={e.field + e.text}>{e.text}</li>)}</ul></section>)}

          {res && (<>
            <section className="dcf-sum" aria-label="Result" aria-live="polite">
              <div className={"dcf-k main st-" + res.status}><span>Intrinsic value per share</span><b>{res.equity > 0 ? rs(res.iv) : "N/M"}</b><small>{form.symbol ? form.symbol + " · " : ""}on these assumptions</small></div>
              <div className="dcf-k"><span>Current price</span><b>{rs(inputs.price)}</b><small>{loaded?.priceAsOf && form.symbol === loaded.symbol ? dateIN(loaded.priceAsOf.slice(0, 10)) : "as entered"}</small></div>
              <div className="dcf-k"><span>Upside / downside</span><b className={res.upside >= 0 ? "up" : "down"}>{res.equity > 0 ? sgn(res.upside) : "—"}</b><small>intrinsic value vs price</small></div>
              <div className="dcf-k"><span>Buy price ({nf(inputs.mos, 0)}% margin)</span><b>{res.equity > 0 ? rs(res.buyPrice) : "—"}</b><small>intrinsic value × (1 − margin)</small></div>
              <div className={"dcf-status st-" + res.status}><b>{STATUS_TEXT[res.status].label}</b><span>{STATUS_TEXT[res.status].text}</span></div>
            </section>

            {out.warnings.length > 0 && <section className="dcf-warn" aria-label="Checks on these assumptions"><h3><Icon name="info" /> Worth a second look</h3><ul>{out.warnings.map((w) => <li key={w.text}>{w.text}</li>)}</ul></section>}

            <section className="card"><h2>How the value is built</h2>
              <div className="dcf-kv">
                <span>Enterprise value <b>{crs(res.ev)}</b></span><span>Equity value <b>{crs(res.equity)}</b></span><span>Shares <b>{nf(res.shares, 2)} Cr</b></span>
                <span>Terminal value share <b>{pc(res.tvShare, 1)}</b></span><span>Implied exit multiple <b>{nf(res.exitMultiple, 1)}× FCF</b></span>
                {inputs.tvMethod === "exit" && <span>Implied perpetual growth <b>{pc(res.impliedGT)}</b></span>}<span>FCF yield at today's EV <b>{pc(res.impliedFcfYield)}</b></span>
              </div>
              <Steps i={inputs} res={res} />
              <div className="dcf-two"><Bridge res={res} i={inputs} /><PvChart res={res} /></div>
            </section>

            <section className="card"><h2>Year by year</h2><YearTable res={res} i={inputs} /></section>

            <section className="card"><h2>What the price implies (reverse DCF)</h2>
              <div className="dcf-kv">
                <span>Growth needed in years 1–5 for {rs(inputs.price)} <b>{ig == null ? "outside −50% to 150%" : pc(ig)}</b></span>
                <span>Return the price offers on these cash flows <b>{ir == null ? "—" : pc(ir)}</b></span>
                {loaded?.fcf.cagr5 != null && form.symbol === loaded.symbol && <span>Actual FCF growth, last 5 years <b>{pc(loaded.fcf.cagr5)}</b></span>}
              </div>
              <p className="faint">If the growth the price needs is far above what the company has done, the market is optimistic; if the return it offers is below your discount rate, the price is above your value.</p>
            </section>

            <section className="card"><h2>Sensitivity</h2>
              {inputs.tvMethod === "gordon" && <Grid title="Discount rate × terminal growth" i={inputs} rowKey="gT" rows={around(inputs.gT, 0.5)} rowLabel="Terminal growth" colKey="r" cols={around(inputs.r, 1)} colLabel="Discount rate"
                note="Each cell is the intrinsic value per share. Green: price at or below the buy price; amber: between buy price and value; red: price above value; — where terminal growth is not below the discount rate." />}
              <Grid title="Discount rate × growth (years 1–5)" i={inputs} rowKey="g1" rows={around(inputs.g1, 2.5)} rowLabel="Growth 1–5" colKey="r" cols={around(inputs.r, 1)} colLabel="Discount rate"
                note="The centre cell is your base case." />
            </section>

            <section className="card"><h2>Bear, base and bull</h2><Scenarios i={inputs} /></section>

            <section className="card"><h2>Save, share and export</h2>
              <div className="dcf-acts"><button className="btn" type="button" onClick={copyLink}><Icon name="arrow" /> Copy share link</button>
                <button className="btn" type="button" onClick={() => exportCsv(inputs, res, form.symbol)}>Download CSV (Excel)</button>
                <button className="btn" type="button" onClick={() => window.print()}>Print / PDF</button></div>
              <SavedScenarios enabled={gold && !!user} form={form} onOpen={(f) => { setForm(f); setLoaded(null); }} />
            </section>
          </>)}
        </Gate>
        <p className="faint dcf-disc">A DCF value is only as good as its assumptions: small changes in growth or discount rate move it a lot. This is a calculation tool for education, not investment advice. <Link to="/glossary#discounted-cash-flow-dcf">What is a DCF?</Link></p>
      </div>
    </>
  );
}
