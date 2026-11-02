// Macro page: "Sector impact" — every sector's macro backdrop (0 to 100, 50 neutral) with its label and the two indicators that move it most. Describes the
// economic backdrop of a sector, never a company and never a recommendation.
import { useMacroSectors, labelTone, reasonText } from "../lib/macroSectors";
import { dateIN } from "../lib/format";

export function MacroSectorImpact() {
  const q = useMacroSectors();
  const d = q.data;
  if (!d) return null;                                          // off, below Gold, or still loading: nothing on the page
  return (
    <section className="mc-panel msi" aria-labelledby="msiH">
      <h2 id="msiH">Sector impact</h2>
      <p className="mc-note">How today's macro readings tend to affect each sector: 50 is neutral; above is a tailwind, below a headwind. The reasons are the two indicators that move it most (+ helps, − hurts).{d.asOf ? ` Readings as of ${dateIN(d.asOf)}.` : ""}{!d.switchedOn && <b> Preview: shown to administrators only until it is switched on in the Console.</b>}</p>
      <div className="tw"><table className="msi-t">
        <thead><tr><th scope="col">Sector</th><th scope="col">Score (line at 50)</th><th scope="col" className="num">Score</th><th scope="col">Label</th><th scope="col">Top reasons</th></tr></thead>
        <tbody>{d.sectors.map((s) => (
          <tr key={s.key}>
            <th scope="row">{s.name}</th>
            <td><span className="msi-bar" aria-hidden="true"><i className={labelTone(s.label)} style={{ width: `${s.score}%` }} /><u /></span></td>
            <td className="num">{Math.round(s.score)}</td>
            <td><span className={"msi-l " + labelTone(s.label)}>{s.label}</span></td>
            <td>{s.reasons.map(reasonText).join(", ")}</td>
          </tr>))}</tbody>
      </table></div>
      <details className="msi-sig"><summary>The indicator signals behind it</summary>
        <ul>{d.signals.map((g) => <li key={g.key}><b>{g.label}</b> {g.signal == null ? <span className="faint">not used: {g.reason}</span> : <><span className="num">{g.signal > 0 ? "+" : g.signal < 0 ? "−" : ""}{Math.abs(g.signal).toFixed(2)}</span>{g.reading && <span className="faint"> · {g.reading}</span>}</>}</li>)}</ul>
        <p className="mc-note">{d.method} The sector sensitivities are starting estimates.</p>
      </details>
      <p className="mc-foot">{d.disclaimer}</p>
    </section>
  );
}
