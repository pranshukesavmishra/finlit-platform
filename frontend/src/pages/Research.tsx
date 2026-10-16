import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { apiGet, type Summary } from "../lib/api";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import { Reveal } from "../components/Reveal";
import { nf } from "../lib/format";

type Row = { symbol: string; band: string | null; overall: number | null; price: number | null; sector: string | null; pe: number | null; roe: number | null };
const FEATURED = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "BPCL", "ITC"];

export function Research({ onSearch }: { onSearch: () => void }) {
  useDocTitle("Stock research", "A FinLit research report for every listed Indian stock: score, scorecard, financials, ratios, ownership and peers.");
  const { data } = useQuery({ queryKey: ["top"], queryFn: () => apiGet<{ rows: Row[] }>("/api/screener/top?limit=24"), staleTime: 60_000, retry: 1 });
  const rows = data?.rows || [];
  return (
    <>
      <section className="pagehead"><div className="aurora" style={{ opacity: 0.7 }} /><div className="wrap">
        <div className="eyebrow">Stock research</div><h1>Every listed stock, in one honest report.</h1>
        <p>A research score, five-pillar scorecard, statements, ratios, ownership and peers, loaded in a blink.</p>
        <div style={{ marginTop: 28 }}><button className="bigsearch" onClick={onSearch}><Icon name="table" /><span>Search any company or ticker</span><span className="kbd">Ctrl K</span></button></div>
      </div></section>
      <section className="sec"><div className="wrap">
        <Reveal className="sec-h"><div className="eyebrow">{rows.length ? "Highest scoring" : "Start with"}</div><h2>{rows.length ? "Strong businesses right now" : "Popular reports"}</h2></Reveal>
        <div className="sgrid">
          {(rows.length ? rows : FEATURED.map((s) => ({ symbol: s, band: null, overall: null, price: null, sector: null, pe: null, roe: null }))).map((r) => (
            <Link className="scard" key={r.symbol} to={`/stocks/${r.symbol}`}><b>{r.symbol}</b><span>{r.sector || "Open the report"}</span>
              {r.overall != null && <span style={{ display: "flex", gap: 8, alignItems: "center" }}><span className={"vd " + (r.band === "strong" ? "strong" : r.band === "healthy" ? "healthy" : r.band === "mixed" ? "mixed" : "weak")}>{r.band}</span><span className="mono">{r.overall}/100</span></span>}
              {r.price != null && <span className="mono">₹{nf(r.price)}</span>}</Link>
          ))}
        </div>
      </div></section>
    </>
  );
}
void (null as unknown as Summary);
