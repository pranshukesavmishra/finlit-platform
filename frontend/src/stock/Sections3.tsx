import { useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { Icon } from "../lib/icons";
import { Gate, TierChip } from "../components/Gate";
import { Info } from "../components/Info";
import { Plain } from "../components/Plain";
import { Spark } from "../charts/Small";
import { LineChart } from "../charts/LineChart";
import { capSize, cr, fmtUnit, initials, nf, pct } from "../lib/format";
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
  { key: "debt_to_equity", max: 3, cuts: [0.5, 1.5], words: ["Low debt", "Moderate", "High debt"], good: "low", say: (x) => `It owes ₹${nf(x, 2)} for every ₹1 of owners' money.` },
  { key: "dividend_yield", max: 6, cuts: [1, 3], words: ["Low", "Moderate", "High"], good: "none", say: (x) => `About ₹${nf(x, 2)} a year in dividends for every ₹100 invested.` },
];

function Meter({ m, r }: { m: (typeof METERS)[number]; r: Ratios }) {
  const e = r.latest[m.key]; if (!e) return null;
  const x = e.value, zone = x < m.cuts[0] ? 0 : x < m.cuts[1] ? 1 : 2;
  const tone = m.good === "none" ? ["--info", "--info", "--info"][zone] : m.good === "low" ? ["--gain", "--warn", "--loss"][zone] : ["--loss", "--warn", "--gain"][zone];
  const pos = Math.min(100, Math.max(0, (x / m.max) * 100)), a = (m.cuts[0] / m.max) * 100, b = (m.cuts[1] / m.max) * 100;
  const zc = m.good === "none" ? ["--info", "--info", "--info"] : m.good === "low" ? ["--gain", "--warn", "--loss"] : ["--loss", "--warn", "--gain"];
  return (
    <div className="mtr" style={{ "--mc": v(tone) } as React.CSSProperties}>
      <div className="mtr-h"><span className="label">{e.label} <Info g={r.glossary[m.key]} /></span><span className="mtr-pill">{m.words[zone]}</span></div>
      <div className="mtr-v">{fmtUnit(x, e.unit)}<em>{e.period === "latest" ? "" : e.period}</em></div>
      <div className="mtr-bar" role="img" aria-label={`${e.label} ${fmtUnit(x, e.unit)}, ${m.words[zone]}`}>
        <span style={{ left: 0, width: `${a}%`, background: v(zc[0]) }} /><span style={{ left: `${a}%`, width: `${b - a}%`, background: v(zc[1]) }} /><span style={{ left: `${b}%`, width: `${100 - b}%`, background: v(zc[2]) }} />
        <i style={{ left: `${pos}%` }} />
      </div>
      <p>{m.say(x)}</p>
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
  if (!r) return <section className="block"><SectionHead id="ratios" no="04 · Ratios" icon="gauge" tier="basic" title="Valuation, quality and safety" color="--p-profit" /><div className="skeleton" style={{ height: 300 }} /></section>;
  const hist = r.history, meters = METERS.filter((m) => r.latest[m.key]);
  return (
    <section className="block" style={{ "--sc": "var(--p-profit)" } as React.CSSProperties}>
      <SectionHead id="ratios" no="04 · Ratios" icon="gauge" tier="basic" title="Valuation, quality and safety" sub="Latest value with its period. Select i for what it means and how to read it." color="--p-profit" />
      <Plain>Ratios turn big numbers into fair comparisons. The meters below show where each one sits against common rules of thumb. Zones are a starting point: always compare with companies in the same industry.</Plain>
      <div className="mtr-grid">{meters.map((m) => <Meter key={m.key} m={m} r={r} />)}</div>
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
const HUES = ["#60A5FA", "#34D399", "#A78BFA", "#F472B6", "#22D3EE", "#F59E0B", "#FB7185", "#818CF8"];
const hue = (s: string) => HUES[[...s].reduce((a, c) => (a * 31 + c.charCodeAt(0)) | 0, 7) >>> 0 % HUES.length] || HUES[0];

export function PeersSection({ p, self, s }: { p?: Peers; self: string; s: Summary }) {
  const nav = useNavigate(); const qc = useQueryClient();
  const items = (p?.items || p?.symbols.map((x) => ({ symbol: x, name: null })) || []) as NonNullable<Peers["items"]>;
  const peers = items.filter((i) => i.symbol !== self);
  if (!p || !peers.length) return null;
  const me = { score: s.score.overall, mcap: s.profile.marketCapCr, pe: metric(s, "pe")?.value ?? null, roe: metric(s, "roe")?.value ?? null };
  const delta = (a: number | null | undefined, b: number | null) => (a == null || b == null || !b ? null : ((a - b) / Math.abs(b)) * 100);
  const hasData = peers.some((i) => i.overall != null || i.market_cap != null || i.pe != null);
  return (
    <section className="block" style={{ "--sc": "var(--gold-deep)" } as React.CSSProperties}>
      <SectionHead id="peers" no="06 · Peers" icon="layers" tier="basic" title="Companies in the same space" sub="Select a company to open its report." color="--gold-deep" />
      <Plain>Comparing a company with its closest rivals is the quickest way to tell whether a number is good or just normal for the industry. {s.profile.sector ? `These ${peers.length} companies work in ${s.profile.sector}.` : ""}</Plain>
      <div className="pr-wrap">
        <div className="pr-me">
          <span className="chip gold">This company</span>
          <div className="pr-id"><span className="av" style={{ background: "linear-gradient(140deg,var(--gold-2),var(--gold-deep))", color: "#2a1c00" }}>{initials(s.profile.name)}</span><div><b>{s.profile.name}</b><span className="tk">{self}</span></div></div>
          <div className="pr-score"><svg viewBox="0 0 80 80" aria-hidden="true"><circle cx="40" cy="40" r="32" fill="none" stroke="var(--s3)" strokeWidth="8" /><circle cx="40" cy="40" r="32" fill="none" stroke="var(--gold)" strokeWidth="8" strokeLinecap="round" strokeDasharray={`${(201 * (me.score ?? 0)) / 100} 201`} transform="rotate(-90 40 40)" /></svg><b>{me.score ?? "—"}</b></div>
          <div className="pr-m"><span>Market cap</span><b>{me.mcap ? "₹" + cr(me.mcap) + " Cr" : "—"}</b></div>
          <div className="pr-m"><span>P/E</span><b>{me.pe != null ? nf(me.pe, 1) + "×" : "—"}</b></div>
          <div className="pr-m"><span>ROE</span><b>{me.roe != null ? nf(me.roe, 1) + "%" : "—"}</b></div>
          <span className="chip ghost">{capSize(me.mcap) || ""}</span>
        </div>
        <div className="pr-grid">{peers.map((i) => {
          const c = hue(i.symbol), dp = delta(i.pe, me.pe), dr = i.roe != null && me.roe != null ? i.roe - me.roe : null;
          return (
            <a key={i.symbol} className="pcard" href={`/stocks/${i.symbol}`} style={{ "--pc": c } as React.CSSProperties} onMouseEnter={() => prefetchStock(qc, i.symbol)} onClick={(e) => { e.preventDefault(); nav(`/stocks/${i.symbol}`); }}>
              <div className="pc-h"><span className="av" style={{ background: `linear-gradient(140deg, ${c}, color-mix(in srgb, ${c} 55%, #000))` }}>{initials(i.name || i.symbol)}</span>
                <span className="pc-n"><b>{i.name || i.symbol}</b><span className="tk">{i.symbol}</span></span></div>
              {hasData ? (
                <div className="pc-m">
                  <div><span>Score</span><b>{i.overall ?? "—"}</b>{i.overall != null && me.score != null && <i className={i.overall >= me.score ? "up" : "down"}>{i.overall >= me.score ? "▲" : "▼"}{Math.abs(i.overall - me.score)}</i>}</div>
                  <div><span>P/E</span><b>{i.pe != null ? nf(i.pe, 1) + "×" : "—"}</b>{dp != null && <i className={dp <= 0 ? "up" : "down"}>{dp <= 0 ? "▼" : "▲"}{nf(Math.abs(dp), 0)}%</i>}</div>
                  <div><span>ROE</span><b>{i.roe != null ? nf(i.roe, 1) + "%" : "—"}</b>{dr != null && <i className={dr >= 0 ? "up" : "down"}>{dr >= 0 ? "▲" : "▼"}{nf(Math.abs(dr), 1)}</i>}</div>
                </div>
              ) : <div className="pc-open">Same industry</div>}
              <span className="pc-go">Open report <Icon name="arrow" /></span>
            </a>
          );
        })}</div>
      </div>
    </section>
  );
}

/* ================= Gold insights ================= */
const BUCKET_SAY: Record<string, (val: string) => string> = {
  Size: (x) => (/Large/.test(x) ? "A big, established company" : /Mid/.test(x) ? "A mid-sized company with room to grow" : "A smaller company; can move faster, with more risk"),
  Style: (x) => (/Premium/.test(x) ? "The market pays a high price for its growth" : /Value/.test(x) ? "Priced low against what it earns" : "Neither cheap nor expensive"),
  Income: (x) => (/High/.test(x) ? "Pays out a large share as dividends" : /Moderate/.test(x) ? "Pays a steady dividend" : "Pays little as dividends; keeps cash for growth"),
  Theme: () => "The industry it works in",
  "Sector group": () => "The wider part of the economy",
  Momentum: (x) => (/Oversold/.test(x) ? "Sold off heavily lately" : /Overbought/.test(x) ? "Bought heavily lately" : "No extreme in recent price moves"),
};

export function InsightsSection({ s, r, seg, tech }: { s: Summary; r?: Ratios; seg?: Segments; tech?: { rsi14: number | null } }) {
  const b = useMemo(() => buckets(s, r, tech), [s, r, tech]);
  const trig = [...s.watchouts.slice(0, 3).map((n) => ({ ...n, kind: "watch" as const })), ...s.strengths.slice(0, 2).map((n) => ({ ...n, kind: "good" as const }))];
  return (
    <section className="block" style={{ "--sc": "var(--t-gold)" } as React.CSSProperties}>
      <SectionHead id="insights" no="07 · Gold insights" icon="crown" tier="gold" title="Buckets, triggers and segments" sub="Where this company sits in FinLit's stock buckets, and what to watch next." color="--t-gold" />
      <Plain>Buckets are quick labels that tell you what kind of company this is. Triggers are the specific things most worth watching next, split into worries and strengths.</Plain>
      <Gate tier="gold" title="Unlock Gold insights" points={["Stock bucketing by size, style and theme", "Key triggers and sector benchmarking", "Revenue segmentation by segment"]}>
        <div className="bk-grid">{b.map(([ic, k, val, c], i) => (
          <div className="bk" key={k} style={{ "--bc": v(c), animationDelay: `${i * 70}ms` } as React.CSSProperties}>
            <span className="bk-i"><Icon name={ic} /></span>
            <span className="label">{k}</span><b>{val}</b><p>{(BUCKET_SAY[k] || (() => ""))(val)}</p>
          </div>))}</div>
        <div className="grid g2" style={{ marginTop: 16 }}>
          <div className="card acc" style={{ "--ac": "var(--t-gold)" } as React.CSSProperties}>
            <div className="card-h"><h3><span className="ci"><Icon name="alert" /></span>Key triggers to watch</h3><span className="s">{s.watchouts.length} worries · {s.strengths.length} strengths</span></div>
            <ul className="trg">{trig.map((n) => (
              <li key={n.key} className={n.kind}><span className="trg-i"><Icon name={n.kind === "watch" ? "alert" : "check"} /></span><div><span className="trg-t">{n.kind === "watch" ? "Watch" : "Strength"}</span><b>{n.title}</b><p>{n.text}</p></div></li>
            ))}</ul>
          </div>
          <SegmentCard seg={seg} />
        </div>
      </Gate>
    </section>
  );
}
