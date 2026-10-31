import { Link } from "react-router";
import { ScreenerFrame, SortTh } from "../components/screener/ScreenerFrame";
import { HowDialog, Slider } from "../components/screener/controls";
import { CheckRow, FilterGroup, QuickRow, RangeRow } from "../components/screener/FilterGroup";
import { Donut } from "../components/screener/PageParts";
import { PrismPart, PrismScore, PrismTrend, med } from "../components/screener/cells";
import { AdvancedUpgrade } from "../components/screener/AdvancedUpgrade";
import { useScreener } from "../components/screener/useScreener";
import { useDocTitle } from "../lib/title";
import { useUI } from "../lib/ui";
import { nf, dateIN, MINUS } from "../lib/format";
import { PRISM_PRESETS, TECH_BANDS, TECH_BAND_ORDER, TECH_KEYS, TECH_NAMES, activePrismPreset, withPrismPreset, withoutPrismPreset } from "../lib/scoreScreen";
import { EXPLAIN, LABEL_WORD, PRISM_LABELS, PRISM_PARTS, coverageLine } from "../lib/scorePrism";
import "../styles/scorescreen.css";

/** Advanced score screener (Gold only): the whole company universe with the FinLit Prism rating, its four parts and its two technical views.
 *  Informational; not a recommendation. Plans below Gold get the upgrade page and never request the universe. */
export function AdvancedScoreScreener() {
  const { has } = useUI();
  useDocTitle("Advanced score screener", "Every listed company with its FinLit Prism rating: the four fundamental parts and the short-term and long-term technical views. Gold plan.");
  return has("gold") ? <Advanced /> : <AdvancedUpgrade />;
}

function Advanced() {
  const s = useScreener("advanced");
  const { draft, setDraft, applied, isLoading, sum, cover, prismAsOf, techAsOf } = s;
  const prismPreset = activePrismPreset(applied);
  const pickPreset = (id: string) => s.apply(prismPreset === id ? withoutPrismPreset(draft) : withPrismPreset(draft, PRISM_PRESETS.find((p) => p.id === id)!));

  const tiles: [string, string, string?][] = [
    ["Companies found", isLoading ? "…" : nf(sum.found, 0)],
    ["Sectors", isLoading ? "…" : nf(sum.sectors, 0)],
    ["Median Prism", med(sum.medZ) ?? MINUS, sum.medZ == null ? "No company in this result has a Prism rating yet" : `Middle value of ${nf(sum.nZ, 0)} companies with a Prism rating`],
    ["Rated by Prism", isLoading ? "…" : nf(sum.nZ, 0), `${nf(sum.nZ, 0)} of the ${nf(sum.found, 0)} companies in this result have a Prism rating`],
    ["Active filters", nf(s.filterCount, 0)],
  ];
  const line = !isLoading ? coverageLine(cover) : null;
  const n = cover ? cover.rated + cover.provisional : 0;

  return (
    <ScreenerFrame s={s} splitKey="score-adv" eyebrow="Advanced score screener" title="Every listed company, rated by FinLit Prism." sideLabel="Advanced score screener filters" errorTitle="The advanced score screener is unavailable right now"
      intro={<>The advanced model for the whole market: the Prism score, its four fundamental parts (Fundamentals, Valuation, Quality, Risk) and two technical views, short term and long term. Filter, sort, compare and export. Want the FinLit score instead? Use the <Link to="/score-screener">Basic score screener</Link>. Need more rules? Use the <Link to="/screener">full screener</Link>.</>}
      tier="gold" sortChoices={[{ key: "prism_final", label: "Prism" }, ...PRISM_PARTS.map((x) => ({ key: x.col, label: x.label })), { key: "prism_st_score", label: "Short-term technical" }, { key: "prism_lt_score", label: "Long-term technical" }]}
      donut={!isLoading && cover && cover.total > 0 ? <Donut part={n} total={cover.total} partLabel="Rated" restLabel="Not rated yet" title={`${nf(Math.max(0, cover.total - n), 0)} of ${nf(cover.total, 0)} companies are not rated yet.`} note="More are added every night, largest first." /> : undefined}
      presets={<div className="sx-presets" role="group" aria-label="Quick views built from the Prism parts">
        {PRISM_PRESETS.map((p) => <QuickRow key={p.id} label={p.label} on={prismPreset === p.id} title={p.say} onClick={() => pickPreset(p.id)} />)}
      </div>}
      filters={<>
        <FilterGroup id="score" title="Prism rating" defaultOpen active={(draft.rated ? 1 : 0) + draft.labels.length + (draft.ranges.z.min != null || draft.ranges.z.max != null ? 1 : 0)}>
          <CheckRow label="Only companies rated by Prism" checked={draft.rated} onChange={() => setDraft((d) => ({ ...d, rated: !d.rated }))} />
          <div className="fgx-chips" role="group" aria-label="Prism rating label">
            {PRISM_LABELS.map((l) => <button key={l} type="button" className={"fgx-chip" + (draft.labels.includes(l) ? " is-on" : "")} aria-pressed={draft.labels.includes(l)} onClick={() => s.setLabel(l)}>{draft.labels.includes(l) && <i aria-hidden="true">&#10003;</i>}{LABEL_WORD[l]}</button>)}
          </div>
          <RangeRow label="Prism score" group="Prism score, exact range" min={draft.ranges.z.min} max={draft.ranges.z.max} error={s.problems.z} onChange={(end, v) => s.setRange("z", end, v)} />
          <div className="pzs-sls"><Slider s={s} k="z" end="min" label="Prism" /><Slider s={s} k="z" end="max" label="Prism" /></div>
        </FilterGroup>
        <FilterGroup id="parts" title="Fundamental parts" defaultOpen active={PRISM_PARTS.filter((x) => draft.ranges[x.range].min != null || draft.ranges[x.range].max != null).length} hint="0 to 100, higher is better. A high Risk score means lower risk.">
          {PRISM_PARTS.map((x) => <RangeRow key={x.range} label={"Prism " + x.label} group={`Prism ${x.label} score, exact range`} min={draft.ranges[x.range].min} max={draft.ranges[x.range].max} error={s.problems[x.range]} onChange={(end, v) => s.setRange(x.range, end, v)} />)}
        </FilterGroup>
        <FilterGroup id="tech" title="Technical views" defaultOpen active={draft.tech.st.length + draft.tech.lt.length}>
          {TECH_KEYS.map((k) => (
            <div key={k} role="group" aria-label={`${TECH_NAMES[k]} view`}><div className="fgx-note">{TECH_NAMES[k]} view</div>
              {TECH_BAND_ORDER.map((b) => <CheckRow key={b} label={TECH_BANDS[b].label} checked={draft.tech[k].includes(b)} onChange={() => s.setTech(k, b)} />)}
            </div>))}
        </FilterGroup>
      </>}
      tiles={tiles}
      beforeTable={<>
        <details className="pzs-explain">
          <summary>What the Prism rating means</summary>
          <div className="pzs-two"><div><b>FinLit Prism <span className="faint">(Gold)</span></b><p>{EXPLAIN.prism}</p></div><div><b>Technical views</b><p>{EXPLAIN.technical}</p></div></div>
        </details>
        {line && cover && (<div className="pzs-cover" role="note"><p>{line} {cover.per_night ? `More are added every night, largest first (about ${nf(cover.per_night, 0)} beyond the companies with a full report).` : "More are added over time, largest first."} Not rated yet? Use Rate now on its row: its Prism page starts the calculation.</p>
          <div className="pzs-bar" aria-hidden="true"><i style={{ width: Math.min(100, (n / cover.total) * 100) + "%" }} /></div></div>)}
      </>}
      groupHead={<tr className="gh"><th scope="col" colSpan={6} className="sr-only-th"><span className="sr">Company</span></th><th scope="colgroup" colSpan={5}>FinLit Prism</th><th scope="colgroup" colSpan={2}>Technical views</th><th scope="col"><span className="sr">Actions</span></th></tr>}
      columnHeads={<>
        <SortTh s={s} k="prism_final" label="Prism" cls="pzs-h" title={EXPLAIN.prism} />
        {PRISM_PARTS.map((x) => <SortTh key={x.col} s={s} k={x.col} label={x.label} cls="ss-ph" title={"Prism " + x.label + ": " + x.say} />)}
        <SortTh s={s} k="prism_st_score" label="Short-term technical" cls="ss-ph" title="Prism's short-term (5 to 20 sessions) price-trend reading" />
        <SortTh s={s} k="prism_lt_score" label="Long-term technical" cls="ss-ph" title="Prism's long-term (6 to 18 months) price-trend reading" />
      </>}
      colSpan={14}
      cells={(r) => <>
        <td className="pzs-c"><PrismScore r={r} gold /></td>
        {PRISM_PARTS.map((x) => <td key={x.col} className="ss-pc"><PrismPart r={r} v={r[x.col]} gold /></td>)}
        <td><PrismTrend r={r} score={r.prism_st_score} gold col="st" /></td><td><PrismTrend r={r} score={r.prism_lt_score} gold col="lt" /></td>
      </>}
      plain="A screen narrows a long list. The Prism rating describes financial health and price trend from filings and prices; it is not a recommendation. Open a company's Prism page to see why a rating looks the way it does."
      how={<HowDialog onClose={() => s.setHow(false)}>
        <p>Every Prism figure runs from 0 to 100 (the technical views from {MINUS}100 to +100) and is worked out from a company's filed statements and its prices.</p>
        <dl>
          <dt>FinLit Prism</dt><dd>{EXPLAIN.prism} {prismAsOf ? <>Newest ratings were calculated on {dateIN(prismAsOf)}.</> : null}{techAsOf ? <> Technical columns use prices up to {dateIN(techAsOf)}.</> : null}</dd>
          <dt>Prism parts</dt><dd>{PRISM_PARTS.map((x) => `${x.label}: ${x.say}`).join(" ")} Each part is 0 to 100 and higher is better; a high Risk score means lower risk.</dd>
          <dt>Technical views</dt><dd>{EXPLAIN.technical} The filter bands are the ones on the Prism card: Positive {TECH_BANDS.pos.label.replace("Positive ", "")}, Neutral {TECH_BANDS.neutral.label.replace("Neutral ", "")}, Negative {TECH_BANDS.neg.label.replace("Negative ", "")}. Strongly positive counts as Positive and strongly negative as Negative.</dd>
          <dt>Not rated yet</dt><dd>Prism ratings are calculated about 30 seconds each from the provider's data, so they are added in steps: first for companies with a full report, then a few hundred more companies every night, largest first. A company without one shows "Not rated yet" and a Rate now link to its Prism page, which starts the calculation when opened. "Not rated" means Prism looked and the filed data was not enough.</dd>
          <dt>Size</dt><dd>Follows SEBI's rule, ranked by market value among the companies loaded here: the 100 largest are Large cap, the next 150 Mid cap, the rest Small cap.</dd>
          <dt>Missing data</dt><dd>A dash means the figure is not available (not rated yet, or not enough data). It never counts as a pass and is never treated as zero.</dd>
          <dt>FinLit score</dt><dd>The basic model has its own page, the <Link to="/score-screener">Basic score screener</Link> (Silver).</dd>
        </dl>
      </HowDialog>} />
  );
}
