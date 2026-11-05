// Blocks 3 and 4: Market snapshot (breadth, and gainers / decliners for Nifty 50, Nifty 500 or all stocks) and Sectors today (a ranked bar list).
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { titleOf } from "../../lib/companyLabel";
import { MINUS, nf } from "../../lib/format";
import { gainers, losers, sectorBoard, useMembers, weightedMove, MAX_MOVE } from "../../lib/markets";
import { scopeStocks, type Scope } from "../../lib/dashboard";
import type { Row } from "../../lib/screener";
import { Card, Rows, Seg, tone, useIsPhone } from "./parts";

const sgn = (v: number | null | undefined, d = 2) => (v == null ? MINUS : (v > 0 ? "+" : v < 0 ? MINUS : "") + nf(Math.abs(v), d) + "%");
const SCOPES = [["n50", "Nifty 50"], ["n500", "Nifty 500"], ["all", "All stocks"]] as const;
const SCOPE_WORD: Record<Scope, string> = { n50: "Nifty 50", n500: "Nifty 500", all: "All stocks" };

export function Snapshot({ rows, loading }: { rows: Row[]; loading: boolean }) {
  const [scope, setScope] = useState<Scope>("n50");
  const phone = useIsPhone(), take = phone ? 4 : 5;
  const members = useMembers().data?.indices;
  const m = useMemo(() => {
    const live = rows.filter((r) => r.change_pct != null && (r.price ?? 0) > 0);          // suspended or delisted companies carry no price and a −100% "change"
    const adv = live.filter((r) => (r.change_pct as number) > 0).length, dec = live.filter((r) => (r.change_pct as number) < 0).length;
    const big = live.filter((r) => (r.market_cap ?? 0) >= 100 && Math.abs(r.change_pct as number) <= MAX_MOVE);
    return { n: live.length, adv, dec, flat: live.length - adv - dec, all: weightedMove(big) };
  }, [rows]);
  const pick = useMemo(() => scopeStocks(scope, rows, members), [scope, rows, members]);
  const up = gainers(pick.stocks, take), down = losers(pick.stocks, take);
  const col = (title: string, list: Row[], cls: string) => (
    <div><div className="dsh-lh">{SCOPE_WORD[scope]} {title}</div>
      {list.length ? list.map((r) => <Link key={r.symbol} to={`/stocks/${r.symbol}`} className="dsh-mv"><b>{titleOf(r)}</b><span className={cls}>{sgn(r.change_pct)}</span></Link>) : <p className="dsh-note">{pick.note ?? `No ${title} in this group today.`}</p>}</div>
  );
  return (
    <Card id="snapshot" title="Market snapshot" sub={m.n ? <>{m.n.toLocaleString("en-IN")} companies{m.all != null ? <> · cap-weighted move <b className={tone(m.all)}>{sgn(m.all)}</b></> : null}</> : undefined}>
      {loading || !m.n ? <Rows n={4} h={34} /> : <>
        <div className="dsh-lh first">Breadth</div>
        <div className="dsh-breadth" role="img" aria-label={`${m.adv} rising, ${m.dec} falling, ${m.flat} unchanged`}><i className="up" style={{ flex: m.adv || 0.01 }} /><i style={{ flex: Math.max(m.flat, 0.01) }} /><i className="down" style={{ flex: m.dec || 0.01 }} /></div>
        <div className="dsh-bk"><span className="up">▲ {m.adv.toLocaleString("en-IN")} rising</span><span>{m.flat.toLocaleString("en-IN")} <span className="long">unchanged</span><span className="short">flat</span></span><span className="down">▼ {m.dec.toLocaleString("en-IN")} <span className="long">falling</span></span></div>
        <div className="dsh-scope"><Seg label="Stocks to rank" value={scope} options={SCOPES} onChange={setScope} /></div>
        <div className="dsh-two">{col("gainers", up, "up")}{col("decliners", down, "down")}</div>
        {pick.note && (up.length || down.length) ? <p className="dsh-foot">{pick.note}</p> : null}
      </>}
    </Card>
  );
}

export function Sectors({ rows, loading }: { rows: Row[]; loading: boolean }) {
  const phone = useIsPhone(), [all, setAll] = useState(false);
  const board = useMemo(() => [...sectorBoard(rows)].sort((a, b) => b.move - a.move), [rows]);
  const max = Math.max(0.01, ...board.map((s) => Math.abs(s.move)));
  const list = phone && !all ? board.slice(0, 6) : board;
  return (
    <Card id="sectors" title="Sectors today" sub="Cap-weighted move, ranked · companies above ₹100 crore">
      {loading || !board.length ? <Rows n={8} h={26} /> : <>
        <div className="dsh-sec">{list.map((s) => (
          <div key={s.sector} className="dsh-sec-r" title={`${s.n} companies`}><span className="nm">{s.sector}</span>
            <span className="bar" aria-hidden="true"><span className="neg">{s.move < 0 && <i style={{ width: `${(Math.abs(s.move) / max) * 100}%` }} />}</span><span className="pos">{s.move > 0 && <i style={{ width: `${(s.move / max) * 100}%` }} />}</span></span>
            <span className={"v " + tone(s.move)}>{Math.abs(s.move) < 0.005 ? "0.00%" : sgn(s.move)}</span></div>))}</div>
        {phone && board.length > 6 && <button type="button" className="dsh-more" onClick={() => setAll(!all)}>{all ? "Show the top 6" : `All ${board.length} sectors →`}</button>}
        <p className="dsh-callout">Coming soon: each sector's state (Thrust, Confirmed, Fading or Washout) from FinLit's sector engine.</p>
      </>}
    </Card>
  );
}
