import { useState } from "react";
import { TONE, type InsightCard, type OwnInsights } from "../../lib/ownView";

/** The tone is always an icon and a word, never colour alone. */
export function ToneTag({ tone }: { tone: InsightCard["tone"] }) {
  const t = TONE[tone];
  return <span className={`ow-tone t-${tone}`}><span className="ow-glyph" aria-hidden="true">{t.glyph}</span>{t.word}</span>;
}

/** "What changed, in short": up to three cards (tone, short title, one number); the rest behind "Show more"; the quiet text when no rule fired. The full sentence is for tooltips and screen readers. */
export function OwnInsightCards({ ins, why, stale }: { ins?: OwnInsights; why?: string | null; stale?: boolean }) {
  const [more, setMore] = useState(false);
  const cards = ins?.cards ?? [], rest = ins?.more ?? [];
  let body: React.ReactNode;
  if (!ins && !why) body = <div className="skeleton" style={{ height: 96 }} aria-label="Reading the filings" />;
  else if (!ins?.available) body = <p className="ow-note" role="status">{why || ins?.reason || "The insights for this company are not available yet."}</p>;
  else if (stale) body = <p className="ow-note" role="status">The short readings are being refreshed for the newest filing.</p>;
  else if (!cards.length) body = <p className="ow-note">{ins.quiet_text || "The latest filing shows no notable change."}</p>;
  else body = (
    <>
      <div className="ow-cards">
        {cards.map((c) => (
          <div key={c.id} className={`ow-icard t-${c.tone}`} title={c.text}>
            <ToneTag tone={c.tone} />
            <div className="ow-ct">{c.title}</div>
            <div className="ow-cs">{c.stat}</div>
            <span className="sr-only">{c.text}</span>
          </div>
        ))}
      </div>
      {more && rest.length > 0 && (
        <ul className="ow-more" id="ow-more">
          {rest.map((m) => <li key={m.id} title={m.text}><ToneTag tone={m.tone} /><b>{m.title}</b><span className="ow-muted">{m.stat}</span><span className="sr-only">{m.text}</span></li>)}
        </ul>
      )}
      {rest.length > 0 && <button type="button" className="ow-btn ow-more-btn" aria-expanded={more} aria-controls="ow-more" onClick={() => setMore((m) => !m)}>{more ? "Show fewer" : `Show ${rest.length} more`}</button>}
    </>
  );
  return (
    <section className="ow-card" aria-labelledby="ow-says">
      <div className="ow-sec-h">
        <h3 id="ow-says">What changed, in short</h3>
        <span className="ow-small ow-muted">{ins?.as_of ? `Latest filing, ${ins.as_of} · ` : ""}same 21 rules for every stock · <a href="#method">how we read it</a></span>
      </div>
      {body}
    </section>
  );
}
