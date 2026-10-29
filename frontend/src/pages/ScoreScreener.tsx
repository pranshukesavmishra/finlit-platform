import { Link, Navigate, useSearchParams } from "react-router";
import { ScreenerFrame, SortTh } from "../components/screener/ScreenerFrame";
import { BandBoxes, HowDialog, RangeBox } from "../components/screener/controls";
import { Score, med } from "../components/screener/cells";
import { useScreener } from "../components/screener/useScreener";
import { ChartHelp } from "../components/ChartHelp";
import { TierChip } from "../components/Gate";
import { Icon } from "../lib/icons";
import { useDocTitle } from "../lib/title";
import { nf, dateIN, MINUS } from "../lib/format";
import { BANDS, BAND_ORDER, PILLARS, PRESETS, activePreset, cloneFilters, hasPrismParams, withPreset } from "../lib/scoreScreen";
import { EXPLAIN } from "../lib/scorePrism";
import "../styles/scorescreen.css";

/** Basic score screener (Silver): the whole company universe with the FinLit score, the basic model. Informational; not a recommendation.
 *  The FinLit Prism rating has its own page, the Advanced score screener (Gold). Old shared links that carry Prism filters go there. */
export function ScoreScreener() {
  const [params] = useSearchParams();
  if (hasPrismParams(params)) return <Navigate to={"/advanced-score-screener" + (params.toString() ? "?" + params.toString() : "")} replace />;
  return <Basic />;
}

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
      presets={<>
        <div className="label">Quick views <ChartHelp id="score-filter" /></div>
        <div className="sx-presets" role="group" aria-label="Quick views by score band">
          {PRESETS.map((p) => <button key={p.id} type="button" className={"bandc" + (preset === p.id ? " on" : "")} aria-pressed={preset === p.id} title={p.say} onClick={() => usePreset(p.id)}>{locked && <Icon name="lock" />} {p.label}</button>)}
        </div>
      </>}
      filters={<>
        <div className="label" style={{ marginTop: 18, display: "flex", justifyContent: "space-between" }}>Score filters<button type="button" className="alx-link" onClick={() => s.setHow(true)}><Icon name="info" /> How scores work</button></div>
        {locked ? (
          <div className="scr-lock"><b><Icon name="lock" /> Score filters are part of Silver</b><span>See and filter by Fundamental, Technical and Overall scores.</span>
            <button type="button" className="btn primary" onClick={() => upgrade("silver", "Score filters come with the Silver plan.")}>Unlock with Silver</button></div>
        ) : (<>
          <BandBoxes s={s} k="f" label="Fundamental" />
          <fieldset className="ss-fs ss-pil"><legend>Fundamental, by pillar</legend>
            <button type="button" className={"bandc ss-all" + (allStrong ? " on" : "")} aria-pressed={allStrong} onClick={setAllStrong}>Strong on all four (78 and above)</button>
            {PILLARS.map((x) => (
              <div key={x.k} className="ss-prow" role="group" aria-label={`${x.label} score`}>
                <span className="ss-pn" title={x.say}>{x.label}</span>
                <span className="ss-seg">{BAND_ORDER.map((b) => (
                  <button key={b} type="button" className={"ss-sb " + b + (draft.bands[x.k].includes(b) ? " on" : "")} aria-pressed={draft.bands[x.k].includes(b)} aria-label={`${x.label} ${BANDS[b].label}`} onClick={() => s.setBand(x.k, b)}>{BANDS[b].short}</button>))}</span>
              </div>))}
          </fieldset>
          <BandBoxes s={s} k="t" label="Technical" />
          <fieldset className="ss-fs"><legend>Overall score</legend><RangeBox s={s} k="o" label="Overall" /></fieldset>
        </>)}
      </>}
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
        {!isLoading && unscored > 0 && <p className="muted" role="note">{nf(unscored, 0)} of {nf(items.length, 0)} listed companies are not scored yet. Scoring fills in every night, or open a company's report to score it now.</p>}
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
