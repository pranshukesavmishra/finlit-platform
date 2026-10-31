import { Link, Navigate, useSearchParams } from "react-router";
import { ScreenerFrame, SortTh } from "../components/screener/ScreenerFrame";
import { HowDialog } from "../components/screener/controls";
import { ChipRow, FilterGroup, QuickRow, RangeRow } from "../components/screener/FilterGroup";
import { Donut } from "../components/screener/PageParts";
import { Score, med } from "../components/screener/cells";
import { useScreener } from "../components/screener/useScreener";
import { TierChip } from "../components/Gate";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import { nf, dateIN, MINUS } from "../lib/format";
import { BANDS, BAND_ORDER, PILLARS, type Band, type RangeKey, PRESETS, activePreset, cloneFilters, hasPrismParams, withPreset } from "../lib/scoreScreen";
import { EXPLAIN } from "../lib/scorePrism";
import "../styles/scorescreen.css";

/** Basic score screener (Silver): the whole company universe with the FinLit score, the basic model. Informational; not a recommendation.
 *  The FinLit Prism rating has its own page, the Advanced score screener (Gold). Old shared links that carry Prism filters go there. */
export function ScoreScreener() {
  const [params] = useSearchParams();
  if (hasPrismParams(params)) return <Navigate to={"/advanced-score-screener" + (params.toString() ? "?" + params.toString() : "")} replace />;
  return <Basic />;
}

const RANGES: [RangeKey, string][] = [["f", "Fundamental score"], ["t", "Technical score"], ["o", "Overall score"]];

function Basic() {
  useDocTitle("Basic score screener", "Every listed company with its FinLit score, the basic model: filter, sort, compare and export by size, sector and score.");
  const s = useScreener("basic");
  const { draft, setDraft, applied, locked, upgrade, isLoading, sum, items, unscored, asOf } = s;
  const preset = activePreset(applied);
  const allStrong = PILLARS.every((x) => draft.bands[x.k].length === 1 && draft.bands[x.k][0] === "high");
  const setAllStrong = () => setDraft((d) => ({ ...d, bands: { ...d.bands, ...Object.fromEntries(PILLARS.map((x) => [x.k, allStrong ? [] : ["high"]])) } }));
  const usePreset = (id: string) => {
    if (locked) { upgrade("silver", "Score filters come with the Silver plan."); return; }
    s.apply(preset === id ? { ...cloneFilters(draft), bands: { ...draft.bands, f: [], t: [] } } : withPreset(draft, PRESETS.find((p) => p.id === id)!));
  };

  const tiles: [string, string, string?][] = [
    ["Companies found", isLoading ? "…" : nf(sum.found, 0)],
    ["Sectors", isLoading ? "…" : nf(sum.sectors, 0)],
    ["Median Fundamental", med(sum.medF) ?? MINUS, sum.medF == null ? (locked ? "Scores are part of the Silver plan" : "No company in this result has a Fundamental score") : `Middle value of ${nf(sum.nF, 0)} companies with a Fundamental score`],
    ["Median Technical", med(sum.medT) ?? MINUS, sum.medT == null ? (locked ? "Scores are part of the Silver plan" : "No company in this result has a Technical score") : `Middle value of ${nf(sum.nT, 0)} companies with a Technical score`],
    ["Active filters", nf(s.filterCount, 0)],
  ];

  return (
    <ScreenerFrame s={s} splitKey="score" eyebrow="Score screener" title="Basic score screener" sideLabel="Score screener filters" errorTitle="The score screener is unavailable right now"
      intro={<>Every listed company with its FinLit score, the basic model: Fundamental, its four pillars, Technical and Overall. Filter, sort, compare and export by size, sector and score. Need more rules? Use the <Link to="/screener">full screener</Link>.</>}
      tier="silver" sortChoices={[{ key: "overall", label: "FinLit score" }, { key: "f", label: "Fundamental" }, { key: "t", label: "Technical" }, ...PILLARS.map((x) => ({ key: x.col, label: x.label }))]}
      donut={!isLoading && items.length > 0 ? <Donut part={items.length - unscored} total={items.length} partLabel="Scored" restLabel="Not scored" title={unscored > 0 ? `${nf(unscored, 0)} of ${nf(items.length, 0)} companies are not scored yet.` : `All ${nf(items.length, 0)} companies are scored.`} note="Scoring fills in every night, or open a company's report to score it now." /> : undefined}
      presets={<div className="sx-presets" role="group" aria-label="Quick views by score band">
        {PRESETS.map((p) => <QuickRow key={p.id} label={<>{locked && <Icon name="lock" />} {p.label}</>} on={preset === p.id} title={p.say} onClick={() => usePreset(p.id)} />)}
      </div>}
      filters={locked ? (
        <FilterGroup id="score" title="Score filters" defaultOpen>
          <div className="scr-lock"><b><Icon name="lock" /> Score filters are part of Silver</b><span>See and filter by Fundamental, Technical and Overall scores.</span>
            <button type="button" className="btn primary" onClick={() => upgrade("silver", "Score filters come with the Silver plan.")}>Unlock with Silver</button></div>
        </FilterGroup>
      ) : (<>
        <FilterGroup id="score" title="Score filters" defaultOpen active={RANGES.filter(([k]) => draft.ranges[k].min != null || draft.ranges[k].max != null).length} hint="Tick a score, then set the lowest and highest value (0 to 100).">
          {RANGES.map(([k, label]) => <RangeRow key={k} label={label} group={`${label.replace(" score", "")} score, exact range`} min={draft.ranges[k].min} max={draft.ranges[k].max} error={s.problems[k]} onChange={(end, v) => s.setRange(k, end, v)} />)}
        </FilterGroup>
        <FilterGroup id="bands" title="Score bands" defaultOpen active={draft.bands.f.length + draft.bands.t.length}>
          {(["f", "t"] as const).map((k) => <ChipRow key={k} label={k === "f" ? "Fundamental" : "Technical"} group={`${k === "f" ? "Fundamental" : "Technical"} score`} onToggle={(b) => s.setBand(k, b as Band)}
            chips={BAND_ORDER.map((b) => ({ key: b, text: BANDS[b].short, on: draft.bands[k].includes(b), aria: BANDS[b].label }))} />)}
        </FilterGroup>
        <FilterGroup id="pillars" title="Fundamental by pillar" defaultOpen active={PILLARS.reduce((n, x) => n + draft.bands[x.k].length, 0)} hint="Select a range for each pillar">
          <button type="button" className={"fgx-chip fgx-all" + (allStrong ? " is-on" : "")} aria-pressed={allStrong} onClick={setAllStrong}>{allStrong && <i aria-hidden="true">&#10003;</i>}Strong on all four (78 and above)</button>
          {PILLARS.map((x) => <ChipRow key={x.k} label={x.label} title={x.say} onToggle={(b) => s.setBand(x.k, b as Band)}
            chips={BAND_ORDER.map((b) => ({ key: b, text: BANDS[b].short, on: draft.bands[x.k].includes(b), aria: `${x.label} ${BANDS[b].label}` }))} />)}
        </FilterGroup>
      </>)}
      tiles={tiles}
      lead={<Link to="/advanced-score-screener" className="sx-adv">
        <span className="sx-adv-t"><TierChip tier="gold" /><b>Advanced score screener</b></span>
        <span className="sx-adv-s">Advanced score screener (Gold): FinLit Prism, 4 fundamental parts and 2 technical views</span>
        <Icon name="arrow" /></Link>}
      beforeTable={<>
        <details className="pzs-explain">
          <summary>What the FinLit score means</summary>
          <div className="pzs-two"><div><b>FinLit score</b><p>{EXPLAIN.finlit}</p></div></div>
        </details>
      </>}
      groupHead={<tr className="gh"><th scope="col" colSpan={6} className="sr-only-th"><span className="sr">Company</span></th><th scope="colgroup" colSpan={7}>FinLit score</th><th scope="col"><span className="sr">Actions</span></th></tr>}
      columnHeads={<>
        <SortTh s={s} k="f" label="Fundamental" help="score-table" />
        {PILLARS.map((x) => <SortTh key={x.k} s={s} k={x.col} label={x.short} cls="ss-ph" title={x.say} />)}
        <SortTh s={s} k="t" label="Technical" /><SortTh s={s} k="overall" label="Overall" />
      </>}
      colSpan={14}
      cells={(r) => <>
        <td><Score r={r} k="f" locked={locked} /></td>
        {PILLARS.map((x) => <td key={x.k} className="ss-pc"><Score r={r} k={x.col} locked={locked} /></td>)}
        <td><Score r={r} k="t" locked={locked} /></td><td><Score r={r} k="overall" locked={locked} /></td>
      </>}
      plain="A score screen narrows a long list. It describes financial health and price trend from filings and prices; it is not a recommendation. Open a company's report to see why a score looks the way it does."
      how={<HowDialog onClose={() => s.setHow(false)}>
        <p>Every score runs from 0 to 100 and is worked out from a company's filed statements and its prices. Nothing on this page is computed differently from the company's own report page.</p>
        <dl>
          <dt>Fundamental</dt><dd>The average of four business pillars, rounded to a whole number: Quality (steady earnings, cash that matches profit), Growth (sales and profit growth over 3 to 5 years), Profitability (margins and returns on capital) and Balance sheet (debt, interest cover, liquidity). It needs at least 3 of the 4 pillars; with fewer it shows a dash.</dd>
          <dt>Technical</dt><dd>The technical pillar: how the price is trending against its 50 and 200 day averages, and its momentum.</dd>
          <dt>Overall</dt><dd>The FinLit overall score shown on every company page: the average of the pillar scores that are available, rounded to a whole number.</dd>
          <dt>Bands</dt><dd>Strong 78 and above, Healthy 62 to 77, Mixed 45 to 61, Watch under 45. The filter groups Healthy and Mixed together as 45 to 77. Bands use whole numbers: 44 is Watch, 45 is Mixed, 77 is Healthy, 78 is Strong.</dd>
          <dt>Size</dt><dd>Follows SEBI's rule, ranked by market value among the companies loaded here: the 100 largest are Large cap, the next 150 Mid cap, the rest Small cap.</dd>
          <dt>Missing data</dt><dd>A dash or a lock means the figure is not available (not scored yet, not enough data, or not in your plan). It never counts as a pass and is never treated as zero.</dd>
          <dt>Data date</dt><dd>{asOf ? <>Newest scores were computed on {dateIN(asOf)}. </> : <>The score date is not available right now. </>}Scores refresh every night; prices come from the latest market refresh.</dd>
          <dt>FinLit Prism</dt><dd>The advanced model has its own page, the <Link to="/advanced-score-screener">Advanced score screener</Link> (Gold).</dd>
        </dl>
      </HowDialog>} />
  );
}
