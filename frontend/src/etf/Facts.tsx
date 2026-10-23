// Fund facts from AMFI's published files and the exchange's rules (through the API): each field shows its value, the date it is true on and where it came from,
// or a dash with the reason. Nothing is filled in from memory.
import { Icon } from "../lib/icons";
import { day, useEtfFacts, type FactCell } from "../lib/etf";
import { Blank, GlossInfo } from "./common";
import type { GlossName } from "../lib/etf";

type Field = { key: string[]; label: string; term?: GlossName; fallback?: string };
const FIELDS: Field[] = [
  { key: ["aum", "AUM"], label: "Assets under management", term: "Assets under management (AUM)", fallback: "The total value of money a fund holds for its investors." },
  { key: ["ter", "expenseRatio", "TER"], label: "Expense ratio (TER)", term: "Expense ratio", fallback: "The yearly fee a fund charges." },
  { key: ["exitLoad", "exit_load"], label: "Exit load" },
  { key: ["benchmark"], label: "Benchmark", term: "Benchmark", fallback: "The index or yardstick a fund is measured against." },
  { key: ["managers", "fundManagers", "manager"], label: "Fund manager" },
  { key: ["riskometer", "risk"], label: "Riskometer" },
  { key: ["launchDate", "launch", "inceptionDate"], label: "Launch date" },
  { key: ["minInvestment", "minimumInvestment", "minimum"], label: "Minimum investment" },
  { key: ["trackingError", "tracking_error"], label: "Tracking error", term: "Tracking error", fallback: "How far a fund drifts from the index it follows." },
];
const NOT_IN = "Not in the fund-house disclosures we have read for this ETF";

function show(c: FactCell, label: string): string {
  const v = c.value;
  if (Array.isArray(v)) return v.join(", ");
  if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v)) return day(v);   // a date (launch date) reads as a date
  if (typeof v === "number") return label.startsWith("Expense") ? `${v}% a year` : label.startsWith("Assets") || label.startsWith("Minimum") ? "₹" + v.toLocaleString("en-IN") : String(v);
  return String(v ?? "");
}

export function EtfFacts({ symbol }: { symbol: string }) {
  const { data, isLoading, isError } = useEtfFacts(symbol);
  const facts = data?.facts ?? {};
  const why = isError ? "The fund facts could not be loaded right now" : data?.unavailable ?? null;
  return (
    <section className="card etf-sec" aria-labelledby="h-ff">
      <div className="card-h"><h3 id="h-ff"><span className="ci"><Icon name="id" /></span>Fund facts</h3><span className="s">AMFI and exchange rules</span></div>
      {isLoading ? <p className="faint">Loading…</p> : (
        <dl className="etf-facts etf-ffacts">
          {FIELDS.map((f) => {
            const hit = f.key.map((k) => facts[k]).find(Boolean);
            const ok = hit && hit.value != null && hit.value !== "" && !hit.unavailable;
            return (
              <div key={f.label}>
                <dt>{f.label}{f.term && <GlossInfo name={f.term} fallback={f.fallback ?? ""} />}</dt>
                <dd>
                  {ok ? <>{show(hit!, f.label)}<small className="faint">{[hit!.asOf ? `as of ${day(hit!.asOf)}` : "", hit!.source || ""].filter(Boolean).join(" · ")}</small>
                    {hit!.note ? <small className="faint">{hit!.note}</small> : null}</>
                    : <Blank why={hit?.unavailable ?? why ?? NOT_IN} />}
                  {!ok && <small className="faint">{hit?.unavailable ?? why ?? NOT_IN}</small>}
                </dd>
              </div>);
          })}
        </dl>)}
      <p className="faint etf-small">The fund house's own factsheet and scheme documents are the authority for these. We show a dash rather than a guess.</p>
    </section>
  );
}
