import { Icon } from "../lib/icons";
import { dateIN, nf } from "../lib/format";
import type { Summary } from "../lib/api";
import { leverageText, priceBand, stageText, useTrading } from "../lib/trading";

/** Under the price: a surveillance warning when the exchange has the share under ASM/GSM, then the day's price band, F&O and margin trading.
 * Nothing is said when a fact is not positively known (no "not under surveillance", no "no F&O"). Information only, never a suggestion. */
export function TradingFacts({ s }: { s: Summary }) {
  const t = useTrading(s.profile.symbol).data;
  const band = priceBand(s.quote), sv = t?.surveillance, fno = t?.fno, mtf = t?.mtf;
  if (!sv && !fno && !mtf && !band) return null;
  const stage = stageText(sv?.stage), from = `the broker Dhan's instrument file${t?.asOf ? ` of ${dateIN(t.asOf)}` : ""}`;
  return (
    <div className="tfacts">
      {sv && (
        <div className="tf-warn" role="note" aria-label="Exchange surveillance">
          <Icon name="alert" />
          <div>
            <b>Under exchange surveillance (ASM/GSM){stage ? `, ${stage}` : ""}</b>
            <p>The exchange has placed this stock under its additional or graded surveillance measures. Exchanges do this when a stock's price or trading needs a closer watch; it is not by itself a finding against the company. While it lasts, stricter trading rules can apply, such as higher margins, a narrower price band or trade-for-trade settlement.</p>
            <small>From {from}. NSE and BSE publish the current lists and their rules.</small>
          </div>
        </div>
      )}
      {(band || fno || mtf) && (
        <ul className="tf-list" aria-label="Trading facts">
          {band && <li title="The lowest and highest prices the exchange allows in the trading session, from the same live quote as the price above."><span className="k">Day's price band</span><span className="v">₹{nf(band.lower)} – ₹{nf(band.upper)}</span>{band.at && <em>At the {band.at} circuit</em>}</li>}
          {fno && <li><span className="k">Futures &amp; options (F&amp;O)</span><span className="v">Yes{fno.lotSize ? `, NSE lot of ${nf(fno.lotSize, 0)} shares` : ""}</span></li>}
          {mtf && <li><span className="k">Margin trading (MTF)</span><span className="v">Eligible, up to {leverageText(mtf.leverage)} leverage</span><small>as listed by the broker Dhan; each broker sets its own list and terms</small></li>}
        </ul>
      )}
    </div>
  );
}
