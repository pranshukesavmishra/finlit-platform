// Option chain (Gold): calls on the left, strike in the centre, puts on the right, for an index or an F&O stock and one expiry, from Dhan via
// /api/options. All figures are worked out on the server (backend/finlit/options.py, definitions below); this page only lays them out.
// Information and education only: no signals, no views on direction, no targets.
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet, type ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { DEMO } from "../lib/demo";
import { Icon } from "../lib/icons";
import { useUI } from "../lib/ui";
import { useDocTitle } from "../lib/title";
import { nf } from "../lib/format";
import { Gate } from "../components/Gate";
import {
  BUILDUP, age, around, compact, count, istTime, matchUnderlyings, price, signedNum, strikeText, ticks,
  type Chain, type Expiries, type Row, type Side, type Underlyings, type Unit,
} from "../lib/options";
import "../styles/options.css";

type Pick = { key: string; name: string; kind: "index" | "stock" };

function Picker({ list, value, onPick }: { list: Pick[]; value: Pick | null; onPick: (p: Pick) => void }) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const hits = useMemo(() => matchUnderlyings(list, q), [list, q]);
  return (
    <div className="oc-pick">
      <label className="oc-lab" htmlFor="oc-u">Underlying</label>
      <div className="oc-search"><Icon name="search" />
        <input id="oc-u" type="search" role="combobox" aria-expanded={open} aria-controls="oc-hits" autoComplete="off" spellCheck={false} maxLength={30}
          value={open ? q : value ? `${value.name} (${value.key})` : q} placeholder="Search an index or F&O stock"
          onFocus={() => { setOpen(true); setQ(""); }} onBlur={() => window.setTimeout(() => setOpen(false), 150)} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && hits[0]) { e.preventDefault(); onPick(hits[0]); setOpen(false); (e.target as HTMLInputElement).blur(); } if (e.key === "Escape") (e.target as HTMLInputElement).blur(); }} /></div>
      {open && (
        <ul id="oc-hits" className="oc-hits" role="listbox" aria-label="Matching underlyings">
          {hits.map((h) => <li key={h.key} role="option" aria-selected={value?.key === h.key}>
            <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => { onPick(h); setOpen(false); }}>
              <b>{h.name}</b><span className="mono faint">{h.key}{h.kind === "index" ? " · index" : ""}</span></button></li>)}
          {hits.length === 0 && <li className="faint oc-none">No index or F&amp;O stock matches “{q.trim()}”.</li>}
        </ul>)}
    </div>
  );
}

const Stat = ({ k, v, sub, wide }: { k: string; v: string; sub?: string; wide?: boolean }) =>
  <div className={"oc-stat" + (wide ? " wide" : "")}><span>{k}</span><b>{v}</b>{sub && <small>{sub}</small>}</div>;

function Cells({ s, unit, lot, itm }: { s: Side | null; unit: Unit; lot: number | null; itm: boolean }) {
  const cls = itm ? " itm" : "";
  if (!s) return <>{[0, 1, 2, 3, 4, 5].map((i) => <td key={i} className={"num faint" + cls}>—</td>)}</>;
  const b = s.buildup ? BUILDUP[s.buildup] : null;
  return (
    <>
      <td className={"num" + cls}>{count(s.oi, unit, lot)}</td>
      <td className={"num" + cls}>{count(s.oiChange, unit, lot, true)}{s.oiChangePct != null && <small className="oc-sub">{signedNum(s.oiChangePct, 1)}%</small>}
        {b && <small className={"oc-bu " + s.buildup} title={`${b.label}: ${b.how}`}>{b.tag}</small>}</td>
      <td className={"num" + cls}>{count(s.volume, unit, lot)}</td>
      <td className={"num" + cls}>{s.iv == null ? "—" : nf(s.iv, 2)}</td>
      <td className={"num" + cls}>{price(s.ltp)}</td>
      <td className={"num" + cls}>{signedNum(s.change)}{s.changePct != null && <small className="oc-sub">{signedNum(s.changePct, 1)}%</small>}</td>
    </>
  );
}

const HEAD = ["OI", "OI chg", "Volume", "IV %", "LTP", "Chg"];

function ChainTable({ rows, unit, lot }: { rows: Row[]; unit: Unit; lot: number | null }) {
  return (
    <div className="oc-scroll" tabIndex={0} role="region" aria-label="Option chain table, scrolls sideways">
      <table className="oc-table">
        <caption className="sr-only">Calls on the left, strike in the centre, puts on the right</caption>
        <thead>
          <tr className="grp"><th colSpan={6} scope="colgroup">Calls</th><th scope="col" rowSpan={2}>Strike</th><th colSpan={6} scope="colgroup">Puts</th></tr>
          <tr>{HEAD.map((h) => <th key={"c" + h} scope="col">{h}</th>)}{HEAD.map((h) => <th key={"p" + h} scope="col">{h}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.strike} className={r.atm ? "atm" : undefined} aria-label={r.atm ? "At-the-money strike" : undefined}>
              <Cells s={r.ce} unit={unit} lot={lot} itm={r.ceItm} />
              <th scope="row" className="oc-k">{strikeText(r.strike)}{r.atm && <small>ATM</small>}</th>
              <Cells s={r.pe} unit={unit} lot={lot} itm={r.peItm} />
            </tr>))}
        </tbody>
      </table>
    </div>
  );
}

/** Calls and puts open interest side by side at each strike. Two series, so a legend; bars are 2px apart, rounded at the top. */
function OiChart({ rows, spot, atm, unit, lot }: { rows: Row[]; spot: number | null; atm: number | null; unit: Unit; lot: number | null }) {
  const [hover, setHover] = useState<number | null>(null);
  const conv = (v: number | null) => (v == null ? 0 : unit === "lots" && lot ? v / lot : v);
  const max = Math.max(1, ...rows.flatMap((r) => [conv(r.ce?.oi ?? null), conv(r.pe?.oi ?? null)]));
  const ts = ticks(0, max, 4), top = ts[ts.length - 1] || 1;
  const W = Math.max(320, rows.length * 22 + 64), H = 240, L = 52, B = 34, T = 10, ph = H - B - T, slot = (W - L - 6) / Math.max(1, rows.length);
  const bw = Math.max(3, Math.min(12, slot / 2 - 2));
  const y = (v: number) => T + ph - (v / top) * ph;
  const h = hover != null ? rows[hover] : null;
  const fmt = (v: number | null) => count(v, unit, lot);
  const every = Math.ceil(rows.length / Math.max(1, Math.floor((W - L) / 54)));
  const table = rows.filter((r) => r.ce?.oi != null || r.pe?.oi != null);
  return (
    <section className="card oc-chart" aria-labelledby="oc-chart-h">
      <h2 id="oc-chart-h">Open interest by strike <span className="faint">{unit === "lots" ? "lots" : "units"}</span></h2>
      <div className="oc-legend" aria-hidden="true"><span><i className="ce" />Calls</span><span><i className="pe" />Puts</span>
        {spot != null && <span><i className="spot" />Underlying {strikeText(spot)}</span>}</div>
      <div className="oc-svgwrap">
        <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} role="img" aria-label={`Bar chart of call and put open interest across ${rows.length} strikes. The same numbers are in the table below.`}
          onMouseLeave={() => setHover(null)}>
          {ts.map((t) => <g key={t}><line x1={L} x2={W} y1={y(t)} y2={y(t)} className="grid" /><text x={L - 6} y={y(t) + 4} textAnchor="end" className="axis">{compact(t)}</text></g>)}
          {rows.map((r, i) => {
            const x = L + i * slot + slot / 2, c = conv(r.ce?.oi ?? null), p = conv(r.pe?.oi ?? null);
            return (
              <g key={r.strike} onMouseEnter={() => setHover(i)} onFocus={() => setHover(i)}>
                <rect x={L + i * slot} y={T} width={slot} height={ph + B} fill="transparent" />
                {r.atm && <rect x={L + i * slot} y={T} width={slot} height={ph} className="atmband" />}
                {c > 0 && <rect x={x - bw - 1} y={y(c)} width={bw} height={Math.max(1, T + ph - y(c))} rx={Math.min(3, bw / 2)} className="bar ce" />}
                {p > 0 && <rect x={x + 1} y={y(p)} width={bw} height={Math.max(1, T + ph - y(p))} rx={Math.min(3, bw / 2)} className="bar pe" />}
                {i % every === 0 && <text x={x} y={H - 14} textAnchor="middle" className="axis">{strikeText(r.strike)}</text>}
              </g>);
          })}
          <line x1={L} x2={W} y1={T + ph} y2={T + ph} className="base" />
          {spot != null && rows.length > 1 && spot >= rows[0].strike && spot <= rows[rows.length - 1].strike && (() => {
            const j = rows.findIndex((r, i) => i === rows.length - 1 || (spot >= r.strike && spot < rows[i + 1].strike));
            const nx = rows[Math.min(rows.length - 1, j + 1)].strike, f = nx === rows[j].strike ? 0 : (spot - rows[j].strike) / (nx - rows[j].strike);
            const x = L + j * slot + slot / 2 + f * slot;
            return <line x1={x} x2={x} y1={T} y2={T + ph} className="spotline" />;
          })()}
        </svg>
      </div>
      <div className="oc-tip" aria-live="polite">{h
        ? <><b>Strike {strikeText(h.strike)}{h.atm ? " (ATM)" : ""}</b> · Calls OI {fmt(h.ce?.oi ?? null)} · Puts OI {fmt(h.pe?.oi ?? null)}</>
        : <span className="faint">Point at a strike for its open interest.{atm != null ? ` Shaded column: ATM strike ${strikeText(atm)}.` : ""}</span>}</div>
      <details className="oc-tbl"><summary>Show these numbers as a table</summary>
        <table><thead><tr><th scope="col">Strike</th><th scope="col">Calls OI</th><th scope="col">Puts OI</th></tr></thead>
          <tbody>{table.map((r) => <tr key={r.strike}><th scope="row">{strikeText(r.strike)}</th><td className="num">{fmt(r.ce?.oi ?? null)}</td><td className="num">{fmt(r.pe?.oi ?? null)}</td></tr>)}</tbody></table>
      </details>
    </section>
  );
}

export function RiskNote() {
  return (
    <aside className="card oc-risk" role="note" aria-labelledby="oc-risk-h">
      <h2 id="oc-risk-h"><Icon name="alert" /> Before you trade derivatives</h2>
      <p>SEBI’s study of individual traders in equity futures and options, published in September 2024, found that <b>93% of the more than 1 crore individual traders lost money between FY22 and FY24</b>.
        The average loss per loss-making trader was about ₹2 lakh over the three years, after transaction costs, and aggregate losses were over ₹1.8 lakh crore.
        {" "}<span className="faint">Source: SEBI press release, 23 September 2024, “Updated SEBI study reveals 93% of individual traders incurred losses in equity F&amp;O between FY22 and FY24”.</span></p>
      <p>FinLit shows this chain as information and for education. It does not recommend buying or selling any contract, does not say which way a market will move,
        and sets no targets. Open interest, put-call ratio and build-up describe what has already happened in the market; they do not predict what comes next.
        FinLit is not a SEBI-registered research analyst or investment adviser for this tool.</p>
    </aside>
  );
}

function Definitions() {
  return (
    <section className="card oc-defs" aria-labelledby="oc-def-h">
      <h2 id="oc-def-h">How each figure is worked out</h2>
      <dl>
        <dt>Put-call ratio (PCR)</dt><dd>Total put open interest ÷ total call open interest over every strike of this expiry. PCR by volume is the same with the day’s traded volume. It is a ratio of positions, not a forecast.</dd>
        <dt>Max pain</dt><dd>Among the listed strikes, the settlement price at which the total intrinsic value payable to option buyers at expiry, Σ call OI × max(0, price − strike) + Σ put OI × max(0, strike − price), is lowest, using today’s open interest. If two strikes tie, the lower one is shown. It is a calculation on current open interest and changes through the day.</dd>
        <dt>OI change</dt><dd>Open interest now minus the previous day’s open interest; the percentage is shown only when the previous day’s open interest was above zero.</dd>
        <dt>ATM strike</dt><dd>The listed strike nearest the underlying’s last price; exactly midway between two strikes, the higher one.</dd>
        <dt>In the money</dt><dd>Shaded: calls at strikes below the underlying’s price, puts at strikes above it.</dd>
        <dt>OI build-up tags</dt><dd>From the option’s own price change since the previous close and its OI change. LB long build-up: price up, OI up. SB short build-up: price down, OI up. SC short covering: price up, OI down. LU long unwinding: price down, OI down. No tag when either change is zero or unknown. These label past activity only.</dd>
        <dt>Dashes</dt><dd>A dash means Dhan did not send a value (or sent a zero that cannot be a real price or volatility). It never means zero.</dd>
      </dl>
    </section>
  );
}

export function OptionChainPage() {
  useDocTitle("Option chain", "Live option chain for Nifty, Bank Nifty, Sensex and F&O stocks: open interest, OI change, put-call ratio and max pain, for information and education.");
  const { has } = useUI();
  const { user } = useAuth();
  const on = has("gold") && !!user && !DEMO;
  const [u, setU] = useState<Pick>({ key: "NIFTY", name: "Nifty 50", kind: "index" });
  const [expiry, setExpiry] = useState<string>("");
  const [unit, setUnit] = useState<Unit>("units");
  const [span, setSpan] = useState(15);

  const list = useQuery<Underlyings, ApiError>({ queryKey: ["oc-underlyings"], queryFn: () => apiGet("/api/options/underlyings"), enabled: on, staleTime: 3_600_000, retry: false });
  const picks = useMemo<Pick[]>(() => list.data ? [...list.data.indices.map((i) => ({ key: i.key, name: i.name, kind: "index" as const })),
    ...list.data.stocks.map((s) => ({ key: s.key, name: s.name, kind: "stock" as const }))] : [u], [list.data]);   // eslint-disable-line react-hooks/exhaustive-deps
  const exp = useQuery<Expiries, ApiError>({ queryKey: ["oc-expiries", u.key], queryFn: () => apiGet(`/api/options/expiries?u=${encodeURIComponent(u.key)}`),
    enabled: on && list.isSuccess, staleTime: 300_000, retry: (n, e) => e.status === 503 && n < 3, retryDelay: (_, e) => (e.body.retryAfter || 3) * 1000 });
  useEffect(() => { setExpiry(""); }, [u.key]);
  useEffect(() => { if (exp.data && !exp.data.expiries.includes(expiry)) setExpiry(exp.data.expiries[0] ?? ""); }, [exp.data, expiry]);
  const chain = useQuery<Chain, ApiError>({
    queryKey: ["oc-chain", u.key, expiry], queryFn: () => apiGet(`/api/options/chain?u=${encodeURIComponent(u.key)}&expiry=${expiry}`),
    enabled: on && !!expiry && exp.data?.underlying.key === u.key, placeholderData: (p) => (p?.underlying.key === u.key ? p : undefined),
    refetchInterval: (q) => (q.state.data?.marketOpen ? Math.max(30, q.state.data.refreshSeconds) * 1000 : false),
    retry: (n, e) => e.status === 503 && n < 4, retryDelay: (_, e) => (e.body.retryAfter || 3) * 1000,
  });
  const c = chain.data;
  const lot = c?.lotSize ?? null;
  const rows = useMemo(() => (c ? around(c.rows, c.atm, span) : []), [c, span]);
  const err = (chain.error ?? exp.error ?? list.error) as ApiError | null;
  const t = c?.summary.totals;

  return (
    <>
      <section className="pagehead"><div className="wrap"><div className="eyebrow">Gold tool</div><h1>Option chain</h1>
        <p>Every strike of an index or F&amp;O stock for one expiry: open interest, OI change, volume, implied volatility and price, with the put-call ratio and max pain worked out from them. For information and education, not trading advice.</p></div></section>
      <div className="wrap oc">
        <Gate tier="gold" title="Option chain" points={["Nifty, Bank Nifty, Fin Nifty, Midcap Nifty, Sensex and every F&O stock", "Open interest, OI change, volume, IV and price at every strike", "Put-call ratio, max pain and OI build-up, with the working explained", "Open interest by strike chart"]}>
          <section className="card oc-controls" aria-label="Choose a chain">
            <Picker list={picks} value={u} onPick={setU} />
            <div className="oc-ctl"><label className="oc-lab" htmlFor="oc-e">Expiry</label>
              <select id="oc-e" value={expiry} onChange={(e) => setExpiry(e.target.value)} disabled={!exp.data?.expiries.length}>
                {!exp.data && <option value="">Loading…</option>}
                {exp.data?.expiries.map((e) => <option key={e} value={e}>{new Date(e + "T00:00:00").toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", year: "numeric" })}</option>)}
              </select></div>
            <div className="oc-ctl"><label className="oc-lab" htmlFor="oc-s">Strikes shown</label>
              <select id="oc-s" value={span} onChange={(e) => setSpan(Number(e.target.value))}>
                <option value={8}>ATM ± 8</option><option value={15}>ATM ± 15</option><option value={30}>ATM ± 30</option><option value={0}>All strikes</option></select></div>
            <div className="oc-ctl"><span className="oc-lab" id="oc-unit">OI and volume in</span>
              <div className="oc-seg" role="group" aria-labelledby="oc-unit">
                {(["units", "lots"] as Unit[]).map((x) => <button key={x} type="button" className={unit === x ? "on" : ""} aria-pressed={unit === x} disabled={x === "lots" && !lot} onClick={() => setUnit(x)}>{x === "units" ? "Units" : "Lots"}</button>)}</div></div>
          </section>

          {err && !c && (
            <p className="formerr" role="alert">{err.status === 503 && err.body.status === "not_connected" ? "The option chain is not connected to its market-data provider yet."
              : err.status === 503 ? "Many people are reading option chains right now. Retrying…" : (err.body.detail as string) || "The option chain could not be loaded."}</p>)}
          {(chain.isFetching && !c || exp.isFetching && !exp.data) && !err && <p className="muted" role="status">Loading the chain…</p>}
          {err && c && <p className="oc-warn" role="status"><Icon name="info" />The latest refresh failed; showing the last chain received.</p>}

          {c && (<>
            {c.state !== "fresh" && <p className="oc-warn" role="status"><Icon name="info" />This chain is {age(c.ageSeconds)} old (taken {istTime(c.asOf)})
              {c.state === "refreshing" ? "; a newer one is being fetched." : "; Dhan could not be reached for a newer one."}</p>}
            {c.notes.map((n) => <p key={n} className="oc-warn" role="note"><Icon name="info" />{n}</p>)}
            <section className="oc-sum" aria-label="Summary" aria-live="polite">
              <Stat k={`${c.underlying.name} (underlying)`} v={c.spot == null ? "—" : nf(c.spot, 2)} sub={c.atm != null ? `ATM strike ${strikeText(c.atm)}` : undefined} />
              <Stat k="PCR by open interest" v={c.summary.pcrOi == null ? "—" : nf(c.summary.pcrOi, 2)} sub="put OI ÷ call OI" />
              <Stat k="PCR by volume" v={c.summary.pcrVolume == null ? "—" : nf(c.summary.pcrVolume, 2)} sub="put volume ÷ call volume" />
              <Stat k="Max pain" v={c.summary.maxPain ? strikeText(c.summary.maxPain.strike) : "—"} sub="strike with the lowest total payout to option buyers" />
              <Stat k="Total call OI" v={count(t?.ce.oi ?? null, unit, lot)} sub={`change ${count(t?.ce.oiChange ?? null, unit, lot, true)}`} />
              <Stat k="Total put OI" v={count(t?.pe.oi ?? null, unit, lot)} sub={`change ${count(t?.pe.oiChange ?? null, unit, lot, true)}`} />
              <Stat k="Lot size" v={lot ? nf(lot, 0) : "—"} sub={c.lotMixed ? "some contracts differ" : lot ? "units per lot" : "not in the instrument list"} />
              <Stat k="Data as of" v={istTime(c.asOf).replace(/^\d+ \w+ \d+, /, "")} sub={`${istTime(c.asOf).replace(/, .*$/, "")} · ${c.marketOpen ? "market open" : "market closed"} · ${c.daysToExpiry} day${c.daysToExpiry === 1 ? "" : "s"} to expiry`} />
            </section>

            <OiChart rows={rows} spot={c.spot} atm={c.atm} unit={unit} lot={lot} />

            <section className="card oc-tablecard" aria-labelledby="oc-t-h">
              <h2 id="oc-t-h">Chain <span className="faint">{c.underlying.key} · {new Date(c.expiry + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}</span></h2>
              <div className="oc-key" aria-label="Key"><span><i className="atmk" />ATM row</span><span><i className="itmk" />In the money</span>
                {Object.values(BUILDUP).map((b) => <span key={b.tag}><b>{b.tag}</b> {b.label.toLowerCase()}</span>)}</div>
              <ChainTable rows={rows} unit={unit} lot={lot} />
              <p className="faint oc-foot">{!c.marketOpen && c.nextOpen ? "The market is closed; this is the last session’s data and stays until the next session. " : `Refreshed about every ${c.refreshSeconds} seconds while the market is open. `}
                Prices in ₹. IV in % as Dhan reports it. Source: Dhan.</p>
            </section>
          </>)}
          <Definitions />
        </Gate>
        <RiskNote />
      </div>
    </>
  );
}
