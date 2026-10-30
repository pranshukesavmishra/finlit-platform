import { useEffect, useRef } from "react";
import { MINUS, nf } from "../lib/format";
import { hasSubscription, listingMove, minInvest, SUBSCRIPTION_ROWS, timeline, type Ipo } from "../lib/ipo";

export const fullDate = (iso: string) => new Date(iso + "T00:00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
export const asOf = (iso: string | null | undefined) => (iso ? new Date(iso).toLocaleString("en-IN", { timeZone: "Asia/Kolkata", day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit" }) + " IST" : null);
const money = (v: number) => "₹" + nf(v, v % 1 ? 2 : 0);
const signed = (v: number, d = 1) => (v >= 0 ? "+" : MINUS) + nf(Math.abs(v), d);
const KINDS = { mainboard: "Mainboard", sme: "SME" } as const;

/** One IPO in full. Only facts that are in the data appear; there are no placeholder rows. */
export function IpoDrawer({ ipo: r, chip, onClose }: { ipo: Ipo; chip: { label: string; colour: string }; onClose: () => void }) {
  const box = useRef<HTMLElement>(null);
  useEffect(() => {
    const prev = document.activeElement as HTMLElement | null;
    box.current?.focus();
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", key);
    return () => { document.removeEventListener("keydown", key); prev?.focus?.(); };
  }, [onClose]);
  const d = r.details || {}, mi = minInvest(r), mv = r.status === "listed" ? listingMove(r) : null, steps = timeline(r), at = asOf(r.updatedAt);
  const band = r.priceLow != null && r.priceHigh != null && r.priceLow !== r.priceHigh ? `${money(r.priceLow)} to ${money(r.priceHigh)}` : r.priceHigh != null ? money(r.priceHigh) : null;
  const facts: [string, string][] = ([
    ["Board", KINDS[r.kind]], ["Issue type", d.issueType], ["Exchange", d.exchange?.join(", ")], ["Sector", r.sector], ["Symbol", r.symbol],
    [r.priceLow !== r.priceHigh ? "Price band" : "Issue price", band], ["Face value", d.faceValue != null ? money(d.faceValue) : null], ["Market lot", r.lotSize ? `${nf(r.lotSize, 0)} shares` : null],
    ["Issue size", r.issueSizeCr != null ? `₹${nf(r.issueSizeCr, 0)} Cr` : null], ["Registrar", d.registrar],
  ] as [string, string | null | undefined][]).filter((f): f is [string, string] => !!f[1]);
  const split = d.freshIssueCr != null || d.ofsCr != null;
  const docs = ([["Draft red herring prospectus", d.docs?.drhp], ["Red herring prospectus", d.docs?.rhp], ["Prospectus", d.docs?.prospectus], ["Offer document", r.link]] as [string, string | null | undefined][]).filter((x): x is [string, string] => !!x[1]);
  return (
    <div className="ipo-dr-bg" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <aside className="ipo-dr" role="dialog" aria-modal="true" aria-labelledby="ipoDrTitle" tabIndex={-1} ref={box} style={{ "--tc": chip.colour } as React.CSSProperties}>
        <header className="ipo-dr-h">
          <div><h2 id="ipoDrTitle">{r.name}</h2><span className="ipo-st"><i />{chip.label}</span></div>
          <button className="ipo-dr-x" onClick={onClose} aria-label="Close details">×</button>
        </header>

        {mv && (
          <section className="ipo-dr-s ipo-perf" aria-label="Listing-day performance">
            <h3>Listing-day performance</h3>
            <p className={"ipo-perf-n " + (mv.pct >= 0 ? "up" : "down")}>{signed(mv.pct)}% <small>({mv.rupees >= 0 ? "+" : MINUS}₹{nf(Math.abs(mv.rupees), 2)} per share)</small></p>
            <p className="ipo-sum">Listing price {money(mv.listing)} compared with the {mv.basis} {money(mv.issue)}: {money(mv.listing)} {MINUS} {money(mv.issue)} = {mv.rupees >= 0 ? "" : MINUS}₹{nf(Math.abs(mv.rupees), 2)}, which is {signed(mv.pct, 2)}% of {money(mv.issue)}.</p>
            <p className="muted">Listing price compared with the issue price; not a return on any investment.</p>
          </section>
        )}

        {facts.length > 0 && <section className="ipo-dr-s"><h3>Issue facts</h3><dl className="ipo-kv">{facts.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl></section>}

        {mi != null && <section className="ipo-dr-s"><h3>Minimum investment</h3><p className="ipo-sum">{nf(r.lotSize || 0, 0)} shares (one lot) × {money(r.priceHigh || 0)} (upper end of the price band) = <b>₹{nf(mi, 0)}</b></p></section>}
        {mi == null && d.minInvestmentProvided != null && <section className="ipo-dr-s"><h3>Minimum investment</h3><p className="ipo-sum"><b>₹{nf(d.minInvestmentProvided, 0)}</b> <span className="muted">as given by the data provider</span></p></section>}

        {steps.length > 1 && <section className="ipo-dr-s"><h3>Key dates</h3>
          <ol className="ipo-tl">{steps.map((s) => <li key={s.key}><i /><b>{s.label}</b><span>{fullDate(s.date)}</span></li>)}</ol></section>}

        {hasSubscription(r) && <section className="ipo-dr-s"><h3>Subscription</h3>
          <table className="ipo-sub"><caption className="sr-only">Times subscribed by investor category</caption><thead><tr><th scope="col">Category</th><th scope="col">Times subscribed</th></tr></thead>
            <tbody>{SUBSCRIPTION_ROWS.filter(([k]) => d.subscription?.[k] != null).map(([k, l]) => <tr key={k}><th scope="row">{l}</th><td>{nf(d.subscription![k]!, 2)}x</td></tr>)}</tbody></table></section>}

        {split && <section className="ipo-dr-s"><h3>Issue breakdown</h3><dl className="ipo-kv">
          {d.freshIssueCr != null && <div><dt>Fresh issue</dt><dd>₹{nf(d.freshIssueCr, 0)} Cr</dd></div>}
          {d.ofsCr != null && <div><dt>Offer for sale</dt><dd>₹{nf(d.ofsCr, 0)} Cr</dd></div>}</dl></section>}

        {(d.promoterPrePct != null || d.promoterPostPct != null) && <section className="ipo-dr-s"><h3>Promoter holding</h3><dl className="ipo-kv">
          {d.promoterPrePct != null && <div><dt>Before the issue</dt><dd>{nf(d.promoterPrePct, 2)}%</dd></div>}
          {d.promoterPostPct != null && <div><dt>After the issue</dt><dd>{nf(d.promoterPostPct, 2)}%</dd></div>}</dl></section>}

        {!!d.leadManagers?.length && <section className="ipo-dr-s"><h3>Lead managers</h3><ul className="ipo-ul">{d.leadManagers.map((m) => <li key={m}>{m}</li>)}</ul></section>}
        {!!d.objectives?.length && <section className="ipo-dr-s"><h3>Objects of the issue</h3><ul className="ipo-ul">{d.objectives.map((m) => <li key={m}>{m}</li>)}</ul></section>}
        {d.about && <section className="ipo-dr-s"><h3>About</h3><p className="ipo-sum">{d.about}</p></section>}
        {docs.length > 0 && <section className="ipo-dr-s"><h3>Documents</h3><ul className="ipo-ul">{docs.map(([l, u]) => <li key={l}><a href={u} target="_blank" rel="noopener noreferrer">{l} ↗</a></li>)}</ul></section>}

        {r.note && <p className="ipo-sum muted">{r.note}</p>}
        <footer className="ipo-dr-f">{at && <span>Data as of {at}</span>}{r.source && <span>Source: {r.source}</span>}</footer>
      </aside>
    </div>
  );
}
