// The scheme table: sortable columns, the columns you chose, a tick box to add a scheme to the comparison. Wide tables scroll inside their own box.
import { Link } from "react-router";
import { HScroll } from "../components/HScroll";
import { useInfoPop } from "../components/Info";
import {
  COLUMNS, COL_GROUPS, aumBucket, aumText, costLevel, returnBand, categoryShort, checklistLines, navFull, navText, noReturnsText, terText,
  type ColDef, type ColId, type FundRow, type ListQuery, type PeerStats, type SortKey,
} from "../lib/mf";
import { dateIN } from "../lib/format";
import { Fig, PlanChip } from "./Bits";
import { tintOf } from "../lib/mfSummary";

const shortAmc = (a: string) => a.replace(/\s*mutual fund\s*$/i, "");
const MARK = { pass: "✓", fail: "✗", unknown: "–" } as const;

/** "3/5": checks passed of those that could be worked out. Hover, focus or tap shows each check with the figures behind it. */
function ChecklistCell({ r, peers }: { r: FundRow; peers?: Record<string, PeerStats> }) {
  const show = useInfoPop();
  const c = r.checklist;
  if (!c) {
    const why = r.optionClass !== "Growth" ? "The checklist is worked out for Growth options." : !r.active ? "This scheme has stopped publishing NAVs." : "Not worked out yet for this scheme.";
    return <span className="mf-na" title={why} aria-label={`No checklist. ${why}`}>—</span>;
  }
  const lines = checklistLines(r, peers);
  const [, plan] = c.peer.split("|");
  const g = {
    key: "checklist", label: `Checklist: ${c.pass} of ${c.of} checks passed`, lines: lines.map((l) => `${MARK[l.state]} ${l.text}`),
    read: `Compared with the active ${plan} plan Growth options of ${categoryShort(r.category)} (both spellings AMFI uses). A dash (–) is a check that could not be worked out; it is not counted.`,
  };
  const label = `Checklist: ${c.pass} of ${c.of} checks passed. ` + lines.map((l) => `${l.state === "pass" ? "Passed" : l.state === "fail" ? "Not passed" : "Not known"}: ${l.text}`).join(" ");
  return (
    <button type="button" className={"mf-chk" + (c.of && c.pass / c.of >= 0.6 ? " hi" : "")} aria-label={label}
      onMouseEnter={(e) => show(g, e.currentTarget)} onMouseLeave={() => show(null)} onFocus={(e) => show(g, e.currentTarget)} onBlur={() => show(null)}
      onClick={(e) => { e.stopPropagation(); show(g, e.currentTarget); }}>
      <span className="mf-meter" aria-hidden="true">{lines.map((l) => <i key={l.key} className={l.state} />)}</span>
      <span className="mf-chk-n"><b>{c.pass}</b>/{c.of}</span>
    </button>
  );
}

/** A thin bar under a return, its length against the largest figure of that column on the page (green up, red down): a quick visual scale, nothing more. */
const Bar = ({ v, max }: { v: number | null | undefined; max: number }) =>
  v == null || !max ? null : <i className={"mf-rbar " + (v < 0 ? "neg" : "pos")} style={{ width: `${Math.max(4, Math.min(100, (Math.abs(v) / max) * 100))}%` }} aria-hidden="true" />;
type Scale = Partial<Record<ColId, number>>;

function cell(c: ColDef, r: FundRow, peers?: Record<string, PeerStats>, scale: Scale = {}) {
  const why = noReturnsText(r.noReturns);
  switch (c.id) {
    case "amc": return shortAmc(r.amc);
    case "category": return <span title={r.category}>{categoryShort(r.category)}</span>;
    case "plan": return r.plan === "Unspecified" ? "—" : r.plan;
    case "option": return r.option || "—";
    case "nav": return r.nav == null ? <span className="mf-na" aria-label="No NAV">—</span> : <span title={navFull(r.nav)}>{navText(r.nav)}</span>;
    case "navDate": return r.navDate ? dateIN(r.navDate, { day: "numeric", month: "short", year: "2-digit" }) : "—";
    case "change": return <span className="mf-rf"><Fig v={r.change} why={r.active ? "The previous NAV is not on file yet." : why} />{r.change == null && <small>{r.active ? "no previous NAV" : "stopped"}</small>}</span>;
    case "r1y": case "r3y": case "r5y": {
      const years = c.id === "r1y" ? 1 : c.id === "r3y" ? 3 : 5;
      const v = r[c.id] ?? null;
      const short = v == null ? shortWhy(r.noReturns, "Insufficient history") : "";
      const band = returnBand(c.id, v);
      return <span className="mf-rf"><Fig v={v} why={why || `Younger than ${years} year${years > 1 ? "s" : ""}, or no NAV near the start date.`} /><Bar v={v} max={scale[c.id] ?? 0} />{short && <small>{short}</small>}
        {band && <small className={"mf-band b" + band.step} title="A screening band, not a performance standard: equity, debt and hybrid funds need different yardsticks.">{band.label}</small>}</span>;
    }
    case "sip3y": case "sip5y": {
      const years = c.id === "sip3y" ? 3 : 5;
      const v = r[c.id] ?? null;
      return <span className="mf-rf"><Fig v={v} why={why || `Needs a month-end NAV for each of the last ${years * 12} months; younger schemes, and month-ends not loaded yet, have none.`} />
        <Bar v={v} max={scale[c.id] ?? 0} />{v == null && <small>{shortWhy(r.noReturns, "Insufficient history")}</small>}</span>;
    }
    case "aum": {
      if (r.aum == null) return <span className="mf-na" title="Fund size is not in AMFI's latest quarterly AUM report or the fund house's month-end portfolio file loaded." aria-label="No fund size">—</span>;
      const when = r.aumAsOf ? dateIN(r.aumAsOf, { month: "short", year: "numeric" }) : "";
      const src = r.aumKind === "m" ? `Net assets at the end of ${when}, all plans together (fund house's portfolio file)` : `Average for the quarter to ${when}, all plans together (AMFI)`;
      const size = aumBucket(r.aum);
      return <span className="mf-aum" title={src}>{aumText(r.aum)}{size && <small className={"mf-size s" + size.step} title={`${size.range}. Size says how big the fund is, not how good it is.`}><i aria-hidden="true" />{size.label}</small>}</span>;
    }
    case "ter": return r.ter == null
      ? <span className="mf-na" title="This plan is not in AMFI's latest expense ratio (TER) file." aria-label="No expense ratio">—</span>
      : (() => {
        const cost = costLevel(r.ter, r.checklist ? peers?.[r.checklist.peer]?.ter : null);
        return <span className="mf-aum" title={`Total expense ratio of the ${r.plan} plan, percent a year${r.terDate ? `, as of ${dateIN(r.terDate)}` : ""} (AMFI)`}>{terText(r.ter)}
          {cost && <small className={"mf-band c" + cost.step} title="Against the median of the same category and plan: low is 20% or more under it, high is 20% or more over it.">{cost.label} for category</small>}</span>;
      })();
    case "checklist": return <ChecklistCell r={r} peers={peers} />;
  }
}
/** The short visible reason under a dash (the full sentence is in the tooltip and read out by screen readers). */
function shortWhy(code: FundRow["noReturns"], young: string): string {
  switch (code) {
    case "stopped": return "stopped";
    case "idcw": return "IDCW option";
    case "unstated": return "no Growth option";
    case "no_history": return "history loading";
    default: return young;
  }
}

export function FundTable({ rows, cols, q, onSort, picked, onPick, peers }: {
  rows: FundRow[]; cols: ColId[]; q: ListQuery; onSort: (s: SortKey) => void; picked: number[]; onPick: (code: number) => void; peers?: Record<string, PeerStats>;
}) {
  const defs = COLUMNS.filter((c) => cols.includes(c.id));
  // the heading row above: neighbouring columns of one group share a heading ("Returns", "SIP returns")
  const runs: { group?: ColDef["group"]; n: number }[] = [];
  for (const c of defs) { const last = runs[runs.length - 1]; if (last && last.group === c.group) last.n++; else runs.push({ group: c.group, n: 1 }); }
  const sorted = (key: SortKey | null) => (key && q.sort === key ? (q.dir === "asc" ? "ascending" : "descending") : key ? "none" : undefined);
  const scale: Scale = {};
  for (const id of ["r1y", "r3y", "r5y", "sip3y", "sip5y"] as const) scale[id] = Math.max(0, ...rows.map((r) => Math.abs(r[id] ?? 0)));
  const tint = (c: ColDef, r: FundRow): React.CSSProperties | undefined => {
    if (c.id !== "r1y" && c.id !== "r3y" && c.id !== "r5y" && c.id !== "sip3y" && c.id !== "sip5y") return undefined;
    const t = tintOf(r[c.id], scale[c.id] ?? 0);
    return t ? ({ "--tint": `color-mix(in srgb, var(${t.tone === "pos" ? "--gain" : "--loss"}) ${Math.round(8 + t.k * 22)}%, transparent)` } as React.CSSProperties) : undefined;
  };
  const cls = (c: ColDef) => (c.num ? "num" : "txt") + (c.group ? ` mf-retcol mf-g-${c.group}` : "") + ` mf-c-${c.id}`;
  return (
    <HScroll label="schemes table">
      <table className="mf-table">
        <caption className="sr-only">Mutual fund schemes. Use the column buttons to sort.</caption>
        <thead>
          {runs.some((r) => r.group) && (
            <tr className="mf-grouprow" aria-hidden="true"><th />{runs.map((r, i) => (r.group ? <th key={i} colSpan={r.n} className={`mf-retgrp mf-g-${r.group}`}>{COL_GROUPS[r.group]}</th> : <th key={i} colSpan={r.n} />))}</tr>)}
          <tr>
            <th scope="col" aria-sort={sorted("name")}><button className="mf-sort" onClick={() => onSort("name")}>Scheme{q.sort === "name" && <i aria-hidden="true">{q.dir === "asc" ? "▲" : "▼"}</i>}</button></th>
            {defs.map((c) => (
              <th key={c.id} scope="col" aria-sort={sorted(c.sort)} className={cls(c)} title={c.hint}>
                {c.sort ? <button className="mf-sort" aria-label={c.group ? `${COL_GROUPS[c.group]}, ${c.label}` : undefined} onClick={() => onSort(c.sort!)}>{c.label}{q.sort === c.sort && <i aria-hidden="true">{q.dir === "asc" ? "▲" : "▼"}</i>}</button> : c.label}
              </th>))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.code} className={r.active ? "" : "mf-stopped"}>
              <th scope="row" className="mf-name">
                <label className="mf-pickbox" title={picked.includes(r.code) ? "Remove from comparison" : "Add to comparison"}>
                  <input type="checkbox" checked={picked.includes(r.code)} onChange={() => onPick(r.code)} aria-label={`Compare ${r.name}`} />
                </label>
                <span className="mf-nm">
                  <Link to={`/funds/${r.code}`}>{r.name}</Link>
                  <small><span className="mf-house">{shortAmc(r.amc)}</span><PlanChip plan={r.plan} option={r.option} />{!r.active && <span className="chip ghost">Stopped publishing</span>}</small>
                  {r.nav != null && <small className="mf-navm">NAV <span className="mono" title={navFull(r.nav)}>{navText(r.nav)}</span></small>}
                </span>
              </th>
              {defs.map((c) => <td key={c.id} className={cls(c) + (tint(c, r) ? " mf-tinted" : "")} style={tint(c, r)}>{cell(c, r, peers, scale)}</td>)}
            </tr>))}
        </tbody>
      </table>
    </HScroll>
  );
}
