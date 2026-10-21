// The scheme table: sortable columns, the columns you chose, a tick box to add a scheme to the comparison. Wide tables scroll inside their own box.
import { Link } from "react-router";
import { HScroll } from "../components/HScroll";
import { COLUMNS, categoryShort, navFull, navText, noReturnsText, type ColDef, type ColId, type FundRow, type ListQuery, type SortKey } from "../lib/mf";
import { dateIN } from "../lib/format";
import { Fig, PlanChip } from "./Bits";

function cell(c: ColDef, r: FundRow) {
  const why = noReturnsText(r.noReturns);
  switch (c.id) {
    case "amc": return r.amc.replace(/\s*mutual fund\s*$/i, "");
    case "category": return <span title={r.category}>{categoryShort(r.category)}</span>;
    case "plan": return r.plan === "Unspecified" ? "—" : r.plan;
    case "option": return r.option || "—";
    case "nav": return r.nav == null ? <span className="mf-na" aria-label="No NAV">—</span> : <span title={navFull(r.nav)}>{navText(r.nav)}</span>;
    case "navDate": return r.navDate ? dateIN(r.navDate, { day: "numeric", month: "short", year: "2-digit" }) : "—";
    case "change": return <Fig v={r.change} />;
    case "r1m": case "r6m": case "r1y": case "r3y": case "r5y": return <Fig v={r[c.id]} why={why || "Not enough NAV history for this period."} />;
    case "vol1y": case "vol3y": return <Fig v={r[c.id]} why={why || "Not enough NAV history for this period."} plain d={2} plus={false} />;
    case "mdd": return <Fig v={r.mdd} why={why || "Not enough NAV history."} d={2} />;
  }
}

export function FundTable({ rows, cols, q, onSort, picked, onPick }: { rows: FundRow[]; cols: ColId[]; q: ListQuery; onSort: (s: SortKey) => void; picked: number[]; onPick: (code: number) => void }) {
  const defs = COLUMNS.filter((c) => cols.includes(c.id));
  const sorted = (key: SortKey | null) => (key && q.sort === key ? (q.dir === "asc" ? "ascending" : "descending") : key ? "none" : undefined);
  return (
    <HScroll label="schemes table">
      <table className="mf-table">
        <caption className="sr-only">Mutual fund schemes. Use the column buttons to sort.</caption>
        <thead>
          <tr>
            <th scope="col" aria-sort={sorted("name")}><button className="mf-sort" onClick={() => onSort("name")}>Scheme{q.sort === "name" && <i aria-hidden="true">{q.dir === "asc" ? "▲" : "▼"}</i>}</button></th>
            {defs.map((c) => (
              <th key={c.id} scope="col" aria-sort={sorted(c.sort)} className={c.num ? "num" : "txt"} title={c.hint}>
                {c.sort ? <button className="mf-sort" onClick={() => onSort(c.sort!)}>{c.label}{q.sort === c.sort && <i aria-hidden="true">{q.dir === "asc" ? "▲" : "▼"}</i>}</button> : c.label}
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
                  <small><PlanChip plan={r.plan} option={r.option} />{!r.active && <span className="chip ghost">Stopped publishing</span>}</small>
                </span>
              </th>
              {defs.map((c) => <td key={c.id} className={c.num ? "num" : "txt"}>{cell(c, r)}</td>)}
            </tr>))}
        </tbody>
      </table>
    </HScroll>
  );
}
