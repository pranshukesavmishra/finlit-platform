// Small shared pieces of the mutual fund pages: a glossary hint, a return figure with its reason, the source / disclaimer footer, the "not available yet" panel.
import { Icon } from "../lib/icons";
import { TERMS, type Term } from "../lib/glossary";
import { Info } from "../components/Info";
import { dateIN } from "../lib/format";
import { DISCLAIMER, MIRROR_LABEL, pctText, tone, type Facts, type FundDetail } from "../lib/mf";
import extra from "./newTerms.json";

// Words for this section. They live in backend/tests/fixtures/mf/new_glossary_terms.json until merged into the glossary; once the site glossary has them this copy is unused.
const EXTRA = extra as Term[];
const termById = (id: string): Term | undefined => TERMS.find((t) => t.id === id) || EXTRA.find((t) => t.id === id);

/** A word with an (i) button that explains it in plain English, from the site glossary. Renders just the word if the term is unknown. */
export function GTerm({ id, children }: { id: string; children: React.ReactNode }) {
  const t = termById(id);
  if (!t) return <>{children}</>;
  return <span className="mf-term">{children}<Info g={{ key: t.id, label: t.term, what: t.meaning, read: t.how, formula: t.formula || undefined, note: t.finlit || undefined }} /></span>;
}

/** A percent figure coloured by sign, or a dash with the reason it is missing (readable on touch and by screen readers, not only on hover). */
export function Fig({ v, why, d = 2, plus = true, plain = false }: { v: number | null | undefined; why?: string | null; d?: number; plus?: boolean; plain?: boolean }) {
  if (v == null) return <span className="mf-na" title={why || undefined} aria-label={why ? `No figure. ${why}` : "No figure"}>—</span>;
  return <span className={plain ? "" : tone(v)}>{pctText(v, d, plus)}</span>;
}

/** Source, data date, last update and the standing disclaimer: on every page of the section. */
export function Foot({ facts, history }: { facts?: Facts | null; history?: FundDetail["history"] | null }) {
  return (
    <footer className="mf-foot" aria-label="Source and disclaimer">
      <p><b>{DISCLAIMER}</b></p>
      <p>
        Source: {facts?.source || "AMFI (Association of Mutual Funds in India), official NAV files"}.
        {facts?.dataDate && <> Data date: {dateIN(facts.dataDate)}.</>}
        {facts?.updatedAt && <> Last updated: {new Date(facts.updatedAt).toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" })}.</>}
        {history?.source === "mirror" && <> {MIRROR_LABEL}.</>}
      </p>
    </footer>
  );
}

/** What this section does not have yet, in one compact panel, with the reason (nothing is shown rather than guessed). */
export function NotAvailable({ items, why }: { items: string[]; why: string }) {
  return (
    <section className="card mf-na-panel" aria-labelledby="mf-na-h">
      <h3 id="mf-na-h"><span className="ci"><Icon name="info" /></span>Not available yet</h3>
      <ul className="mf-chips">{items.map((x) => <li key={x}><span className="chip ghost">{x}</span></li>)}</ul>
      <p className="muted">{why}</p>
    </section>
  );
}

export const PlanChip = ({ plan, option }: { plan: string; option: string }) => <span className="mf-plan">{plan === "Unspecified" ? "Plan not stated" : plan}{option && option !== "Not stated" ? ` · ${option.replace(/\s*option$/i, "")}` : ""}</span>;
