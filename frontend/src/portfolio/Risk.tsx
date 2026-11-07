import { dateText, pct, readingsFor, sectorOrder, signedPct1 } from "./derive";
import { MODE_NOTE, NIFTY_NOTE } from "./words";
import type { Mode, PageObject } from "./types";
import { ChartZoom } from "../components/ChartZoom";

const secName = (s: string) => s.replace(/ \(not classified\)$/, "");

/** Share of the amount against share of the risk, by sector (short lists) or share by share (long lists). */
export function RiskShare({ page, mode, colors }: { page: PageObject; mode: Mode; colors: Record<string, string> }) {
  const long = page.layout === "long";
  const text = readingsFor(page, mode, "risk", 2).map((x) => x.text).join(" ") || "Risk is spread roughly in line with the amounts.";
  if (!long) {
    const secs = sectorOrder(page, mode), aw = page.sector_weight[mode], rw = page.sector_risk[mode];
    const max = Math.max(1, ...secs.map((s) => Math.max(aw[s] ?? 0, rw[s] ?? 0)));
    return (
      <section className="pfx-card pfx-grow" id="pf-risk" aria-labelledby="pfx-rk">
        <div className="pfx-h"><h2 id="pfx-rk">Share of the amount and share of the risk</h2><p className="pfx-note">{MODE_NOTE[mode]}</p></div>
        <p className="pfx-legend"><span><i className="amt" />Share of the amount</span><span><i className="risk" />Share of the ups and downs (risk)</span></p>
        <ul className="pfx-rbars">{secs.map((s) => (
          <li key={s}><span className="pfx-sec"><i className="pfx-dot" style={{ background: colors[s] }} aria-hidden="true" />{secName(s)}</span>
            <span className="pfx-rb"><span className="amt"><span className="tr"><i style={{ width: `${((aw[s] ?? 0) / max) * 100}%` }} /></span><b>{pct(aw[s] ?? 0)}</b></span><span className="risk"><span className="tr"><i style={{ width: `${((rw[s] ?? 0) / max) * 100}%` }} /></span><b>{pct(rw[s] ?? 0)}</b></span></span></li>))}</ul>
        <p className="pfx-line">{text}</p>
      </section>
    );
  }
  const rs = page.share_risk[mode], ws = page.share_weight[mode];
  const xs = Object.keys(rs).sort((a, b) => rs[b] - rs[a]);
  const max = Math.max(1, ...xs.map((s) => Math.max(rs[s], ws[s] ?? 0)));
  return (
    <section className="pfx-card pfx-wide" id="pf-risk" aria-labelledby="pfx-rk">
      <ChartZoom label={"Share of the risk, share by share"} className="cz-r">
      <div className="pfx-h"><h2 id="pfx-rk">Share of the risk, share by share</h2><p className="pfx-note">{MODE_NOTE[mode]}</p></div>
      <p className="pfx-legend"><span><i className="risk" />Share of the ups and downs (risk)</span><span><i className="line" />Share of the amount</span><span className="pfx-note">A bar above its line carries more risk than its amount.</span></p>
      <div className="pfx-vbars" role="img" aria-label="Each share's share of the risk against its share of the amount">{xs.map((s) => (
        <span key={s} title={`${s}: ${pct(rs[s])} of the risk, ${pct(ws[s] ?? 0)} of the amount`}>
          <span className="col"><i style={{ height: `${(rs[s] / max) * 100}%` }} /><em className="v" style={{ bottom: `${(rs[s] / max) * 100}%` }}>{rs[s].toFixed(1)}</em><u style={{ bottom: `${((ws[s] ?? 0) / max) * 100}%` }} /></span><em className="n">{s}</em></span>))}</div>
      <p className="pfx-line">{text}</p>
      </ChartZoom>
    </section>
  );
}

/** Against the NIFTY 50: beta, the index's worst weeks, the typical swing in a year and the worst fall from a high. */
export function Nifty({ page, mode }: { page: PageObject; mode: Mode }) {
  const m = page.market[mode], to = page.to;
  const cell = (label: string, list: string, nifty: string) => <div className="pfx-mk"><p className="pfx-mk-l">{label}</p><p className="pfx-mk-v">{list}</p><p className="pfx-sub">NIFTY 50: {nifty}</p></div>;
  const worst = readingsFor(page, mode, "market");
  return (
    <aside className="pfx-card pfx-side" aria-labelledby="pfx-nf">
      <h2 id="pfx-nf">Against the NIFTY 50</h2><p className="pfx-note">{MODE_NOTE[mode]}</p>
      <div className="pfx-mks">
        {cell("Beta to the index", m.beta.toFixed(2), "1.00")}
        {cell("Average of the 10 worst weeks", signedPct1(m.worst10_list), signedPct1(m.worst10_nifty))}
        {cell("Typical swing in a year", `${m.vol.toFixed(1)}%`, `${m.vol_nifty.toFixed(1)}%`)}
        {cell("Worst fall from a high", signedPct1(m.max_fall), signedPct1(m.max_fall_nifty))}
      </div>
      <p className="pfx-fine">{NIFTY_NOTE} Weeks to {dateText(to)}.</p>
      {worst.map((x) => <p className="pfx-fine" key={x.rule + x.text}>{x.text}</p>)}
    </aside>
  );
}
