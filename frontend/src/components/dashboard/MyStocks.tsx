// Block 1, Your stocks today: one row per followed stock (at most 10): price and today's move from the quotes call for just those symbols, FinLit IQ, latest quarter against the
// same quarter a year earlier, and any alert. Descriptive only; a blank carries its reason.
import { Link } from "react-router";
import { useQueries } from "@tanstack/react-query";
import { apiGet, useQuotesFor, type Financials } from "../../lib/api";
import { useAlerts } from "../../lib/alerts";
import { quoteMap, BAND_LABEL } from "../../lib/globalSearch";
import { MINUS, nf } from "../../lib/format";
import { dayMonth, quarterEndLabel, yoyLabel } from "../../lib/dashboard";
import { Card, Rows, tone } from "./parts";

export type Followed = { symbol: string; name: string | null };
const MAX = 10;
const pct = (v: number | null | undefined, d = 1) => (v == null ? "—" : (v > 0 ? "+" : v < 0 ? MINUS : "") + nf(v, d) + "%");

function Pill({ score, band }: { score: number | null; band: string | null }) {
  if (band === "locked") return <span className="dsh-pill none" title="The FinLit IQ is part of the Silver plan">Silver</span>;
  if (score == null || !band) return <span className="dsh-pill none" title="Not scored yet">—</span>;
  return <span className={"dsh-pill " + band}>{Math.round(score)} · {BAND_LABEL[band] ?? band}</span>;
}

export function MyStocks({ followed, loading }: { followed: Followed[]; loading: boolean }) {
  const shown = followed.slice(0, MAX), syms = shown.map((f) => f.symbol);
  const quotes = useQuotesFor(syms), qm = quoteMap(quotes.data);
  const fins = useQueries({ queries: syms.map((s) => ({ queryKey: ["stock", s, "/financials"], queryFn: () => apiGet<Financials>(`/api/stocks/${s}/financials`), staleTime: 60_000, retry: false })) });
  const { alerts } = useAlerts();
  const latestEnd = fins.map((f) => f.data?.quarterly?.pl?.periodEnds?.slice(-1)[0]).filter(Boolean).sort().pop();
  const priced = [...qm.values()].map((q) => q.date).filter(Boolean).sort().pop();
  const when = priced ? dayMonth(priced) : null;
  const sub = followed.length ? `${followed.length > MAX ? `${MAX} of ${followed.length}` : followed.length} followed${when ? ` · prices of ${when}` : ""}${latestEnd ? ` · latest quarter ${quarterEndLabel(latestEnd)}` : ""}` : undefined;
  return (
    <Card id="mystocks" title="Your stocks today" sub={sub} right={<Link className="dsh-link" to="/watchlist"><span className="long">Open watchlist</span><span className="short">Watchlist</span> →</Link>}>
      {loading ? <Rows n={3} h={56} /> : !followed.length ? (
        <div className="dsh-empty"><b>Follow stocks to see them here every day</b><p>Price, today's move, FinLit IQ and latest results for each stock you follow.</p>
          <button type="button" className="dsh-search" onClick={() => dispatchEvent(new Event("finlit:open-search"))}>Find a stock to follow</button></div>
      ) : (
        <div className="dsh-st" role="table" aria-label="Followed stocks">
          <div className="dsh-st-h" role="row"><span role="columnheader">Stock</span><span role="columnheader" className="r">Price</span><span role="columnheader" className="r">Today</span><span role="columnheader">FinLit IQ</span><span role="columnheader" className="r">Revenue YoY</span><span role="columnheader" className="r">Profit YoY</span><span role="columnheader" className="r">Alert</span></div>
          {shown.map((f, i) => {
            const q = qm.get(f.symbol), fin = fins[i], pl = fin.data?.quarterly?.pl;
            const rev = pl ? yoyLabel(pl.rows.revenue, pl.periodEnds) : null, np = pl ? yoyLabel(pl.rows.net_profit, pl.periodEnds) : null;
            const mine = alerts.filter((a) => a.symbol === f.symbol && a.status !== "done");
            const reasonRev = fin.isError ? "Results not available for this company yet" : rev?.reason ?? undefined;
            const reasonNp = fin.isError ? "Results not available for this company yet" : np?.reason ?? undefined;
            return (
              <div className="dsh-st-r" role="row" key={f.symbol}>
                <div className="nm" role="cell"><Link to={`/stocks/${f.symbol}`}>{/^\d+$/.test(f.symbol) && f.name ? f.name : f.symbol}</Link><small>{f.name || ""}</small></div>
                <div className="dsh-pr r" role="cell">{quotes.isLoading ? <i className="skeleton sk-n" /> : q?.price != null ? "₹" + nf(q.price) : <span title="No traded price held yet">—</span>}</div>
                <div className={"ch r " + tone(q?.chg)} role="cell">{quotes.isLoading ? <i className="skeleton sk-n" /> : pct(q?.chg, 2)}</div>
                <div className="dsh-st-x"><div className="sc" role="cell">{quotes.isLoading ? <i className="skeleton sk-p" /> : <Pill score={q?.score ?? null} band={q?.band ?? null} />}</div>
                <div className={"yy r " + tone(rev?.tone === "up" ? 1 : rev?.tone === "down" ? -1 : 0)} role="cell" title={reasonRev}><b className="lbl">Revenue </b>{fin.isLoading ? <i className="skeleton sk-n" /> : rev?.text ?? pct(rev?.pct)}</div>
                <div className={"yy r " + tone(np?.tone === "up" ? 1 : np?.tone === "down" ? -1 : 0)} role="cell" title={reasonNp}><b className="lbl">Profit </b>{fin.isLoading ? <i className="skeleton sk-n" /> : np?.text ?? pct(np?.pct)}</div>
                <div className="al r" role="cell">{mine.length ? <Link to="/alerts" title={mine.map((a) => a.label).join(", ")}>{mine.length === 1 ? (mine[0].met ? "Alert met" : "Alert set") : `${mine.length} alerts`}</Link> : <Link to="/alerts">Add alert</Link>}</div></div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
}
