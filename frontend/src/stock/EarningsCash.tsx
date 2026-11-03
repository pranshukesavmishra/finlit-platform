// Earnings & cash quality (section 09): ONE section that answers "is the profit real, and is it turning into cash?".
// Order: three verdict tiles, the read, the red flag and what to investigate (each shown once), then 1. Profit against cash, 2. Collections and stock,
// 3. Is the profit clean?, 4. The checks, and the rules and investor interpretation folded away. Everything is worked out from the company's own statements
// (lib/profitReality, lib/revenueCash, lib/earningsIntel); it describes, it is not a recommendation. Gold, like the two cards it replaces.
import { useContext } from "react";
import { Gate, OpenAccess, TierChip } from "../components/Gate";
import { Icon } from "../lib/icons";
import { fyLabel, type ProfitReality as PrModel } from "../lib/profitReality";
import { earningsIntel } from "../lib/earningsIntel";
import { fmtPct } from "../lib/revenueCash";
import { nf } from "../lib/format";
import { useUI } from "../lib/ui";
import { PrCash, PrChart, PrOneOff, PrWorking, useProfitReality } from "./ProfitReality";
import { DISCLAIMER, Tile, Trend, gapLine, useRevenueCashModel } from "./RevenueCash";
import { Pill } from "./EarningsIntel";
import "../styles/insights.css";
import "../styles/earningscash.css";

const TONE: Record<string, string> = { Strong: "s", Mixed: "w", "Needs a closer look": "f" };

/** The one red flag and the items to investigate, with the receivables warning written once (both bases together). */
export function flagsOf(pr: PrModel, m: ReturnType<typeof useRevenueCashModel>["m"], intel: ReturnType<typeof earningsIntel>) {
  const y = pr.years[pr.years.length - 1], L = m && m.state === "ok" ? m.latest : null;
  const rcRec = m?.warnings.find((w) => w.id === "receivables");
  const flag = (y?.receivablesFlag || rcRec) && (y?.receivablesGrowth != null || L?.receivablesGrowth != null)
    ? { title: "Customers are paying more slowly", text: `Receivables grew ${y?.receivablesGrowth != null ? fmtPct(y.receivablesGrowth, 1) + " on year-end balances" : ""}${y?.receivablesGrowth != null && L?.receivablesGrowth != null ? " and " : ""}${L?.receivablesGrowth != null ? fmtPct(L.receivablesGrowth, 1) + " on average balances" : ""}${y?.revenueGrowth != null ? `, against revenue growth of ${fmtPct(y.revenueGrowth, 1)}` : ""}${y ? ` (${fyLabel(y.period)})` : ""}. Sales are being booked faster than the cash comes in.` }
    : null;
  const watch = [...(m?.warnings ?? []).filter((w) => w.id !== "receivables" && w.id !== "improving"), ].slice(0, 3);
  const oi = y?.otherIncomeShare != null && y.otherIncomeShare >= 20 ? `Other income is ${nf(y.otherIncomeShare, 0)}% of pre-tax profit (${fyLabel(y.period)}). Check where it comes from and whether it repeats.` : null;
  const investigate = [oi, ...(intel?.questions ?? []).filter((q) => !/receivable/i.test(q))].filter((t): t is string => !!t).slice(0, 2);
  return { flag, watch, investigate };
}

export function EarningsCash({ symbol, lender, sector, industry, labels }: { symbol: string; lender: boolean; sector?: string | null; industry?: string | null; labels?: (string | null | undefined)[] }) {
  const { has } = useUI(), open = useContext(OpenAccess);
  const locked = !open && !has("gold");
  const pr = useProfitReality(symbol, lender), rc = useRevenueCashModel(symbol, lender, labels);
  const head = <div className="ec-h"><TierChip tier="gold" /></div>;
  if (locked) {
    return (
      <div className="card ec" id="earnings-body">{head}
        <Gate tier="gold" title="Earnings & cash quality" points={["Profit against cash, five years", "Receivables and inventory against sales", "One-off items taken out of the profit"]}>
          <div className="rcx-skel" aria-hidden="true"><i /><i /><i /><i /></div>
        </Gate>
      </div>);
  }
  if (!pr.years.length && !rc.loaded) return <div className="card ec" id="earnings-body"><div className="skeleton" style={{ height: 240 }} /></div>;
  if (!pr.years.length) return <div className="card ec" id="earnings-body"><p className="faint">Profit and cash flow are not reported for enough years to show this.</p></div>;
  const m = rc.m, intel = earningsIntel(pr, sector, industry), { flag, watch, investigate } = flagsOf(pr, m, intel);
  const ok = m && m.state === "ok" ? m : null, L = ok?.latest ?? null;
  return (
    <div className="card ec" id="earnings-body" aria-label="Earnings and cash quality">
      <div className="ec-tiles" role="list">
        <div className={"ec-tile " + (pr.verdict ? TONE[pr.verdict] : "")} role="listitem"><span className="k">Earnings quality</span><b>{pr.verdict ?? "Not enough data"}</b><small>{pr.findings.length ? `${pr.findings.length} point${pr.findings.length === 1 ? "" : "s"} to look at` : "Nothing flagged"}</small></div>
        <div className="ec-tile" role="listitem"><span className="k">Cash backing</span><b>{intel ? <Pill tone={intel.pill.tone}>{intel.pill.label}</Pill> : "Not enough data"}</b><small>{lender ? "Cash flow is not comparable for lenders" : "Operating cash flow against profit"}</small></div>
        <div className="ec-tile" role="listitem"><span className="k">Cash conversion health</span><b>{ok?.status ?? (m?.state === "lender" ? "Not comparable" : "Not enough data")}</b><small>{L?.ocfMargin != null ? `Operating cash flow ${fmtPct(L.ocfMargin)} of revenue (${L.period})` : "Operating cash flow against revenue"}</small></div>
      </div>

      {intel && <div className="ins v"><span className="ins-tag">The read</span><b>{intel.happening}</b></div>}
      {flag && <div className="ins f"><span className="ins-tag">Red flag</span><b>{flag.title}</b><p>{flag.text}</p></div>}
      {watch.map((w) => <div className="ins w" key={w.id}><span className="ins-tag">Watch</span><b>{w.text}</b><p>{w.why}</p></div>)}
      {investigate.map((t, i) => <div className="ins i" key={i}><span className="ins-tag">Investigate</span><p>{t}</p></div>)}

      {!lender && (<section className="ec-sec" aria-labelledby="ec-1"><h3 id="ec-1"><span className="ec-n">1</span>Profit against cash</h3>
        <PrCash r={pr} lender={lender} />
        {ok && <><h4 className="ec-k">Revenue growth and operating cash flow margin</h4><Trend years={ok.years} /></>}</section>)}

      {!lender && (<section className="ec-sec" aria-labelledby="ec-2"><h3 id="ec-2"><span className="ec-n">2</span>Collections and stock</h3>
        {L && <div className="rcx-ind">
          <Tile label="Receivables growth" v={L.receivablesGrowth} tone={L.receivablesGap != null && L.receivablesGap > 0 ? "warn" : ""} sub={gapLine(L.receivablesGap)} tip="Receivables on the balance sheet, this year against last year." basis={L.receivablesBasis} />
          <Tile label="Inventory growth" v={L.inventoryGrowth} tone={L.inventoryGap != null && L.inventoryGap > 0 ? "warn" : ""} sub={gapLine(L.inventoryGap)} tip="Inventory on the balance sheet, this year against last year." basis={L.inventoryBasis} />
        </div>}
        <PrWorking r={pr} lender={lender} /></section>)}

      <section className="ec-sec" aria-labelledby="ec-3"><h3 id="ec-3"><span className="ec-n">{lender ? 1 : 3}</span>Is the profit clean?</h3>
        <PrChart r={pr} lender={lender} /><PrOneOff r={pr} lender={lender} /></section>

      {intel && intel.modules.length > 0 && (<section className="ec-sec" aria-labelledby="ec-4"><h3 id="ec-4"><span className="ec-n">{lender ? 2 : 4}</span>{intel.modules.length === 6 ? "Six checks" : "The checks"}</h3>
        <ul className="ei-mods ec-checks">{intel.modules.map((mo) => (
          <li key={mo.key}><details><summary><span className="ci"><Icon name={mo.icon} /></span><span className="nm">{mo.name}</span><Pill tone={mo.tone}>{mo.badge}</Pill></summary>
            <ul className="ei-facts">{mo.facts.map((t, i) => <li key={i}>{t}</li>)}</ul></details></li>))}</ul></section>)}

      <details className="ec-fold"><summary>How this is decided</summary>
        <ul>{pr.rules.map((x) => <li key={x.key}><b>{x.text}.</b> <small>{x.detail}</small></li>)}</ul>
        {intel && <ul>{intel.modules.map((mo) => <li key={mo.key}><b>{mo.name}.</b> {mo.rule}</li>)}</ul>}
        <p className="faint">Two or more flagged rules, or "profit rose but cash did not", gives "Needs a closer look". One flagged rule or two watch rules gives "Mixed". Otherwise "Strong".</p>
      </details>
      {intel && <details className="ec-fold"><summary>Investor interpretation</summary>
        <dl><dt>Why it matters</dt><dd>{intel.meaning.why}</dd>
          {intel.meaning.risks.length > 0 && <><dt>Possible risks</dt><dd><ul>{intel.meaning.risks.map((t, i) => <li key={i}>{t}</li>)}</ul></dd></>}
          <dt>What to investigate next</dt><dd>{intel.meaning.where}</dd></dl></details>}
      {[...(intel?.caveats ?? []), ...pr.notes].map((t, i) => <p className="faint ec-note" key={i}>{t}</p>)}
      <p className="faint ec-note">Worked out from the company's own yearly statements. These are warning signs to investigate, not proof of anything. {DISCLAIMER}</p>
    </div>
  );
}
