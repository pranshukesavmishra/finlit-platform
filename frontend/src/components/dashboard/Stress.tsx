// Block 6, Stress Lab: today's conditions. The Stress Lab nightly run (site_data/stress/SYM.json) is not part of this codebase yet, so every followed stock is shown as "Not covered yet"
// (banks and lenders: "Not covered: banks and lenders"). Nothing is estimated; the rows fill in when the batch exists.
import { Link } from "react-router";
import { isLenderSector } from "../../lib/questionBank";
import { Card, Rows } from "./parts";
import type { Followed } from "./MyStocks";

export function Stress({ followed, loading, sectors }: { followed: Followed[]; loading: boolean; sectors: Map<string, string | null> }) {
  const shown = followed.slice(0, 5);
  return (
    <Card id="stress" title="Stress Lab: today's conditions" right={<span className="dsh-new">New</span>} sub="How crude, rupee, inflation and rate shocks would touch the stocks you follow">
      {loading ? <Rows n={3} h={34} /> : !shown.length ? <p className="dsh-note">Follow stocks to see how today's conditions could touch them.</p> : <>
        <p className="dsh-note">The Stress Lab's nightly run does not cover any stock yet, so there are no shocks or earnings changes to show. They appear here once it does.</p>
        <div className="dsh-lh">Your stocks</div>
        {shown.map((f) => <div key={f.symbol} className="dsh-sl"><Link to={`/stocks/${f.symbol}`}><b>{f.symbol}</b></Link><span>{isLenderSector(sectors.get(f.symbol)) ? "Not covered: banks and lenders" : "Not covered yet"}</span></div>)}
      </>}
    </Card>
  );
}
