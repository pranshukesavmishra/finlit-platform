// The three figures every ETF page leads with: 1 day, 1 year, 5 years. Large, green or red with a real minus sign, an arrow so colour is never the only cue,
// and when a figure cannot be given, a dash with the reason in plain words (never only a tooltip).
import { Icon } from "../lib/icons";
import { GlossInfo, Tone } from "./common";
import { day, pct, rupee, type Headline } from "../lib/etf";

const sign = (v: number) => (v > 0 ? "▲ +" : v < 0 ? "▼ −" : "");
/** "▲ +12.34%" for a gain, "▼ −5.60%" for a loss. Two decimals, Indian digit grouping. */
export const bigMove = (v: number): string => (v === 0 ? "0.00%" : sign(v) + pct(Math.abs(v)));

export function ReturnsBlock({ head, asOf }: { head: Headline[]; asOf: string | null }) {
  return (
    <section className="card etf-sec etf-returns" aria-labelledby="h-r3">
      <div className="card-h">
        <h3 id="h-r3"><span className="ci"><Icon name="growth" /></span>Price returns <GlossInfo name="Price return" fallback="How much the exchange price changed. Dividends and other payouts are not included." /></h3>
        <span className="s">to {day(asOf)}</span>
      </div>
      <ul className="etf-r3">
        {head.map((h) => (
          <li key={h.key} className="etf-rc">
            <span className="label">{h.label}{h.key === "5y" && <small> · total</small>}</span>
            {h.value == null ? (
              <>
                <b className="etf-rbig etf-blank-big" aria-label="Not available">—</b>
                <span className="etf-rwhy">{h.why ?? "Not enough price history"}</span>
              </>
            ) : (
              <>
                <b className={"etf-rbig " + (h.value > 0 ? "up" : h.value < 0 ? "down" : "")}>{bigMove(h.value)}</b>
                {h.key === "5y" && h.annualised != null && <span className="etf-rsub">about <Tone v={h.annualised}>{pct(h.annualised)}</Tone> a year <GlossInfo name="CAGR (compound annual growth rate)" fallback="The yearly rate that gives the same total change over the period." /></span>}
                {h.from && h.to && <span className="etf-rfrom">{rupee(h.from.close)} on {day(h.from.date)} → {rupee(h.to.close)} on {day(h.to.date)}</span>}
                <span className="etf-rbasis">{h.basis}</span>
              </>
            )}
          </li>))}
      </ul>
    </section>
  );
}
