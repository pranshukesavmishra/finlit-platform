import { useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Icon } from "../lib/icons";
import { Gate, TierChip } from "../components/Gate";
import { Info } from "../components/Info";
import { Plain } from "../components/Plain";
import { Spark } from "../charts/Small";
import { LineChart } from "../charts/LineChart";
import { cr, fmtUnit, initials, nf, pct } from "../lib/format";
import { prefetchStock, type Peers, type Ratios, type Segments, type Summary } from "../lib/api";
import { buckets, metric } from "./derive";
import { useUI } from "../lib/ui";
import { SectionHead } from "./Sections";
import { SegmentCard } from "./Sections2";

const v = (n: string) => `var(${n})`;

/* ================= Ratios ================= */
const TREND_KEYS: [string, string, string][] = [["gross_margin", "Gross margin", "--p-growth"], ["operating_margin", "Operating margin", "--p-profit"], ["net_margin", "Net margin", "--p-tech"], ["roe", "Return on equity", "--p-quality"], ["roce", "Return on capital", "--p-balance"]];
const GROUP_COLOR: Record<string, string> = { valuation: "--p-quality", returns: "--p-quality", margins: "--p-profit", growth: "--p-growth", leverage: "--p-balance", liquidity: "--p-balance", efficiency: "--p-profit", shareholder: "--gold-deep", quality: "--p-quality" };
const GROUP_ICON: Record<string, string> = { valuation: "tag", returns: "quality", margins: "profit", growth: "growth", leverage: "balance", liquidity: "balance", efficiency: "activity", shareholder: "coins", quality: "quality" };
const GOLD_GROUPS = new Set(["leverage", "liquidity", "efficiency", "quality", "shareholder"]);
const DUPES: Record<string, string> = { sales_cagr: "revenue_cagr_5y", profit_cagr: "profit_cagr_5y", npm: "net_margin", opm: "operating_margin" };

/** Rule-of-thumb zones for the headline ratios. They are a starting point, not a verdict: compare within the same industry. */
const METERS: { key: string; max: number; cuts: [number, number]; words: [string, string, string]; good: "low" | "high" | "none"; say: (x: number) => string }[] = [
  { key: "pe", max: 60, cuts: [15, 30], words: ["Low", "Moderate", "High"], good: "low", say: (x) => `You pay ₹${nf(x, 1)} for every ₹1 the company earns in a year.` },
  { key: "pb", max: 8, cuts: [1.5, 4], words: ["Low", "Moderate", "High"], good: "low", say: (x) => `The price is ${nf(x, 1)} times what the company's books say it owns.` },
  { key: "roe", max: 30, cuts: [10, 15], words: ["Low", "Decent", "Strong"], good: "high", say: (x) => `It earns ₹${nf(x, 1)} a year for every ₹100 of shareholders' money.` },
  { key: "roce", max: 30, cuts: [10, 15], words: ["Low", "Decent", "Strong"], good: "high", say: (x) => `It earns ₹${nf(x, 1)} a year for every ₹100 of all capital used.` },
  { key: "debt_to_equity", max: 3, cuts: [0.5, 1.5], words: ["Low", "Moderate", "High"], good: "low", say: (x) => `It owes ₹${nf(x, 2)} for every ₹1 of owners' money.` },
  { key: "dividend_yield", max: 6, cuts: [1, 3], words: ["Low", "Moderate", "High"], good: "none", say: (x) => `About ₹${nf(x, 2)} a year in dividends for every ₹100 invested.` },
];

function Meter({ m, r, on, onSel }: { m: (typeof METERS)[number]; r: Ratios; on: boolean; onSel: () => void }) {
  const e = r.latest[m.key]; if (!e) return null;
  const x = e.value, zone = x < m.cuts[0] ? 0 : x < m.cuts[1] ? 1 : 2;
  const tone = m.good === "none" ? ["--info", "--info", "--info"][zone] : m.good === "low" ? ["--gain", "--warn", "--loss"][zone] : ["--loss", "--warn", "--gain"][zone];
  const pos = Math.min(100, Math.max(0, (x / m.max) * 100)), a = (m.cuts[0] / m.max) * 100, b = (m.cuts[1] / m.max) * 100;
  const zc = m.good === "none" ? ["--info", "--info", "--info"] : m.good === "low" ? ["--gain", "--warn", "--loss"] : ["--loss", "--warn", "--gain"];
  return (
    <div className={"mtr" + (on ? " on" : "")} tabIndex={0} onMouseEnter={onSel} onFocus={onSel} style={{ "--mc": v(tone) } as React.CSSProperties}>
      <div className="mtr-h"><span className="label">{e.label} <Info g={r.glossary[m.key]} /></span><span className="mtr-pill">{m.words[zone]}</span></div>
      <div className="mtr-v">{fmtUnit(x, e.unit)}<em>{e.period === "latest" ? "" : e.period}</em></div>
      <div className="mtr-bar" role="img" aria-label={`${e.label} ${fmtUnit(x, e.unit)}, ${m.words[zone]}`}>
        <span style={{ left: 0, width: `${a}%`, background: v(zc[0]) }} /><span style={{ left: `${a}%`, width: `${b - a}%`, background: v(zc[1]) }} /><span style={{ left: `${b}%`, width: `${100 - b}%`, background: v(zc[2]) }} />
        <i style={{ left: `${pos}%` }} />
      </div>
    </div>
  );
}

function TrendCard({ k, label, col, vals, better }: { k: string; label: string; col: string; vals: (number | null)[]; better?: string | null }) {
  const nn = vals.filter((x): x is number => x != null);
  if (nn.length < 2) return null;
  const now = nn[nn.length - 1], prev = nn[nn.length - 2], d = now - prev, hi = Math.max(...nn), lo = Math.min(...nn), avg = nn.reduce((a, b) => a + b, 0) / nn.length;
  const up = d >= 0, goodDir = better === "lower" ? !up : up;
  return (
    <div className="trc" key={k} style={{ "--tc": v(col) } as React.CSSProperties}>
      <div className="trc-h"><span>{label}</span><span className={"chip " + (goodDir ? "up" : "down")}>{up ? "▲ +" : "▼ −"}{nf(Math.abs(d), 1)} pts</span></div>
      <div className="trc-v">{pct(now, 1)}</div>
      <Spark values={vals} color={v(col)} w={220} h={70} />
      <div className="trc-f"><span>Low <b>{nf(lo, 1)}%</b></span><span>Avg <b>{nf(avg, 1)}%</b></span><span>High <b>{nf(hi, 1)}%</b></span></div>
    </div>
  );
}

function HistoryTable({ r }: { r: Ratios }) {
  const hist = r.history;
  const rows = Object.entries(hist.rows).filter(([k]) => r.glossary[k]?.label);
  return (
    <div className="tw"><table className="htab">
      <thead><tr><th>Ratio</th>{hist.periods.map((p, i) => <th key={p} className={i === hist.periods.length - 1 ? "latest" : ""}>{p}</th>)}<th>Change</th><th>Trend</th></tr></thead>
      <tbody>{rows.map(([k, vals]) => {
        const nn = vals.filter((x): x is number => x != null), lo = Math.min(...nn), hi = Math.max(...nn), better = r.glossary[k].better || r.latest[k]?.better;
        const last = nn[nn.length - 1], prev = nn[nn.length - 2], ch = prev ? ((last - prev) / Math.abs(prev)) * 100 : null;
        const up = (ch ?? 0) >= 0, good = better === "lower" ? !up : better === "higher" ? up : null;
        const sc = good == null ? "var(--c2)" : good ? "var(--gain)" : "var(--loss)";
        return (
          <tr key={k}><td>{r.glossary[k].label}</td>
            {vals.map((x, i) => {
              let t = x == null || hi === lo ? 0.5 : (x - lo) / (hi - lo); if (better === "lower") t = 1 - t;
              const bg = x == null ? "transparent" : t >= 0.5 ? `color-mix(in srgb, var(--gain) ${Math.round((t - 0.5) * 44)}%, transparent)` : `color-mix(in srgb, var(--loss) ${Math.round((0.5 - t) * 44)}%, transparent)`;
              return <td key={i} className={i === vals.length - 1 ? "latest" : ""} style={{ background: good == null ? undefined : bg }}>{x == null ? <span className="faint">—</span> : nf(x)}</td>;
            })}
            <td>{ch == null ? "—" : <span className={"dchip " + (good == null ? "" : good ? "up" : "down")}>{up ? "▲" : "▼"} {nf(Math.abs(ch), 1)}%</span>}</td>
            <td><Spark values={vals} color={sc} w={84} h={30} /></td></tr>
        );
      })}</tbody>
    </table><p className="faint" style={{ fontSize: 12, margin: "10px 0 0" }}>Green cells are the best years for that ratio, red the weakest. Where "better" depends on the business, cells stay uncoloured.</p></div>
  );
}

function ValuationHistory({ r }: { r: Ratios }) {
  const [k, setK] = useState<"pe" | "pb" | "ps">("pe");
  const vh = r.valuationHistory, vals = vh.rows[k] || [], nn = vals.filter((x): x is number => x != null);
  if (!nn.length) return null;
  const mean = nn.reduce((a, b) => a + b, 0) / nn.length, now = nn[nn.length - 1], diff = ((now - mean) / mean) * 100;
  const name = { pe: "P/E", pb: "P/B", ps: "P/S" }[k];
  return (
    <div className="vh">
      <div className="tools"><div><div className="label">Valuation history</div><p className="faint" style={{ margin: "4px 0 0", fontSize: 12.5 }}>How much investors paid over the years</p></div><div className="seg">{(["pe", "pb", "ps"] as const).map((x) => <button key={x} aria-pressed={k === x} onClick={() => setK(x)}>{x === "pe" ? "P/E" : x === "pb" ? "P/B" : "P/S"}</button>)}</div></div>
      <div className="vh-top">
        <div className="vh-k"><span className="label">{name} in {vh.periods[vh.periods.length - 1]}</span><b>{nf(now, 1)}×</b></div>
        <div className="vh-k"><span className="label">{vh.periods.length}-year average</span><b>{nf(mean, 1)}×</b></div>
        <div className={"vh-k " + (diff > 10 ? "hi" : diff < -10 ? "lo" : "")}><span className="label">Versus its history</span><b>{diff >= 0 ? "▲ " : "▼ "}{nf(Math.abs(diff), 0)}% {diff >= 0 ? "above" : "below"}</b></div>
      </div>
      <LineChart periods={vh.periods} series={[{ key: k, label: name, color: "var(--c4)", values: vals }]} fmt={(x) => nf(x, 1) + "×"} area avg={mean} height={250} />
      <Plain tone={diff > 10 ? "warn" : diff < -10 ? "good" : "info"}>{diff > 10 ? `Investors are paying more than usual for each rupee of ${k === "pe" ? "profit" : k === "pb" ? "book value" : "sales"} — about ${nf(Math.abs(diff), 0)}% above this company's own average.` : diff < -10 ? `Investors are paying less than usual — about ${nf(Math.abs(diff), 0)}% below this company's own average.` : "The price is close to what investors have usually paid for this company."}</Plain>
    </div>
  );
}

export function RatiosSection({ r }: { r?: Ratios }) {
  const { has, setPlan } = useUI();
  const [sel, setSel] = useState("pe");
  if (!r) return <section className="block"><SectionHead id="ratios" no="04 · Ratios" icon="gauge" tier="basic" title="Valuation, quality and safety" color="--p-profit" /><div className="skeleton" style={{ height: 300 }} /></section>;
  const hist = r.history, meters = METERS.filter((m) => r.latest[m.key]);
  const cur = meters.find((m) => m.key === sel) || meters[0];
  return (
    <section className="block" style={{ "--sc": "var(--p-profit)" } as React.CSSProperties}>
      <SectionHead id="ratios" no="04 · Ratios" icon="gauge" tier="basic" title="Valuation, quality and safety" sub="Latest value with its period. Select i for what it means and how to read it." color="--p-profit" />
      <Plain>Ratios turn big numbers into fair comparisons. The meters below show where each one sits against common rules of thumb. Zones are a starting point: always compare with companies in the same industry.</Plain>
      <div className="mtr-grid">{meters.map((m) => <Meter key={m.key} m={m} r={r} on={cur?.key === m.key} onSel={() => setSel(m.key)} />)}</div>
      {cur && <p className="mtr-say" aria-live="polite"><b>{r.latest[cur.key].label}</b> {cur.say(r.latest[cur.key].value)}</p>}
      <Gate tier="bronze" title="Historical trend for each parameter" points={["Eight years of margins and returns", "Spot improvement or deterioration", "Median and low for every series"]}>
        <div style={{ margin: "24px 0 16px" }}>
          <div className="label" style={{ marginBottom: 12, display: "flex", gap: 8, alignItems: "center" }}>Historical trend · {hist.periods[0]}–{hist.periods[hist.periods.length - 1]} <TierChip tier="bronze" /></div>
          <div className="trc-grid">{TREND_KEYS.filter(([k]) => hist.rows[k]).map(([k, label, col]) => <TrendCard key={k} k={k} label={label} col={col} vals={hist.rows[k]} better="higher" />)}</div>
        </div>
      </Gate>
      <div className="grid g3">
        {r.groups.filter((g) => g.keys.length).map((g) => {
          const keys = g.keys.filter((k) => !(DUPES[k] && r.latest[DUPES[k]]));
          const gold = GOLD_GROUPS.has(g.id) && !has("gold");
          const rows = gold ? keys.slice(0, 2) : keys;
          return (
            <div className="card acc hover-lift rg" key={g.id} style={{ "--ac": v(GROUP_COLOR[g.id] || "--gold") } as React.CSSProperties}>
              <div className="card-h"><h3><span className="ci"><Icon name={GROUP_ICON[g.id] || "info"} /></span>{g.label}</h3><span className="chip ghost">{rows.length} ratios</span></div>
              {rows.map((k) => {
                const e = r.latest[k], gl = r.glossary[k];
                return (
                  <div className="mrow" key={k}><span className="k"><i className={"bt " + (e.better || "")} title={e.better ? `${e.better === "higher" ? "Higher" : "Lower"} is usually better` : ""}>{e.better === "higher" ? "▲" : e.better === "lower" ? "▼" : "•"}</i>{e.label} <Info g={gl} /></span><span className="v">{fmtUnit(e.value, e.unit)}<span className="unit" style={{ marginLeft: 6, fontSize: 11 }}>{e.period === "latest" ? "" : e.period}</span></span></div>
                );
              })}
              {gold && keys.length > 2 && <div className="more-gold" role="button" tabIndex={0} onClick={() => setPlan("gold")} onKeyDown={(e) => e.key === "Enter" && setPlan("gold")}><Icon name="crown" /><span><b>+{keys.length - 2} more ratios</b> in detailed ratio analysis · Gold</span></div>}
            </div>
          );
        })}
      </div>
      <p className="faint" style={{ fontSize: 12, margin: "10px 2px 0" }}>▲ higher is usually better · ▼ lower is usually better</p>
      <Gate tier="gold" title="Detailed ratio analysis" points={["Every ratio with its history", "Quality, growth, solvency and efficiency", "Full multi-year table"]}>
        <div className="card acc" style={{ marginTop: 16, "--ac": "var(--p-profit)" } as React.CSSProperties}>
          <div className="card-h"><h3><span className="ci"><Icon name="table" /></span>Ratio history</h3><TierChip tier="gold" /></div>
          <HistoryTable r={r} />
          <ValuationHistory r={r} />
        </div>
      </Gate>
    </section>
  );
}

/* ================= Peers ================= */
const HUES = ["#C1B7A1", "#D4B26A", "#E5E2D9", "#E8D29B", "#BAB5A8", "#B8934A", "#AFA48B", "#D7D1C4"];
const hue = (s: string) => HUES[[...s].reduce((a, c) => (a * 31 + c.charCodeAt(0)) | 0, 7) >>> 0 % HUES.length] || HUES[0];

export function PeersSection({ p, self, s }: { p?: Peers; self: string; s: Summary }) {
  const nav = useNavigate(); const qc = useQueryClient();
  const [hv, setHv] = useState<string | null>(null);
  const items = (p?.items || p?.symbols.map((x) => ({ symbol: x, name: null })) || []) as NonNullable<Peers["items"]>;
  const peers = items.filter((i) => i.symbol !== self);
  if (!p || !peers.length) return null;
  const me = { score: s.score.overall, mcap: s.profile.marketCapCr, pe: metric(s, "pe")?.value ?? null, roe: metric(s, "roe")?.value ?? null };
  const hasData = peers.some((i) => i.overall != null || i.market_cap != null || i.pe != null);
  const maxCap = Math.max(me.mcap || 0, ...peers.map((i) => i.market_cap || 0), 1);
  const rad = (cap: number | null | undefined) => (cap ? 20 + 18 * Math.sqrt(cap / maxCap) : 26);
  const go = (sym: string) => nav(`/stocks/${sym}`);
  const hov = hv ? peers.find((i) => i.symbol === hv) : null;
  const N = peers.length, CX = 190, CY = 190, RR = 128;
  return (
    <section className="block" style={{ "--sc": "var(--gold-deep)" } as React.CSSProperties}>
      <SectionHead id="peers" no="06 · Peers" icon="layers" tier="basic" title="Companies in the same space" sub="Select a company to open its report." color="--gold-deep" />
      <Plain>Comparing a company with its closest rivals is the quickest way to tell whether a number is good or just normal for the industry. {s.profile.sector ? `These ${N} companies work in ${s.profile.sector}.` : ""}</Plain>
      <div className="pr2">
        <div className="card acc orbit-card" style={{ "--ac": "var(--gold)" } as React.CSSProperties}>
          <svg viewBox="0 0 380 380" role="group" aria-label="Map of companies in the same industry">
            <defs><radialGradient id="orb" cx=".5" cy=".5" r=".5"><stop offset="0" stopColor="var(--gold)" stopOpacity=".22" /><stop offset="1" stopColor="var(--gold)" stopOpacity="0" /></radialGradient>
              <linearGradient id="orbg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stopColor="var(--gold-2)" /><stop offset="1" stopColor="var(--gold-deep)" /></linearGradient></defs>
            <circle cx={CX} cy={CY} r="178" fill="url(#orb)" />
            <circle cx={CX} cy={CY} r={RR} fill="none" stroke="var(--border-strong)" strokeDasharray="2 7" /><circle cx={CX} cy={CY} r={RR * 0.62} fill="none" stroke="var(--border)" strokeDasharray="2 9" />
            {peers.map((i, k) => { const a = (k / N) * Math.PI * 2 - Math.PI / 2, x = CX + RR * Math.cos(a), y = CY + RR * Math.sin(a), c = hue(i.symbol), r = rad(i.market_cap), on = hv === i.symbol;
              return (
                <g key={i.symbol}>
                  <line x1={CX} y1={CY} x2={x} y2={y} stroke={c} strokeWidth={on ? 2.4 : 1.2} strokeOpacity={on ? 0.9 : 0.35} strokeDasharray={on ? "" : "4 5"} />
                  <g className="orb-n" tabIndex={0} role="link" aria-label={`Open ${i.name || i.symbol}`} transform={`translate(${x} ${y})`} onMouseEnter={() => { setHv(i.symbol); prefetchStock(qc, i.symbol); }} onMouseLeave={() => setHv(null)} onFocus={() => setHv(i.symbol)} onBlur={() => setHv(null)} onClick={() => go(i.symbol)} onKeyDown={(e) => e.key === "Enter" && go(i.symbol)} style={{ cursor: "pointer" }}>
                    <circle r={r + 8} fill={c} opacity={on ? 0.28 : 0.12} /><circle r={r} fill={`color-mix(in srgb, ${c} 30%, var(--s1))`} stroke={c} strokeWidth={on ? 3 : 2} />
                    <text textAnchor="middle" dy=".35em" fontSize={r > 28 ? 11 : 9.5} fontWeight="700" fontFamily="IBM Plex Mono, monospace" fill="var(--text)">{i.symbol.length > 7 ? i.symbol.slice(0, 6) + "…" : i.symbol}</text>
                  </g>
                </g>
              ); })}
            <g transform={`translate(${CX} ${CY})`}><circle r="58" fill="var(--gold)" opacity=".16" /><circle r="46" fill="url(#orbg)" /><text textAnchor="middle" dy="-.15em" fontSize="12" fontWeight="700" fill="#2a1c00" fontFamily="IBM Plex Mono, monospace">{self}</text><text textAnchor="middle" dy="1.5em" fontSize="9.5" fill="#2a1c00" opacity=".75">THIS COMPANY</text></g>
          </svg>
          <p className="orb-cap">{hov ? <><b>{hov.name || hov.symbol}</b> · click to open its report</> : hasData ? "Bubble size shows market value. Hover or click a company." : "Hover or click a company to open its report."}</p>
        </div>
        <div className="pr-list">
          <div className="pr-row me"><span className="av" style={{ background: "linear-gradient(140deg,var(--gold-2),var(--gold-deep))", color: "#2a1c00" }}>{initials(s.profile.name)}</span><span className="pr-nm"><b>{s.profile.name}</b><span className="tk">{self} · this company</span></span>
            <span className="pr-st"><span>Score</span><b>{me.score ?? "—"}</b></span><span className="pr-st"><span>P/E</span><b>{me.pe != null ? nf(me.pe, 1) + "×" : "—"}</b></span><span className="pr-st"><span>ROE</span><b>{me.roe != null ? nf(me.roe, 1) + "%" : "—"}</b></span><span className="pr-st"><span>Cap</span><b>{me.mcap ? "₹" + cr(me.mcap) : "—"}</b></span></div>
          {peers.map((i) => { const c = hue(i.symbol); return (
            <a key={i.symbol} className={"pr-row" + (hv === i.symbol ? " hot" : "")} href={`/stocks/${i.symbol}`} style={{ "--pc": c } as React.CSSProperties} onMouseEnter={() => { setHv(i.symbol); prefetchStock(qc, i.symbol); }} onMouseLeave={() => setHv(null)} onClick={(e) => { e.preventDefault(); go(i.symbol); }}>
              <span className="av" style={{ background: `linear-gradient(140deg, ${c}, color-mix(in srgb, ${c} 55%, #000))` }}>{initials(i.name || i.symbol)}</span>
              <span className="pr-nm"><b>{i.name || i.symbol}</b><span className="tk">{i.symbol}</span></span>
              {hasData ? <><span className="pr-st"><span>Score</span><b>{i.overall ?? "—"}</b></span><span className="pr-st"><span>P/E</span><b>{i.pe != null ? nf(i.pe, 1) + "×" : "—"}</b></span><span className="pr-st"><span>ROE</span><b>{i.roe != null ? nf(i.roe, 1) + "%" : "—"}</b></span><span className="pr-st"><span>Cap</span><b>{i.market_cap ? "₹" + cr(i.market_cap) : "—"}</b></span></> : <span className="pr-go">Open report <Icon name="arrow" /></span>}
            </a>); })}
        </div>
      </div>
    </section>
  );
}

/* ================= Gold insights ================= */
const SPEC: Record<string, { stops: string[]; at: (val: string) => number; say: (val: string) => string }> = {
  Size: { stops: ["Micro", "Small", "Mid", "Large"], at: (x) => (/Large/.test(x) ? 3.5 : /Mid/.test(x) ? 2.5 : /Small/.test(x) ? 1.5 : 0.5), say: (x) => (/Large/.test(x) ? "A big, established company" : /Mid/.test(x) ? "A mid-sized company with room to grow" : "A smaller company; can move faster, with more risk") },
  Style: { stops: ["Value", "Blend", "Growth"], at: (x) => (/Premium/.test(x) ? 2.5 : /Value/.test(x) ? 0.5 : 1.5), say: (x) => (/Premium/.test(x) ? "The market pays a high price for its growth" : /Value/.test(x) ? "Priced low against what it earns" : "Neither cheap nor expensive") },
  Income: { stops: ["Low", "Moderate", "High"], at: (x) => (/High/.test(x) ? 2.5 : /Moderate/.test(x) ? 1.5 : 0.5), say: (x) => (/High/.test(x) ? "Pays out a large share as dividends" : /Moderate/.test(x) ? "Pays a steady dividend" : "Pays little; keeps cash for growth") },
  Momentum: { stops: ["Oversold", "Neutral", "Overbought"], at: (x) => (/Oversold/.test(x) ? 0.5 : /Overbought/.test(x) ? 2.5 : 1.5), say: (x) => (/Oversold/.test(x) ? "Sold off heavily lately" : /Overbought/.test(x) ? "Bought heavily lately" : "No extreme in recent price moves") },
};
const WHY: Record<string, [string, string]> = {
  roe: ["A low return means each rupee of shareholders' money earns little.", "Watch whether ROE climbs above 15% in coming results."],
  profit_cagr: ["Profit growing slower than sales means costs are eating into margins.", "Watch the profit margin in the next two quarters."],
  current_ratio: ["Short-term bills slightly exceed short-term assets, so cash management matters.", "Watch operating cash flow and short-term borrowings."],
  rsi14: ["Heavy selling can mean fear, or a chance if the business is sound.", "Watch for the price to stop falling before drawing conclusions."],
  vsEma200Pct: ["Trading below its long-term average signals a weak longer trend.", "Watch whether the price reclaims its 200-day average."],
  cfo_to_pat: ["Profit is turning into real cash, which makes earnings more trustworthy.", "Watch that cash flow stays above reported profit."],
  debt_to_equity: ["Low borrowing leaves room to handle a bad year or fund growth.", "Watch if debt rises faster than profit."],
  sales_cagr: ["Steady sales growth shows demand for what the company sells.", "Watch whether growth holds as the base gets bigger."],
};

export function InsightsSection({ s, r, seg, tech }: { s: Summary; r?: Ratios; seg?: Segments; tech?: { rsi14: number | null } }) {
  const b = useMemo(() => buckets(s, r, tech), [s, r, tech]);
  const trig = [...s.watchouts.slice(0, 3).map((n) => ({ ...n, kind: "watch" as const })), ...s.strengths.slice(0, 3).map((n) => ({ ...n, kind: "good" as const }))];
  const spec = b.filter(([, k]) => SPEC[k]), plain = b.filter(([, k]) => !SPEC[k]);
  return (
    <section className="block" style={{ "--sc": "var(--t-gold)" } as React.CSSProperties}>
      <SectionHead id="insights" no="07 · Gold insights" icon="crown" tier="gold" title="Buckets, triggers and segments" sub="Where this company sits in FinLit's stock buckets, and what to watch next." color="--t-gold" />
      <Plain>Buckets tell you what kind of company this is, and where it sits on each scale. Triggers are the specific things most worth watching next. Segments show where the money comes from.</Plain>
      <Gate tier="gold" title="Unlock Gold insights" points={["Stock bucketing by size, style and theme", "Key triggers and sector benchmarking", "Revenue segmentation by segment"]}>
        <div className="spc-grid">{spec.map(([ic, k, val, c], i) => {
          const sp = SPEC[k], pos = ((sp.at(val)) / sp.stops.length) * 100;
          return (
            <div className="spc" key={k} style={{ "--bc": v(c), animationDelay: `${i * 80}ms` } as React.CSSProperties}>
              <div className="spc-h"><span className="bk-i"><Icon name={ic} /></span><div><span className="label">{k}</span><b>{val}</b></div></div>
              <div className="spc-bar"><span>{sp.stops.map((t) => <em key={t}>{t}</em>)}</span><div className="spc-t"><i style={{ left: `${pos}%` }} /></div></div>
              <p>{sp.say(val)}</p>
            </div>
          );
        })}
          {plain.length > 0 && <div className="spc tags"><span className="label">Where it fits</span><div>{plain.map(([ic, k, val, c]) => <span className="tagc" key={k} style={{ "--bc": v(c) } as React.CSSProperties}><Icon name={ic} /><small>{k}</small><b>{val}</b></span>)}</div></div>}
        </div>
        <div className="card acc" style={{ "--ac": "var(--t-gold)", marginTop: 16 } as React.CSSProperties}>
          <div className="card-h"><h3><span className="ci"><Icon name="alert" /></span>Key triggers to watch</h3><span className="s">{s.watchouts.length} worries · {s.strengths.length} strengths</span></div>
          <div className="trg-bal"><span style={{ flex: s.watchouts.length || 0.2, background: "var(--warn)" }} /><span style={{ flex: s.strengths.length || 0.2, background: "var(--gain)" }} /></div>
          <div className="trg-cols">
            {([["watch", "Worries", "alert"], ["good", "Strengths", "check"]] as const).map(([kind, title]) => (
              <div key={kind}><div className={"trg-colh " + kind}>{title}<span>{trig.filter((n) => n.kind === kind).length}</span></div>
                <ul className="trg2">{trig.filter((n) => n.kind === kind).map((n) => { const w = WHY[n.key]; return (
                  <li key={n.key} className={n.kind}><div className="trg2-h"><span className="trg-i"><Icon name={n.kind === "watch" ? "alert" : "check"} /></span><b>{n.title}</b></div><p>{n.text}</p>
                    {w && <div className="trg2-w"><span><small>Why it matters</small>{w[0]}</span><span><small>What to watch</small>{w[1]}</span></div>}</li>
                ); })}{!trig.some((n) => n.kind === kind) && <li className={kind}><p>Nothing stands out.</p></li>}</ul></div>
            ))}
          </div>
        </div>
        <div style={{ marginTop: 16 }}><SegmentCard seg={seg} /></div>
      </Gate>
    </section>
  );
}
