// Under a company's tags: the macro backdrop of its sector ("Headwind · Rate hikes −, Credit +"). Separate from every score on the page: it describes the
// economy around the sector, not the company. Gold, and only once switched on (administrators always see it); nothing is shown otherwise.
import { Link } from "react-router";
import { useMacroSectors, labelTone, reasonText } from "../lib/macroSectors";

export function MacroBackdrop({ symbol }: { symbol: string }) {
  const q = useMacroSectors(symbol, !!symbol);
  const c = q.data?.company;
  if (!q.data || !c) return null;
  if (!c.sector) return <div className="mb-line"><span className="mb-k">Macro backdrop</span><span className="faint">{c.reason}</span></div>;
  const s = c.sector;
  return (
    <div className="mb-line" title={`${s.name}: ${Math.round(s.score)} out of 100 (50 is neutral). ${q.data.disclaimer}`}>
      <span className="mb-k">Macro backdrop</span>
      <span className={"msi-l " + labelTone(s.label)}>{s.label}</span>
      <span className="mb-s">{s.name} · {Math.round(s.score)}/100 · {s.reasons.map(reasonText).join(", ")}</span>
      <Link to="/macro#sector-impact" className="mb-more">How it works</Link>
      {!q.data.switchedOn && <span className="faint mb-prev">Preview: administrators only</span>}
    </div>
  );
}
