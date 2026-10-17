import { useState } from "react";
import { Icon } from "../lib/icons";
import { MiniBars, type BarSeries } from "../charts/MiniBars";
import { Plain } from "../components/Plain";
import { MINUS, cr, nf, num } from "../lib/format";
import type { Events, Financials, Ratios, Segments, Table } from "../lib/api";
import { SectionHead } from "./Sections";

const crf = (v: number) => (v < 0 ? MINUS : "") + (Math.abs(v) >= 1000 ? cr(Math.abs(v)) : nf(v, Math.abs(v) < 10 && v !== 0 ? 1 : 0));
const pctf = (v: number) => num(v, 1) + "%";
const eps = (v: number) => (v < 0 ? MINUS : "") + "₹" + nf(v, 1);
const row = (t: Table | undefined, k: string) => (t?.rows[k] || []) as (number | null)[];
const chg = (a: number | null | undefined, b: number | null | undefined) => (a == null || b == null || !b ? null : ((a - b) / Math.abs(b)) * 100);
const ratio = (a: (number | null)[], b: (number | null)[]) => a.map((x, i) => (x != null && b[i] ? (x / (b[i] as number)) * 100 : null));
const G = "var(--gold)", INK = "var(--c2)", STONE = "var(--c4)", DEEP = "var(--c1)";

function Delta({ v, label }: { v: number | null; label: string }) {
  if (v == null) return <span className="qd none">{label} —</span>;
  return <span className={"qd " + (v >= 0 ? "up" : "down")}>{v >= 0 ? "▲ +" : "▼ −"}{nf(Math.abs(v), 1)}% <small>{label}</small></span>;
}

/* ============== Latest quarter results ============== */
export function QuarterSection({ f }: { f?: Financials }) {
  const q = f?.quarterly.pl;
  if (!f || !q || q.periods.length < 2) return null;
  const n = q.periods.length, last = n - 1, yoy = n >= 5 ? n - 5 : -1;
  const rev = row(q, "revenue"), op = row(q, "operating_profit"), np = row(q, "net_profit"), ep = row(q, "eps");
  const opm = ratio(op, rev), npm = ratio(np, rev);
  const end = q.periodEnds?.[last] ? new Date(q.periodEnds[last]).toLocaleDateString("en-IN", { day: "numeric", month: "long", year: "numeric" }) : q.periods[last];
  const tiles = [
    { k: "Revenue", v: rev, fmt: (x: number) => (x < 0 ? MINUS : "") + "₹" + cr(Math.abs(x)) + " Cr", bar: crf, ic: "rupee", c: G },
    { k: "Operating profit", v: op, fmt: (x: number) => (x < 0 ? MINUS : "") + "₹" + cr(Math.abs(x)) + " Cr", bar: crf, ic: "growth", c: DEEP, sub: opm[last] != null ? `${nf(opm[last] as number, 1)}% margin` : "" },
    { k: "Net profit", v: np, fmt: (x: number) => (x < 0 ? MINUS : "") + "₹" + cr(Math.abs(x)) + " Cr", bar: crf, ic: "profit", c: INK, sub: npm[last] != null ? `${nf(npm[last] as number, 1)}% margin` : "" },
    { k: "Earnings per share", v: ep, fmt: (x: number) => (x < 0 ? MINUS : "") + "₹" + nf(x, 2), bar: eps, ic: "coins", c: STONE },
  ];
  const npY = chg(np[last], yoy >= 0 ? np[yoy] : null), rvY = chg(rev[last], yoy >= 0 ? rev[yoy] : null);
  const lines: [string, (number | null)[], boolean?][] = [["Revenue", rev], ["Expenses", row(q, "expenses")], ["Operating profit", op, true], ["Other income", row(q, "other_income")], ["Interest", row(q, "finance_costs")], ["Depreciation", row(q, "depreciation")], ["Profit before tax", row(q, "profit_before_tax"), true], ["Tax", row(q, "tax")], ["Net profit", np, true], ["EPS (₹)", ep]];
  const cols = [last, last - 1, yoy].filter((i) => i >= 0);
  return (
    <section className="block" style={{ "--sc": "var(--gold-deep)" } as React.CSSProperties}>
      <SectionHead id="quarter" no="03 · Latest quarter" icon="notes" tier="basic" title={`Results for ${q.periods[last]}`} sub={`Quarter ended ${end}. Compared with the previous quarter and the same quarter a year earlier.`} color="--gold-deep" />
      {rvY != null && npY != null && <Plain tone={npY >= 0 ? "good" : "warn"}>In the latest quarter, sales {rvY >= 0 ? "grew" : "fell"} {nf(Math.abs(rvY), 1)}% and profit {npY >= 0 ? "rose" : "fell"} {nf(Math.abs(npY), 1)}% compared with the same quarter last year.{opm[last] != null && opm[yoy] != null ? ` The operating margin ${(opm[last] as number) >= (opm[yoy] as number) ? "widened" : "narrowed"} from ${nf(opm[yoy] as number, 1)}% to ${nf(opm[last] as number, 1)}%.` : ""}</Plain>}
      <div className="qk">{tiles.map((t) => (
        <div className="qt" key={t.k} style={{ "--qc": t.c } as React.CSSProperties}>
          <div className="qt-h"><span className="qt-i"><Icon name={t.ic} /></span><span className="label">{t.k}</span></div>
          <div className="qt-v">{t.v[last] == null ? "—" : t.fmt(t.v[last] as number)}</div>
          {t.sub && <div className="qt-s">{t.sub}</div>}
          <div className="qt-d"><Delta v={chg(t.v[last], yoy >= 0 ? t.v[yoy] : null)} label="vs year ago" /><Delta v={chg(t.v[last], t.v[last - 1])} label="vs last quarter" /></div>
          <MiniBars labels={q.periods.slice(-8)} series={[{ key: t.k, label: t.k, values: t.v.slice(-8), color: t.c }]} fmt={t.bar} height={116} highlight={7 - (t.v.slice(-8).length < 8 ? 8 - t.v.slice(-8).length : 0)} />
        </div>))}</div>
      <div className="card acc qtab" style={{ "--ac": "var(--gold)" } as React.CSSProperties}>
        <div className="card-h"><h3><span className="ci"><Icon name="table" /></span>Profit and loss for the quarter</h3><span className="s">₹ Crore · change in brackets</span></div>
        <div className="tw"><table className="qtt"><thead><tr><th>Line</th>{cols.map((i, j) => <th key={i} className={j === 0 ? "latest" : ""}>{q.periods[i]}{j === 1 ? " (last quarter)" : j === 2 ? " (year ago)" : ""}</th>)}</tr></thead>
          <tbody>{lines.map(([k, v, b]) => <tr key={k} className={b ? "sub" : ""}><td>{k}</td>{cols.map((i, j) => { const x = v[i], ref = j === 0 ? null : v[last], c = ref != null && x != null ? chg(ref, x) : null; return <td key={i} className={j === 0 ? "latest" : ""}>{x == null ? "—" : num(x, k.startsWith("EPS") ? 2 : 0)}{j > 0 && c != null && <small className={c >= 0 ? "pos" : "neg"}> ({c >= 0 ? "+" : "−"}{nf(Math.abs(c), 1)}%)</small>}</td>; })}</tr>)}</tbody></table></div>
        <p className="faint" style={{ fontSize: 12, margin: "10px 0 0" }}>Brackets show how much the latest quarter changed compared with that column. Figures are as reported on the exchange filing.</p>
      </div>
    </section>
  );
}

/* ============== Trends grid ============== */
type Card = { id: string; title: string; hint?: string; annualOnly?: boolean; build: (m: "q" | "a") => { labels: string[]; series: BarSeries[]; mode?: "single" | "group" | "stack"; fmt: (v: number) => string } | null };

export function TrendsSection({ f, seg, e, r }: { f?: Financials; seg?: Segments; e?: Events; r?: Ratios }) {
  const [tab, setTab] = useState<"key" | "margin" | "div">("key");
  const [mode, setMode] = useState<"q" | "a">("q");
  const [big, setBig] = useState<string | null>(null);
  if (!f) return null;
  const A = f.yearly, Q = f.quarterly.pl;
  const tbl = (m: "q" | "a") => (m === "q" ? Q : A.pl);
  const mk = (title: string, key: string, color: string, fmt = crf): Card => ({ id: key, title, build: (m) => { const t = tbl(m); return { labels: t.periods, series: [{ key, label: title, values: row(t, key), color }], fmt }; } });
  const annual = (id: string, title: string, hint: string, build: Card["build"]): Card => ({ id, title, hint, annualOnly: true, build });
  const segColors = [G, INK, STONE, DEEP, "var(--c3)"];
  const cards: Record<typeof tab, Card[]> = {
    key: [
      mk("Revenue", "revenue", G),
      annual("seg", "Revenue by segment", "Annual", () => seg && seg.periods.length ? { labels: seg.periods, mode: "stack" as const, fmt: crf, series: Object.entries(seg.segments).sort((a, b) => ((b[1].revenue.slice(-1)[0] as number) || 0) - ((a[1].revenue.slice(-1)[0] as number) || 0)).map(([k, v], i) => ({ key: k, label: k, values: v.revenue, color: segColors[i % segColors.length] })) } : null),
      mk("Operating profit", "operating_profit", DEEP),
      annual("fcf", "Free cash flow", "Annual", () => ({ labels: A.cf.periods, series: [{ key: "fcf", label: "Free cash flow", values: row(A.cf, "free_cash_flow"), color: INK }], fmt: crf })),
      mk("Net profit", "net_profit", INK),
      mk("Earnings per share", "eps", STONE, eps),
      annual("cashdebt", "Cash and borrowings", "Annual", () => ({ labels: A.bs.periods, mode: "group" as const, fmt: crf, series: [{ key: "cash", label: "Cash", values: row(A.bs, "cash"), color: G }, { key: "debt", label: "Borrowings", values: row(A.bs, "borrowings"), color: INK }] })),
      annual("cfo", "Cash from operations", "Annual", () => ({ labels: A.cf.periods, series: [{ key: "cfo", label: "Cash from operations", values: row(A.cf, "operating"), color: DEEP }], fmt: crf })),
    ],
    margin: [
      { id: "opm", title: "Operating margin", build: (m) => { const t = tbl(m); return { labels: t.periods, series: [{ key: "opm", label: "Operating margin", values: ratio(row(t, "operating_profit"), row(t, "revenue")), color: G }], fmt: pctf }; } },
      { id: "npm", title: "Net margin", build: (m) => { const t = tbl(m); return { labels: t.periods, series: [{ key: "npm", label: "Net margin", values: ratio(row(t, "net_profit"), row(t, "revenue")), color: INK }], fmt: pctf }; } },
      annual("capex", "Capital spending", "Annual", () => ({ labels: A.cf.periods, series: [{ key: "capex", label: "Capital spending", values: row(A.cf, "capex").map((x) => (x == null ? null : Math.abs(x))), color: DEEP }], fmt: crf })),
      annual("roe", "Return on equity and capital", "Annual", () => r && r.history.rows.roe ? { labels: r.history.periods, mode: "group" as const, fmt: pctf, series: [{ key: "roe", label: "ROE", values: r.history.rows.roe, color: G }, { key: "roce", label: "ROCE", values: r.history.rows.roce || [], color: INK }] } : null),
      annual("int", "Interest and depreciation", "Annual", () => ({ labels: A.pl.periods, mode: "group" as const, fmt: crf, series: [{ key: "i", label: "Interest", values: row(A.pl, "finance_costs"), color: INK }, { key: "d", label: "Depreciation", values: row(A.pl, "depreciation"), color: STONE }] })),
      annual("tax", "Tax paid on profit", "Annual", () => ({ labels: A.pl.periods, series: [{ key: "t", label: "Tax", values: row(A.pl, "tax"), color: STONE }], fmt: crf })),
    ],
    div: [
      annual("dps", "Dividend per share", "Annual", () => e && e.dividendsByFY.periods.length ? { labels: e.dividendsByFY.periods, series: [{ key: "dps", label: "Dividend per share", values: e.dividendsByFY.dps, color: G }], fmt: eps } : null),
      annual("paid", "Dividends paid out", "Annual", () => ({ labels: A.cf.periods, series: [{ key: "p", label: "Dividends paid", values: row(A.cf, "dividends_paid").map((x) => (x == null ? null : Math.abs(x))), color: DEEP }], fmt: crf })),
      annual("payout", "Share of profit paid out", "Annual", () => r && r.history.rows.dividend_payout ? { labels: r.history.periods, series: [{ key: "po", label: "Payout ratio", values: r.history.rows.dividend_payout, color: INK }], fmt: pctf } : null),
    ],
  };
  const list = cards[tab];
  return (
    <section className="block" style={{ "--sc": "var(--gold)" } as React.CSSProperties}>
      <SectionHead id="trends" no="05 · Trends" icon="line" tier="basic" title="How the numbers have moved" sub="Quarter by quarter or year by year. Hover a column for its exact value." color="--gold" />
      <div className="tr-bar">
        <div className="seg" role="tablist" aria-label="Trend groups">{([["key", "Key metrics"], ["margin", "Margins and investment"], ["div", "Dividends"]] as const).map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}>{l}</button>)}</div>
        <div className="seg" role="group" aria-label="Period"><button aria-pressed={mode === "q"} onClick={() => setMode("q")}>Quarterly</button><button aria-pressed={mode === "a"} onClick={() => setMode("a")}>Annual</button></div>
      </div>
      <div className="tr-grid">{list.map((c) => {
        const d = c.build(mode); if (!d || !d.series.some((s) => s.values.some((v) => v != null))) return null;
        const open = big === c.id;
        return (
          <div className={"card tr-c" + (open ? " big" : "")} key={c.id}>
            <div className="tr-h"><h3>{c.title}</h3>{c.annualOnly && mode === "q" && <span className="chip ghost">Annual</span>}
              <button className="tr-x" aria-label={open ? `Shrink ${c.title}` : `Expand ${c.title}`} aria-pressed={open} onClick={() => setBig(open ? null : c.id)}><Icon name="arrow" /></button></div>
            <MiniBars labels={d.labels} series={d.series} mode={d.mode} fmt={d.fmt} height={open ? 240 : 150} w={open ? 900 : 300} highlight={d.labels.length - 1} />
            {d.series.length > 1 && <div className="tr-key">{d.series.map((s) => <span key={s.key}><i style={{ background: s.color }} />{s.label}</span>)}</div>}
          </div>);
      })}</div>
      <p className="faint" style={{ fontSize: 12, margin: "10px 2px 0" }}>₹ Crore unless stated. Cash flow and balance sheet items are reported once a year, so they stay annual.</p>
    </section>
  );
}
