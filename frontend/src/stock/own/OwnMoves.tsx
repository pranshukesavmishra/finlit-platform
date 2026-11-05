import { ChartHelp } from "../../components/ChartHelp";
import { CMP_OPTIONS, pc, type Moves } from "../../lib/ownView";

/** Before and after bars for the chosen window, with neutral badges and the note on whether new shares were issued. */
export function OwnMoves({ moves, q, sel, onQ }: { moves: Moves; q: number; sel: number; onQ: (q: number) => void }) {
  const activeQ = Math.min(q, sel);
  return (
    <section className="ow-card" aria-labelledby="ow-moves">
      <div className="ow-sec-h"><h3 id="ow-moves" className="ow-h2">Who bought and who sold<ChartHelp id="own-bought-sold" /></h3><span className="ow-small ow-muted">{sel === 0 ? `${moves.to}, no earlier filing to compare` : `${moves.from} → ${moves.to}`}</span></div>
      <div className="ow-seg" role="group" aria-label="Compare with">
        {CMP_OPTIONS.map((o) => <button key={o.q} type="button" aria-pressed={o.q === activeQ} disabled={sel - o.q < 0} aria-label={o.label} onClick={() => onQ(o.q)}><span className="ow-lg" aria-hidden="true">{o.label}</span><span className="ow-sh" aria-hidden="true">{o.short}</span></button>)}
      </div>
      {moves.rows.map((r) => (
        <div className="ow-move" key={r.key}>
          <div className="ow-mvt"><span className="ow-nm"><span className="ow-dot" style={{ background: r.color }} aria-hidden="true" />{r.name}</span><span className="ow-badge">{r.badge}</span></div>
          <div className="ow-bars">
            <span className="ow-muted">{moves.from}</span><span className="ow-track"><i style={{ width: `${r.barBefore.toFixed(1)}%`, background: r.color, opacity: 0.35 }} /></span><span className="ow-r">{pc(r.before)}</span>
            <span className="ow-muted">{moves.to}</span><span className="ow-track"><i style={{ width: `${r.barNow.toFixed(1)}%`, background: r.color }} /></span><b className="ow-r">{pc(r.now)}</b>
          </div>
        </div>
      ))}
      <p className="ow-note" role="status">{sel === 0 ? "This is the first filing on record, so there is nothing earlier to compare with." : moves.note}</p>
    </section>
  );
}
