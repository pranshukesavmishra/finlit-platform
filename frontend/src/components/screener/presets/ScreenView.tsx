// The screen view: one prebuilt screen as a card (name, card text, match count, as-of date, how it works, its options) with a results table built from the response.
// Values come from the response only: a missing one is a dash, never zero, and nothing is ranked or recommended here.
import { titleOf, subOf, codeNote, exchangeTag, isBseOnly } from "../../../lib/companyLabel";
import { useMemo, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router";
import { ApiError } from "../../../lib/api";
import { Icon } from "../../../lib/icons";
import { cr, dateIN, nf, MINUS } from "../../../lib/format";
import { useUI } from "../../../lib/ui";
import { HScroll } from "../../HScroll";
import {
  DISCLAIMER, PAGE_SIZE, PLAN_OF, asPct, nextSortState, pageRange, rowsForTheme, sortPresetRows, usePresetDetail,
  type ColFormat, type PresetColumn, type PresetDetail, type PresetRow, type SortState, type Theme,
} from "../../../lib/presets";
import type { PresetRoute } from "./usePresetRoute";
import "../../../styles/presets.css";

const STATE_WORD: Record<Theme["state"], string> = { in_play: "In play", emerging: "Emerging", fading: "Fading", closest: "Closest to qualifying" };
const signed = (v: number, d = 1) => (v > 0 ? "+" : v < 0 ? MINUS : "") + nf(Math.abs(v), d);
const BADGE_TONE: Record<string, string> = { "prism-confirmed": "good", provisional: "warn", "loss-making": "warn", "closest to qualifying": "info", "trend not confirmed": "warn", "not rated by prism": "plain" };
export const Badge = ({ text }: { text: string }) => <span className={"psx-b psx-b-" + (BADGE_TONE[text.trim().toLowerCase()] ?? "plain")}>{text}</span>;

/** One table cell in its column's format. A missing value is a dash. */
export function CellValue({ v, f }: { v: unknown; f: ColFormat }) {
  if (v == null || v === "") return <span className="psx-dash" aria-label="not available" title="not available">{MINUS}</span>;
  if (f === "badge") return <>{(Array.isArray(v) ? v : [v]).map((b) => <Badge key={String(b)} text={String(b)} />)}</>;
  if (typeof v !== "number") return <>{String(v)}</>;
  if (f === "pct") return <>{signed(v)}%</>;
  if (f === "num1") return <>{v < 0 ? MINUS : ""}{nf(Math.abs(v), 1)}</>;
  if (f === "score") return <>{v < 0 ? MINUS : ""}{nf(Math.abs(Math.round(v)), 0)}</>;
  if (f === "cr") return <>{cr(v)}</>;
  return <>{String(v)}</>;
}

const alignOf = (c: PresetColumn) => c.align ?? (c.format === "text" || c.format === "label" || c.format === "badge" ? "left" : "right");

function ThemeCards({ themes, on, onPick }: { themes: Theme[]; on: string | null; onPick: (industry: string) => void }) {
  return (
    <div className="psx-themes" role="group" aria-label="Themes. Choose one to show only its leaders.">
      {themes.map((t) => {
        const breadth = asPct(t.breadth), market = asPct(t.marketBreadth ?? null), pressed = on === t.industry;
        return (
          <button key={t.industry} type="button" className={"psx-th" + (pressed ? " is-on" : "")} aria-pressed={pressed} onClick={() => onPick(t.industry)}>
            <span className="psx-thh"><b>{t.industry}</b><span className={"psx-st psx-st-" + t.state}>{STATE_WORD[t.state] ?? t.state}</span></span>
            <span className="psx-thm">
              <span title="Share of the sector's companies within 15% of their 52-week high"><small>Near the high</small><b>{breadth == null ? MINUS : nf(breadth, 0) + "%"}</b>{market != null && <small>market {nf(market, 0)}%</small>}</span>
              <span title="3-month return of the sector against the market, in percentage points"><small>3M vs market</small><b>{t.rs3 == null ? MINUS : signed(t.rs3) + " pts"}</b></span>
              <span><small>Members</small><b>{t.members == null ? MINUS : nf(t.members, 0)}</b></span>
            </span>
            {t.reason && <span className="psx-thr">{t.reason}</span>}
          </button>);
      })}
    </div>);
}

function Results({ d, cols, rows, sort, setSort }: { d: PresetDetail; cols: PresetColumn[]; rows: PresetRow[]; sort: SortState; setSort: (k: string, first: 1 | -1) => void }) {
  const first = d.offset ?? 0;
  const head = (key: string, label: string, align: string, first: 1 | -1 = -1) => (
    <th scope="col" className={"psx-a-" + align} aria-sort={sort?.key === key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
      <button type="button" onClick={() => setSort(key, first)} aria-label={`Sort by ${label}`}>{label} <span aria-hidden="true">{sort?.key === key ? (sort.dir > 0 ? "▲" : "▼") : "▾"}</span></button></th>);
  return (
    <HScroll className="scr-tw" label="results table"><table className="scr-t psx-t">
      <caption className="sr">{d.name}: {rows.length} {rows.length === 1 ? "company" : "companies"} shown{d.offset ? `, from number ${first + 1}` : ""}. Select a column heading to sort the shown rows.</caption>
      <thead><tr><th scope="col" className="psx-n">#</th>{head("symbol", "Stock", "left", 1)}{cols.map((c) => <Head key={c.key} c={c} h={head} />)}</tr></thead>
      <tbody>{rows.map((r, i) => (
        <tr key={r.symbol}>
          <td className="psx-n">{first + i + 1}</td>
          <td className="stick psx-stock"><Link to={`/stocks/${encodeURIComponent(r.symbol)}`} className="psx-co"><b title={codeNote(r)}>{titleOf(r)}</b>{subOf(r) && <small>{subOf(r)}</small>}{exchangeTag(r) && <small className="psx-ex">{exchangeTag(r)}</small>}</Link>
            {!!r.badges?.length && <span className="psx-bs">{r.badges.map((b) => <Badge key={b} text={b} />)}</span>}</td>
          {cols.map((c) => <td key={c.key} className={"psx-a-" + alignOf(c)}><CellValue v={r[c.key]} f={c.format} /></td>)}
        </tr>))}
      </tbody>
    </table></HScroll>);
}
const Head = ({ c, h }: { c: PresetColumn; h: (key: string, label: string, align: string, first?: 1 | -1) => ReactNode }) => <>{h(c.key, c.label, alignOf(c), c.format === "text" || c.format === "label" ? 1 : -1)}</>;

/** Previous / next 25 of a long screen, with where the page stands ("26–50 of 76"). Plain buttons, so the keyboard reaches them; the position is announced when it changes. */
function Pager({ d, range, busy, hidden, goTo }: { d: PresetDetail; range: { from: number; to: number; of: number }; busy: boolean; hidden: number; goTo: (offset: number) => void }) {
  const size = d.pageSize ?? PAGE_SIZE, off = d.offset ?? 0, left = Math.max(0, (d.available ?? d.count) - (off + d.shown));
  return (
    <nav className="psx-pager" aria-label="Pages of this screen">
      <p className="psx-pg-t" role="status" aria-live="polite">Showing <b>{nf(range.from, 0)}{"–"}{nf(range.to, 0)}</b> of <b>{nf(range.of, 0)}</b>{hidden > 0 && <small> ({hidden} listed only on the BSE hidden on this page)</small>}</p>
      <div className="psx-pg-b">
        <button type="button" className="btn" disabled={off <= 0 || busy} onClick={() => goTo(off - size)}>Previous {size}</button>
        <button type="button" className="btn primary" disabled={!d.hasMore || busy} onClick={() => goTo(off + size)}>Show next {Math.min(size, left) || size}</button>
      </div>
    </nav>);
}

function Misses({ d }: { d: PresetDetail }) {
  const list = (d.closestMisses ?? []).slice(0, 5);
  return (
    <div className="psx-empty">
      <p className="psx-eh" role="status">{d.emptyText || "No company meets every rule today."}</p>
      {list.length > 0 && <>
        <h3>The {list.length === 1 ? "company" : `${list.length} companies`} closest to qualifying</h3>
        <ol className="psx-miss">{list.map((m) => (
          <li key={m.symbol}><span className="psx-mh"><Link to={`/stocks/${encodeURIComponent(m.symbol)}`}><b title={codeNote(m)}>{titleOf(m)}</b></Link>{subOf(m) && <small>{subOf(m)}</small>}{exchangeTag(m) && <small className="psx-ex">{exchangeTag(m)}</small>}<Badge text="Closest to qualifying" /></span>
            <span className="psx-mr">{m.failed.length > 1 ? "Rules missed" : "Rule missed"}: {m.failed.join("; ")}</span></li>))}
        </ol></>}
    </div>);
}

function Frame({ route, name, cardText, children, actions, meta }: { route: PresetRoute; name: string; cardText?: string; children: ReactNode; actions?: ReactNode; meta?: ReactNode }) {
  return (
    <section className="psx-screen card" aria-label={`Prebuilt screen: ${name}`}>
      <header className="psx-top">
        <div className="psx-tt"><span className="psx-eyebrow">Prebuilt screen</span><h2>{name}</h2>{cardText && <p className="psx-card-text">{cardText}</p>}{meta}</div>
        <div className="psx-act">{actions}<button type="button" className="btn" onClick={route.clear}>Clear screen</button></div>
      </header>
      {children}
    </section>);
}
const Disclaimer = ({ text }: { text?: string }) => <p className="psx-disc" role="note">{text || DISCLAIMER}</p>;

/** The screen named in the address. `route` is the shared route state (list, chips, choose, clear). */
export function ScreenView({ route }: { route: PresetRoute }) {
  const { id, preset, chips, list } = route;
  const { upgrade } = useUI();
  const plan = PLAN_OF[route.tab], planName = plan === "gold" ? "Gold" : "Silver";
  const listReady = list.isSuccess || list.isError;
  const unknown = list.isSuccess && !preset;
  const blocked = preset?.status === "blocked", lockedList = !!preset?.locked;
  const pageKey = `${id}|${[...chips].sort().join(",")}`;
  const [pg, setPg] = useState({ key: "", offset: 0 });
  const offset = pg.key === pageKey ? pg.offset : 0;                      // a new screen or a new option starts at the first 25
  const q = usePresetDetail(id, chips, listReady && !unknown && !blocked && !lockedList, offset);
  const d = q.data, err = q.error;
  const top = useRef<HTMLDivElement>(null);
  const [theme, setTheme] = useState<string | null>(null), [nseOnly, setNseOnly] = useState(false), [sort, setSortState] = useState<SortState>(null);
  const setSort = (k: string, first: 1 | -1) => setSortState((s) => nextSortState(s, k, first));
  const goTo = (o: number) => { setPg({ key: pageKey, offset: Math.max(0, o) }); window.setTimeout(() => top.current?.scrollIntoView?.({ block: "start" }), 0); };
  const themes = d?.themes ?? [];
  const activeTheme = themes.find((t) => t.industry === theme) ?? null;
  const cols = useMemo(() => (d?.columns ?? []).filter((c) => !["symbol", "name", "stock", "badges"].includes(c.key)), [d]);
  const bseCount = useMemo(() => (d?.rows ?? []).filter(isBseOnly).length, [d]);
  const rows = useMemo(() => sortPresetRows(rowsForTheme(d?.rows ?? [], activeTheme), sort).filter((r) => !nseOnly || !isBseOnly(r)), [d, activeTheme, sort, nseOnly]);
  const name = d?.name ?? preset?.name ?? id ?? "";

  if (unknown) return (
    <section className="psx-screen card" aria-label="Prebuilt screen not found"><div className="psx-state"><h2>We could not find that screen</h2><p>There is no prebuilt screen called “{id}”. It may have been renamed or removed. Pick one from the list, or go back to the filters.</p>
      <button type="button" className="btn primary" onClick={route.clear}>Clear screen</button></div></section>);
  if (preset && blocked) return (
    <Frame route={route} name={preset.name} cardText={preset.cardText}><div className="psx-state"><h2>Coming soon</h2><p>{preset.blockedReason || "Coming soon: this screen needs data we do not hold yet."}</p></div><Disclaimer /></Frame>);
  if (lockedList || (err instanceof ApiError && err.status === 403)) return (
    <Frame route={route} name={name} cardText={preset?.cardText}><div className="psx-state psx-lock"><h2><Icon name="lock" /> This screen is part of {planName}</h2><p>{preset?.cardText ?? "Prebuilt screens narrow the whole market with ready-made rules."} Upgrade to see which companies it finds today.</p>
      <button type="button" className="btn primary" onClick={() => upgrade(plan, `Prebuilt screens on this page are part of ${planName}.`)}>Unlock with {planName} <Icon name="arrow" /></button></div><Disclaimer /></Frame>);
  if (err instanceof ApiError && err.status === 404) return (
    <section className="psx-screen card" aria-label="Prebuilt screen not found"><div className="psx-state"><h2>We could not find that screen</h2><p>There is no prebuilt screen called “{id}”. Pick one from the list, or go back to the filters.</p>
      <button type="button" className="btn primary" onClick={route.clear}>Clear screen</button></div></section>);
  if (err && !d) return (
    <Frame route={route} name={name} cardText={preset?.cardText}><div className="psx-state" role="alert"><h2>This screen is unavailable right now</h2><p>Please try again in a moment.</p>
      <button type="button" className="btn" onClick={() => q.refetch()}>Try again</button></div><Disclaimer /></Frame>);

  const paged = !!d && d.pageSize != null && d.count > d.pageSize;      // more rows than one page: the pager shows, and the CSV holds all of them
  const range = d ? pageRange(d) : null;
  const meta = d ? (
    <p className="psx-meta"><b>{d.listText || `${nf(d.count, 0)} match`}</b>{!d.listText && !paged && d.shown !== d.count && <span>showing {nf(d.shown, 0)}</span>}{paged && range && <span>showing {nf(range.from, 0)}{"–"}{nf(range.to, 0)}</span>}{d.asOf && <span>as of {dateIN(d.asOf)}</span>}</p>
  ) : preset ? <p className="psx-meta">{preset.count != null && <b>{preset.listText || `${nf(preset.count, 0)} match`}</b>}{preset.asOf && <span>as of {dateIN(preset.asOf)}</span>}</p> : null;
  const how = d?.howItWorks?.length ? d.howItWorks : preset?.howItWorks ?? [];
  return (
    <Frame route={route} name={name} cardText={d?.cardText ?? preset?.cardText} meta={meta}>
      {how.length > 0 && <details className="psx-how"><summary>How this screen works</summary><ul>{how.map((h) => <li key={h}>{h}</li>)}</ul></details>}
      {!!preset?.chips.length && (
        <div className="psx-chips" role="group" aria-label="Screen options">
          {preset.chips.map((c) => {
            const on = chips.includes(c.id), did = `psx-cd-${c.id}`;
            return (
              <div key={c.id} className="psx-chipw">
                <button type="button" className={"fgx-chip psx-chip" + (on ? " is-on" : "")} aria-pressed={on} aria-describedby={did} onClick={() => route.toggleChip(c.id)}>{on && <i aria-hidden="true">&#10003;</i>}{c.label}</button>
                {c.description && <small id={did}>{c.description}</small>}
              </div>);
          })}
        </div>)}
      {bseCount > 0 && (
        <div className="psx-chips" role="group" aria-label="Exchange">
          <div className="psx-chipw">
            <button type="button" className={"fgx-chip psx-chip" + (nseOnly ? " is-on" : "")} aria-pressed={nseOnly} aria-describedby="psx-cd-nse" onClick={() => setNseOnly((v) => !v)}>{nseOnly && <i aria-hidden="true">&#10003;</i>}NSE-listed only</button>
            <small id="psx-cd-nse">Leaves out the {bseCount} {bseCount === 1 ? "company" : "companies"} listed only on the BSE.</small>
          </div>
        </div>)}
      {!!d?.notes?.length && <div className="psx-notes" role="note">{d.notes.map((n) => <p key={n}>{n}</p>)}</div>}
      {themes.length > 0 && <ThemeCards themes={themes} on={theme} onPick={(i) => setTheme((t) => (t === i ? null : i))} />}
      <div ref={top} className={"psx-res" + (q.isFetching && d ? " is-busy" : "")} aria-busy={q.isFetching}>
        {!d ? <div className="skeleton" style={{ height: 300 }} role="status" aria-label="Loading the screen" />
          : d.count === 0 || (!d.rows.length) ? <Misses d={d} />
          : <>
            {activeTheme && <p className="psx-filt" role="status">Showing the leaders of {activeTheme.industry}. <button type="button" className="fgx-link" onClick={() => setTheme(null)}>Show all</button></p>}
            <p className="sr" role="status" aria-live="polite">{rows.length} {rows.length === 1 ? "company" : "companies"} shown.</p>
            {rows.length ? <Results d={d} cols={cols} rows={rows} sort={sort} setSort={setSort} /> : <p className="psx-filt">{nseOnly ? "Every company shown for this screen is listed only on the BSE. Switch off NSE-listed only to see them." : "No leaders are listed for this theme today."}</p>}
            {paged && range && <Pager d={d} range={range} busy={q.isFetching} hidden={nseOnly ? bseCount : 0} goTo={goTo} />}
          </>}
      </div>
      {d?.rankScoreNote && !!d.rows.length && <p className="psx-notes" role="note">{d.rankScoreNote}</p>}
      <Disclaimer text={d?.disclaimer} />
    </Frame>);
}
