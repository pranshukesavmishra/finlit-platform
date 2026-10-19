import { PageArt } from "../components/PageArt";
import { Link } from "react-router";
import { useMemo, useState } from "react";
import { BAND_LABEL, useUniverse, type Row } from "../lib/screener";
import { useUI } from "../lib/ui";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import { Reveal } from "../components/Reveal";
import { nf, MINUS } from "../lib/format";
import { useIndices } from "../lib/indices";
import { useGold } from "../lib/premium";

const FEATURED = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "BPCL", "ITC"];
const TABS = [["score", "Highest scoring", "Silver"], ["size", "Largest companies", ""], ["up", "Top gainers today", ""], ["down", "Top decliners today", ""]] as const;

/** The market at a glance, at the front of Stock research: the key indices with today's level, move and P/E, refreshed every minute. */
function IndexBoard() {
  const { data, isError } = useIndices();
  const gold = useGold();
  if (isError || !data) return data === undefined && !isError ? <section className="sec" style={{ paddingBottom: 0 }}><div className="wrap"><div className="skeleton" style={{ height: 96 }} aria-busy="true" /></div></section> : null;
  const key = data.key.map((c) => data.items.find((r) => r.code === c)).filter((r) => r && r.close != null);
  if (!key.length) return null;
  return (
    <section className="sec" style={{ paddingBottom: 0 }}><div className="wrap">
      <Reveal className="sec-h"><div className="eyebrow"><span className={"pm-live" + (data.marketOpen ? " on" : "")} />{data.marketOpen ? "Market open · live" : "Market closed · last close"}{data.asOf ? ` · ${new Date(data.asOf + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" })}` : ""}</div><h2>The market today</h2></Reveal>
      <div className="pm-heat ib" aria-label="Index levels">{key.map((r) => { const c = r!.changePct, good = r!.code === "INDVIX" ? (c ?? 0) <= 0 : (c ?? 0) >= 0;
        return <div key={r!.code} className="pm-tile" style={{ "--tc": c == null ? "var(--faint)" : good ? "var(--gain)" : "var(--loss)", "--ti": c == null ? 0 : 6 + Math.min(Math.abs(c), 3) * 7 } as React.CSSProperties}>
          <small>{r!.name}</small><b>{nf(r!.close as number)}</b><span>{c == null ? MINUS : (c > 0 ? "▲ +" : c < 0 ? "▼ " + MINUS : "") + nf(Math.abs(c)) + "%"}{r!.points != null ? ` (${r!.points > 0 ? "+" : ""}${nf(r!.points)})` : ""}</span>{r!.pe != null && <em>P/E {nf(r!.pe, 1)}</em>}</div>; })}</div>
      <p className="faint" style={{ fontSize: 12.5, margin: "10px 2px 0" }}>{gold ? <>All {data.items.length} indices and 5-year valuation history: <Link to="/premium/markets#indices">Market events &amp; index dashboard</Link>.</> : <>NSE and BSE index levels, refreshed every minute while the market is open.</>}</p>
    </div></section>
  );
}

export function Research({ onSearch }: { onSearch: () => void }) {
  useDocTitle("Stock research", "A FinLit research report for every listed Indian stock: score, scorecard, financials, ratios, ownership and peers.");
  const { data, isLoading } = useUniverse();
  const { has, upgrade } = useUI();
  const rows = data?.rows || [];
  const scored = rows.some((r) => r.overall != null);
  const [tab, setTab] = useState<(typeof TABS)[number][0]>("size");
  const traded = useMemo(() => rows.filter((r) => r.price != null && (r.market_cap ?? 0) >= 100), [rows]);
  const list = useMemo(() => {
    const by = (k: "market_cap" | "change_pct" | "overall", dir: 1 | -1) => [...traded].filter((r) => r[k] != null).sort((x, y) => dir * ((y[k] as number) - (x[k] as number)));
    return (tab === "score" ? by("overall", 1) : tab === "up" ? by("change_pct", 1) : tab === "down" ? by("change_pct", -1) : by("market_cap", 1)).slice(0, 12);
  }, [traded, tab]);
  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.7 }} /><div className="wrap"><PageArt kind="research" />
        <div className="eyebrow">Stock research</div><h1>Every listed stock, in one honest report.</h1>
        <p>A research score, five-pillar scorecard, statements, ratios, ownership and peers, loaded in a blink.</p>
        <div style={{ marginTop: 28 }}><button className="bigsearch" onClick={onSearch}><Icon name="table" /><span>Search any company or ticker</span><span className="kbd">Ctrl K</span></button></div>
      </div></section>
      <IndexBoard />
      <section className="sec"><div className="wrap">
        <Reveal className="sec-h"><div className="eyebrow">Start exploring</div><h2>{rows.length ? "Where to look today" : "Popular reports"}</h2></Reveal>
        {rows.length > 0 && (
          <div className="seg" role="group" aria-label="List" style={{ marginBottom: 16, flexWrap: "wrap" }}>
            {TABS.map(([k, l, tier]) => <button key={k} aria-pressed={tab === k} onClick={() => (k === "score" && !has("silver") ? upgrade("silver", "Ranking by FinLit score is part of Silver.") : setTab(k))}>{l}{tier && !has("silver") ? <Icon name="lock" /> : null}</button>)}
          </div>)}
        {tab === "score" && !scored && rows.length > 0 && <p className="muted">Scores appear here once your plan includes them.</p>}
        {isLoading && <div className="skeleton" style={{ height: 160 }} />}
        <div className="sgrid">
          {(rows.length ? list : FEATURED.map((s) => ({ symbol: s, name: s, band: null, overall: null, price: null, sector: null, change_pct: null, market_cap: null } as unknown as Row))).map((r) => (
            <Link className="scard" key={r.symbol} to={`/stocks/${r.symbol}`}><b>{r.symbol}</b><span>{r.name && r.name !== r.symbol ? r.name : r.sector || "Open the report"}</span>
              <span style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                {r.overall != null && <span className={"vd " + (r.band === "strong" ? "strong" : r.band === "healthy" ? "healthy" : r.band === "mixed" ? "mixed" : "weak")}>{r.band ? BAND_LABEL[r.band] : ""} {r.overall}</span>}
                {r.price != null && <span className="mono">₹{nf(r.price)}</span>}
                {r.change_pct != null && <span className={"mono " + (r.change_pct >= 0 ? "up" : "down")}>{(r.change_pct >= 0 ? "▲ +" : "▼ −") + nf(Math.abs(r.change_pct), 2)}%</span>}
              </span></Link>
          ))}
        </div>
        <p style={{ marginTop: 20 }}><Link className="btn" to="/screener">Open the screener <Icon name="arrow" /></Link></p>
      </div></section>
    </>
  );
}
