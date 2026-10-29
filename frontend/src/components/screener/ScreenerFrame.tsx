// The page frame both score screeners share: header, filter sidebar (quick views, size, sector, then the page's own filters), summary tiles, active-filter
// chips, sector mix, the results table with selection, compare, watchlist and CSV, and the pager. The page supplies the model-specific parts.
import { type ReactNode } from "react";
import { Link } from "react-router";
import { HScroll } from "../HScroll";
import { SplitDivider, useSideWidth } from "../SplitDivider";
import { PageArt } from "../PageArt";
import { Plain } from "../Plain";
import { ChartHelp } from "../ChartHelp";
import { Icon } from "../../lib/icons";
import { cr, nf } from "../../lib/format";
import { watch } from "../../lib/watchlist";
import { CAPS, PAGE_SIZES, pageList, type SortKey } from "../../lib/scoreScreen";
import { Dash } from "./cells";
import type { Screener } from "./useScreener";

export type Tile = [label: string, value: string, why?: string];

export function SortTh({ s, k, label, cls = "", help, title }: { s: Screener; k: SortKey; label: string; cls?: string; help?: string; title?: string }) {
  const { sort } = s;
  return (
    <th scope="col" className={cls} title={title} aria-sort={sort.key === k ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
      <button type="button" onClick={() => s.sortBy(k)} aria-label={`Sort by ${label}`}>{label} <span aria-hidden="true">{sort.key === k ? (sort.dir > 0 ? "▲" : "▼") : "▾"}</span></button>{help && <ChartHelp id={help} />}
    </th>);
}

type Props = {
  s: Screener; splitKey: string; eyebrow: string; title: string; intro: ReactNode; sideLabel: string;
  /** Quick views at the top of the sidebar. */ presets: ReactNode;
  /** The page's own filters, after Market cap and Sector. */ filters: ReactNode;
  tiles: Tile[]; lead?: ReactNode; beforeTable?: ReactNode; errorTitle: string;
  groupHead: ReactNode; columnHeads: ReactNode; cells: (r: Screener["pg"]["view"][number]) => ReactNode; colSpan: number;
  plain: string; how: ReactNode;
};
export function ScreenerFrame({ s, splitKey, eyebrow, title, intro, sideLabel, presets, filters, tiles, lead, beforeTable, errorTitle, groupHead, columnHeads, cells, colSpan, plain, how }: Props) {
  const [sideW, setSide] = useSideWidth(splitKey);
  const { draft, setDraft, facets, secQ, setSecQ, drawer, setDrawer, sort, size, pg, rows, sel, bad, dirty, isLoading, isError, chips, mix, filterCount, maxCompare } = s;
  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.6 }} /><div className="wrap"><PageArt kind="research" />
        <div className="eyebrow">{eyebrow}</div><h1>{title}</h1>
        <p>{intro}</p></div></section>
      <div className="wrap scr-wrap">
        <div className={"scr sx" + (drawer ? " sx-open" : "")} style={{ "--side-w": `${sideW}px` } as React.CSSProperties}>
          {drawer && <div className="sx-back" onClick={() => setDrawer(false)} aria-hidden="true" />}
          <aside className="scr-side card sx-side" aria-label={sideLabel} hidden={sideW === 0}>
            <button type="button" className="sx-close btn" onClick={() => setDrawer(false)}>Close filters</button>
            <form onSubmit={(e) => { e.preventDefault(); s.apply(); }} noValidate>
              {presets}
              <div className="label" style={{ marginTop: 18 }}>Market cap</div>
              <div className="sx-opts" role="group" aria-label="Market cap size">
                {CAPS.map((c) => <label key={c} className={"sx-opt" + (draft.caps.includes(c) ? " on" : "")}><input type="checkbox" checked={draft.caps.includes(c)} onChange={() => setDraft((d) => ({ ...d, caps: s.toggle(d.caps, c) }))} /><span>{c} cap</span><small>{facets.caps[c]}</small></label>)}
              </div>
              <div className="label" style={{ marginTop: 18, display: "flex", justifyContent: "space-between" }}>Industry / sector{draft.sectors.length > 0 && <button type="button" className="alx-link" onClick={() => setDraft((d) => ({ ...d, sectors: [] }))}>Clear {draft.sectors.length}</button>}</div>
              <label className="scr-find sm"><Icon name="table" /><input value={secQ} onChange={(e) => setSecQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && e.preventDefault()} placeholder="Search sectors" aria-label="Search sectors" type="search" /></label>
              <ul className="scr-sec" aria-label="Sectors">
                {facets.sectors.filter(([x]) => x.toLowerCase().includes(secQ.trim().toLowerCase())).map(([x, n]) => (
                  <li key={x}><label><input type="checkbox" checked={draft.sectors.includes(x)} onChange={() => setDraft((d) => ({ ...d, sectors: s.toggle(d.sectors, x) }))} /><span>{x}</span><small className="faint" style={{ marginLeft: "auto" }}>{n}</small></label></li>))}
                {!facets.sectors.length && !isLoading && <li className="faint">No sectors loaded yet.</li>}
                {!!facets.sectors.length && !facets.sectors.some(([x]) => x.toLowerCase().includes(secQ.trim().toLowerCase())) && <li className="faint">No sector matches “{secQ}”.</li>}
              </ul>
              {filters}
              <div className="sx-hint" role="status" aria-live="polite">{bad ? "Fix the highlighted ranges to apply." : dirty ? "Unsaved changes. Press Apply filters (or Enter) to update the table." : ""}</div>
              <div className="ss-actions"><button type="submit" className="btn primary" disabled={bad}>Apply filters</button><button type="button" className="btn" onClick={s.clear}>Clear all</button></div>
            </form>
          </aside>
          <SplitDivider width={sideW} set={setSide} />

          <section className="scr-main card" aria-label="Results">
            <div className="sx-top">
              <button type="button" className="btn sx-fbtn" onClick={() => setDrawer(true)} aria-haspopup="dialog">Filters{filterCount > 0 && <span className="dotn">{filterCount}</span>}{dirty && <span className="sr"> (unsaved changes)</span>}</button>
              <button type="button" className="btn" onClick={() => s.setHow(true)}><Icon name="info" /> How scores work</button>
            </div>
            {lead}
            <div className="ss-stats sx-stats" aria-label="Summary">
              {tiles.map(([l, v, why]) => <div key={l} className="ss-stat" title={why}><b>{v}</b><small>{l}</small></div>)}
            </div>
            {beforeTable}
            {chips.length > 0 && <div className="scr-chips" aria-label="Active filters">{chips.map((c) => <button type="button" key={c.id} className="fchip" onClick={() => s.drop(c.id)} aria-label={`Remove filter ${c.label}`}>{c.label}<span aria-hidden="true">×</span></button>)}<button type="button" className="alx-link" onClick={s.clear}>Clear all</button></div>}
            {mix.length > 0 && (
              <div className="sx-mix" aria-label="Sector mix of the result">
                <div className="sx-bar" aria-hidden="true">{mix.map((m, i) => <i key={m.label} className={"sx-c" + i} style={{ width: m.pct + "%" }} />)}</div>
                <ul>{mix.map((m, i) => <li key={m.label}><i className={"sx-c" + i} aria-hidden="true" />{m.label} <b>{nf(m.n, 0)}</b> <small>{nf(m.pct, 0)}%</small></li>)}</ul>
              </div>)}
            {isError ? <div className="state"><h2>{errorTitle}</h2><p>Please try again in a moment.</p></div> : isLoading ? <div className="skeleton" style={{ height: 380 }} /> : (
              <>
                <div className="sx-bulk" role="toolbar" aria-label="Actions for the table">
                  <span aria-live="polite">{sel.length ? `${nf(sel.length, 0)} selected` : `${nf(rows.length, 0)} ${rows.length === 1 ? "company" : "companies"} in this result`}</span>
                  <span className="sx-bulkb">
                    <button type="button" className="btn primary" disabled={sel.length < 2 || sel.length > maxCompare} onClick={() => s.nav(`/compare?c=${sel.join(",")}`)}
                      title={sel.length > maxCompare ? `Your plan compares up to ${maxCompare} companies` : "Select 2 to " + maxCompare + " companies"}>{sel.length >= 2 && sel.length <= maxCompare ? `Compare ${sel.length}` : "Compare"}</button>
                    <button type="button" className="btn" disabled={!sel.length} onClick={s.addSelected}>Add to watchlist</button>
                    <button type="button" className="btn" disabled={!sel.length} onClick={() => s.exportCsv("selected")}>Export selected</button>
                    <button type="button" className="btn" disabled={!rows.length} onClick={() => s.exportCsv("filtered")}>Export all {nf(rows.length, 0)}</button>
                    {sel.length > 0 && <button type="button" className="alx-link" onClick={() => s.setPicked([])}>Clear selection</button>}
                  </span>
                  {sel.length > maxCompare && <small className="muted">{s.has("gold") ? "Compare takes up to 4 companies." : "Your plan compares up to 2 companies; Gold compares 4."}</small>}
                </div>
                <HScroll className="scr-tw" label="results table"><table className="scr-t ss-t sx-t">
                  <caption className="sr">Companies matching the filters, {sort.key === "name" ? "sorted by name" : "sorted by " + sort.key}. Select a column heading to sort.</caption>
                  <thead>{groupHead}
                  <tr>
                    <th scope="col"><input ref={s.headBox} type="checkbox" checked={s.allOnPage} onChange={s.toggleAll} aria-label="Select all companies on this page" disabled={!pg.view.length} /></th>
                    <th scope="col" className="sx-n">#</th>
                    <SortTh s={s} k="name" label="Stock" cls="stick" /><SortTh s={s} k="price" label="LTP (₹)" /><SortTh s={s} k="market_cap" label="Market cap" /><SortTh s={s} k="sector" label="Sector" />
                    {columnHeads}
                    <th scope="col">Action</th></tr></thead>
                  <tbody>{pg.view.map((r, i) => {
                    const on = sel.includes(r.symbol);
                    return (
                    <tr key={r.symbol} className={on ? "sx-sel" : ""}>
                      <td><input type="checkbox" checked={on} onChange={() => s.togglePick(r.symbol)} aria-label={`Select ${r.symbol}`} /></td>
                      <td className="sx-n">{pg.page * size + i + 1}</td>
                      <td className="stick"><Link to={`/stocks/${r.symbol}`} className="co"><span className="av mini" aria-hidden="true">{(r.name || r.symbol).slice(0, 2).toUpperCase()}</span><span><b>{r.symbol}</b><small>{r.name}</small></span></Link></td>
                      <td>{r.price != null ? nf(r.price) : <Dash why="no price yet" />}</td>
                      <td>{r.market_cap != null ? <>{cr(r.market_cap)}{r.cap && <small className="sx-cap">{r.cap} cap</small>}</> : <Dash why="market value not available" />}</td>
                      <td style={{ fontFamily: "var(--sans)", textAlign: "left" }}>{r.sector || <Dash why="sector not listed" />}</td>
                      {cells(r)}
                      <td className="ss-act"><Link className="btn" to={`/stocks/${r.symbol}`} aria-label={`Open ${r.symbol} report`}>Report</Link>
                        <button type="button" className={"btn" + (watch.has(r.symbol) ? " on" : "")} aria-pressed={watch.has(r.symbol)} aria-label={`${watch.has(r.symbol) ? "Remove" : "Add"} ${r.symbol} ${watch.has(r.symbol) ? "from" : "to"} watchlist`} onClick={() => s.addWatch(r.symbol)}><Icon name="wallet" /></button></td>
                    </tr>);
                  })}
                    {!rows.length && <tr><td colSpan={colSpan} className="empty">No companies match all of these filters. Try loosening one, or clear them all.</td></tr>}
                  </tbody>
                </table></HScroll>
                <div className="ss-foot">
                  <label className="muted">Rows per page <select value={size} onChange={(e) => s.go({ size: Number(e.target.value), page: 0 })} aria-label="Rows per page">{PAGE_SIZES.map((n) => <option key={n} value={n}>{n}</option>)}</select></label>
                  <span className="muted" aria-live="polite">{pg.from}–{pg.to} of {nf(rows.length, 0)}</span>
                  <nav className="sx-pager" aria-label="Pages">
                    <button type="button" className="btn" disabled={pg.page <= 0} onClick={() => s.go({ page: pg.page - 1 })} aria-label="Previous page">‹</button>
                    {pageList(pg.page, pg.pages).map((n, i) => n == null ? <span key={"g" + i} aria-hidden="true">…</span> :
                      <button type="button" key={n} className={"btn" + (n === pg.page ? " on" : "")} aria-current={n === pg.page ? "page" : undefined} aria-label={`Page ${n + 1}`} onClick={() => s.go({ page: n })}>{n + 1}</button>)}
                    <button type="button" className="btn" disabled={pg.page >= pg.pages - 1} onClick={() => s.go({ page: pg.page + 1 })} aria-label="Next page">›</button>
                  </nav>
                </div>
              </>
            )}
            <Plain>{plain}</Plain>
          </section>
        </div>
      </div>
      {s.how && how}
    </>
  );
}
