// What a plan below Gold sees at /advanced-score-screener: an explanation, a static example (sample markup, no real figures) and the benefits.
// Nothing here reads the universe, so no Prism value reaches the browser of a plan that does not include it.
import { Link } from "react-router";
import { Gate } from "../Gate";
import { PageArt } from "../PageArt";
import { Icon } from "../../lib/icons";
import { useUI } from "../../lib/ui";
import { MINUS } from "../../lib/format";
import "../../styles/scorescreen.css";

const POINTS = [
  "The FinLit Prism score with its rating word for every listed company",
  "Four fundamental parts, each 0 to 100: Fundamentals, Valuation, Quality, Risk",
  "Short-term and long-term technical views, from " + MINUS + "100 to +100",
  "Filters, quick views, compare, watchlist and CSV export",
];
/** Invented companies and numbers, only to show the shape of the page. */
const SAMPLE: { n: string; sector: string; z: number; w: string; p: [number, number, number, number]; st: [string, string]; lt: [string, string] }[] = [
  { n: "Example Company A", sector: "Sector one", z: 82, w: "Strong", p: [78, 64, 85, 71], st: ["Positive", "+31"], lt: ["Positive", "+24"] },
  { n: "Example Company B", sector: "Sector two", z: 68, w: "Healthy", p: [66, 52, 74, 80], st: ["Neutral", "+6"], lt: ["Positive", "+22"] },
  { n: "Example Company C", sector: "Sector one", z: 54, w: "Average", p: [58, 45, 60, 49], st: ["Negative", MINUS + "28"], lt: ["Neutral", MINUS + "4"] },
  { n: "Example Company D", sector: "Sector three", z: 41, w: "Weak", p: [40, 70, 38, 35], st: ["Neutral", MINUS + "9"], lt: ["Negative", MINUS + "33"] },
];
const tone = (v: number) => (v >= 70 ? "hi" : v >= 50 ? "mid" : "lo");

export function AdvancedUpgrade() {
  const { has, upgrade } = useUI();
  const silver = has("silver");
  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><PageArt kind="research" />
        <div className="eyebrow">Advanced score screener</div><h1>Screen every company with FinLit Prism.</h1>
        <p>The advanced model for the whole market: the Prism score, its four fundamental parts and two technical views, side by side, with filters, quick views, compare and export. It is part of the Gold plan.{" "}
          {silver ? <>Your plan includes the <Link to="/score-screener">Basic score screener</Link>, which uses the FinLit score.</> : <>The <Link to="/score-screener">Basic score screener</Link> uses the FinLit score and comes with Silver.</>}</p></div></section>
      <div className="wrap scr-wrap">
        <div className="sx-up">
          <div className="sx-ex-h"><span className="tier gold">Example</span><span className="muted">Sample companies and figures, only to show the layout. Not real data.</span></div>
          <Gate tier="gold" title="Advanced score screener" points={POINTS}>
            <section className="card sx-ex" aria-label="Example of the advanced score screener">
              <div className="scr-tw"><table className="scr-t ss-t sx-t">
                <caption className="sr">Example of the advanced score screener with invented companies</caption>
                <thead><tr><th scope="col">Company</th><th scope="col">Prism</th><th scope="col">Fundamentals</th><th scope="col">Valuation</th><th scope="col">Quality</th><th scope="col">Risk</th><th scope="col">Short-term technical</th><th scope="col">Long-term technical</th></tr></thead>
                <tbody>{SAMPLE.map((r) => (
                  <tr key={r.n}>
                    <td className="stick"><span className="co"><span><b>{r.n}</b><small>{r.sector}</small></span></span></td>
                    <td className="pzs-c"><span className="pzs"><span className={"ssp pzs-n " + tone(r.z)}>{r.z}</span><span className="pzs-l"><b className={tone(r.z)}>{r.w}</b></span></span></td>
                    {r.p.map((v, i) => <td key={i} className="ss-pc"><span className={"ssp pzs-n " + tone(v)}>{v}</span></td>)}
                    <td><span className="pzs-w"><b>{r.st[0]}</b><small>{r.st[1]}</small></span></td><td><span className="pzs-w"><b>{r.lt[0]}</b><small>{r.lt[1]}</small></span></td>
                  </tr>))}</tbody>
              </table></div>
            </section>
          </Gate>
          <section className="card sx-ben">
            <h2>What Gold adds</h2>
            <ul>{POINTS.map((p) => <li key={p}><Icon name="check" /><span>{p}</span></li>)}</ul>
            <p className="muted">It describes financial health and price trend from filings and prices. Information only, not advice.</p>
            <button type="button" className="btn primary" onClick={() => upgrade("gold", "The Advanced score screener is part of Gold.")}>Unlock with Gold <Icon name="arrow" /></button>
          </section>
        </div>
      </div>
    </>
  );
}
