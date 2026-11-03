// "What stands out across the report": every red flag, watch item and strength in one place, each linking to the section it comes from.
// Red flags and watch items from the profit-and-loss checks (lib/plFlags) and the scorecard notes; strengths from the scorecard notes. They describe
// what the figures did and are not a recommendation. Same Silver plan as the scorecard notes they repeat.
import { useMemo } from "react";
import type { Financials, Summary } from "../lib/api";
import { plInsights } from "../lib/plFlags";
import { Gate } from "../components/Gate";
import { Icon } from "../lib/icons";
import { SectionHead } from "./Sections";
import "../styles/insights.css";

export type Findings = { flags: Item[]; watch: Item[]; good: Item[] };
type Item = { key: string; title: string; text: string; to: string };

export function findingsOf(s: Summary, f: Financials | undefined, lender: boolean): Findings {
  const pl = plInsights({ annual: f?.yearly?.pl, quarterly: f?.quarterly?.pl, lender });
  const fromPl = (sev: "caution" | "watch") => pl.filter((i) => i.severity === sev).map((i) => ({ key: "pl-" + i.key, title: i.title, text: i.why, to: "financials" }));
  return {
    flags: fromPl("caution"),
    watch: [...fromPl("watch"), ...s.watchouts.map((n) => ({ key: "w-" + n.key, title: n.title, text: n.text, to: "notes" }))],
    good: s.strengths.map((n) => ({ key: "s-" + n.key, title: n.title, text: n.text, to: "notes" })),
  };
}

const jump = (id: string) => (e: React.MouseEvent) => { e.preventDefault(); document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" }); };

function Col({ kind, tag, icon, items, empty }: { kind: "f" | "w" | "s"; tag: string; icon: string; items: Item[]; empty: string }) {
  return (
    <div className="kf-col">
      <h3><span className={"ins-dot " + kind} aria-hidden="true"><Icon name={icon} /></span>{tag}<span className="kf-n">{items.length}</span></h3>
      {items.length ? items.map((i) => (
        <div className={"ins " + kind} key={i.key}><span className="ins-tag">{tag}</span><b>{i.title}</b><p>{i.text}</p><a href={"#" + i.to} onClick={jump(i.to)}>See the section ↓</a></div>
      )) : <p className="kf-none">{empty}</p>}
    </div>);
}

export function KeyFindings({ s, f, lender }: { s: Summary; f?: Financials; lender: boolean }) {
  const k = useMemo(() => findingsOf(s, f, lender), [s, f, lender]);
  const total = k.flags.length + k.watch.length + k.good.length;
  if (!total) return null;
  const counts = `${k.flags.length} red flag${k.flags.length === 1 ? "" : "s"} · ${k.watch.length} to watch · ${k.good.length} positive${k.good.length === 1 ? "" : "s"}`;
  return (
    <section className="block" style={{ "--sc": "var(--gold-deep)" } as React.CSSProperties}>
      <SectionHead id="findings" no="Key findings" icon="notes" tier="silver" title="What stands out across the report" color="--gold-deep" aside={<span className="sh-counts">{counts}</span>} />
      <Gate tier="silver" title="See every key finding in one place" points={["Red flags, items to watch and strengths together", "Each links to its section"]}>
        <div className="kf-g">
          <Col kind="f" tag="Red flag" icon="alert" items={k.flags} empty="No red flags from the profit and loss checks." />
          <Col kind="w" tag="Watch" icon="info" items={k.watch} empty="Nothing to watch right now." />
          <Col kind="s" tag="Strength" icon="check" items={k.good} empty="Nothing stands out yet." />
        </div>
        <p className="faint kf-foot">Describes the company's financial health from its filings and prices; not a recommendation. Information only, not investment advice.</p>
      </Gate>
    </section>
  );
}
