// The category chooser of /funds: six quick cards, the fund-type tabs and the sub-category tick boxes with "Select All". State lives in the address.
import { useEffect, useRef } from "react";
import { Link } from "react-router";
import { Icon } from "../lib/icons";
import { useUI } from "../lib/ui";
import { useCategoryScores } from "../lib/mfScore";
import { cardScoreView, scoreSortHref, type CardScoreView } from "../lib/mfScoreDash";
import { bandInk } from "../lib/scoreBands";
import { toggleAll, toggleCat, type ListQuery, type SubCat } from "../lib/mf";
import { CARDS, TABS, type Card, type TabKey } from "../lib/mfCategories";

/** The Health score strip of a card: the median of the category's scored Direct-plan funds, how they split into the three colour bands, and a link to the list in that order. */
function ScoreStrip({ v, card }: { v: CardScoreView; card: Card }) {
  if (v.kind === "locked") return <div className="mf-qscore"><span className="mf-qs-lock"><Icon name="lock" /><span>Health score: part of the Gold plan</span></span></div>;
  if (v.kind === "loading") return <div className="mf-qscore" aria-busy="true"><span className="skeleton" style={{ height: 40 }} /></div>;
  if (v.kind === "unavailable") return <div className="mf-qscore"><span>The Health score is not available right now.</span></div>;
  if (v.kind === "notRun") return <div className="mf-qscore"><span><b>Health score:</b> Not scored yet</span></div>;
  if (v.kind === "none") return <div className="mf-qscore"><span><b>Health score:</b> no Direct-plan fund of this category is scored yet</span><Link to={scoreSortHref(card)}>See the funds</Link></div>;
  const { green, orange, red } = v.shares;
  return (
    <div className="mf-qscore" role="group" aria-label={v.label}>
      <div className="mf-qs-h"><span className="mf-qs-t">Health score, median</span><b className="mf-qs-n" style={{ color: bandInk(v.band) }}>{v.median}</b><span className="mf-qs-t">of {v.n.toLocaleString("en-IN")} scored fund{v.n === 1 ? "" : "s"}</span></div>
      <div className="mf-qdist" aria-hidden="true">{green > 0 && <i className="g" style={{ flex: green }} />}{orange > 0 && <i className="o" style={{ flex: orange }} />}{red > 0 && <i className="r" style={{ flex: red }} />}</div>
      <div className="mf-qdist-l" aria-hidden="true"><span className="g">{green}% green</span><span className="o">{orange}% orange</span><span className="r">{red}% red</span></div>
      <Link to={scoreSortHref(card)}>See these funds by Health score</Link>
    </div>
  );
}

/** One card per popular category; the pressed one is the category shown on its own. Under each card, for Gold, the category's Health score. */
export function CategoryCards({ q, onPick }: { q: ListQuery; onPick: (c: Card) => void }) {
  const { has } = useUI();
  const canSee = has("gold");
  const sc = useCategoryScores(canSee);
  return (
    <section aria-label="Popular categories">
      <ul className="mf-cards">
        {CARDS.map((c) => {
          const on = q.tab === c.tab && q.cats?.length === 1 && q.cats[0] === c.key;
          const v = cardScoreView(c.key, sc.data, { canSee, loading: sc.isLoading, failed: sc.isError });
          return (
            <li key={c.key}>
              <div className="mf-qwrap">
                <button type="button" className="mf-qcard" aria-pressed={on} onClick={() => onPick(c)}>
                  <span className="ci" aria-hidden="true"><Icon name={c.icon} /></span>
                  <b>{c.title}</b>
                  <span>{c.lines[0]}</span>
                  <span title={c.note}>{c.lines[1]}{c.note && <><sup aria-hidden="true">*</sup><span className="sr-only"> ({c.note})</span></>}</span>
                </button>
                <ScoreStrip v={v} card={c} />
              </div>
            </li>);
        })}
      </ul>
    </section>
  );
}

function SelectAll({ all, some, n, onChange }: { all: boolean; some: boolean; n: number; onChange: () => void }) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { if (ref.current) ref.current.indeterminate = some && !all; }, [some, all]);
  return <label className="mf-check mf-all"><input ref={ref} type="checkbox" checked={all} onChange={onChange} /> <span>Select All ({n})</span></label>;
}

/** Equity | Hybrid | Debt | Solution Oriented | Others (and All funds), and under the chosen tab its sub-categories with how many schemes each shows. */
export function CategoryPicker({ q, subs, loading, onTab, onCats }: {
  q: ListQuery; subs: SubCat[]; loading: boolean; onTab: (t: TabKey | "all") => void; onCats: (c: string[] | null) => void;
}) {
  const tabs: { key: TabKey | "all"; label: string }[] = [...TABS, { key: "all", label: "All funds" }];
  const keys = subs.map((s) => s.key);
  const on = (k: string) => q.cats === null || q.cats.includes(k);
  const onTabKey = (e: React.KeyboardEvent, i: number) => {   // arrow keys move between the tabs, as a tab list should
    const d = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!d) return;
    e.preventDefault();
    const next = tabs[(i + d + tabs.length) % tabs.length].key;
    onTab(next);
    requestAnimationFrame(() => document.getElementById(`mf-tab-${next}`)?.focus());
  };
  return (
    <section className="card mf-catpick" aria-label="Choose categories">
      <div className="mf-tabs" role="tablist" aria-label="Type of fund">
        {tabs.map((t, i) => (
          <button key={t.key} id={`mf-tab-${t.key}`} type="button" role="tab" aria-selected={q.tab === t.key} aria-controls="mf-subcats" tabIndex={q.tab === t.key ? 0 : -1}
            onClick={() => onTab(t.key)} onKeyDown={(e) => onTabKey(e, i)}>{t.label}</button>))}
      </div>
      <div id="mf-subcats" role="tabpanel" aria-labelledby={`mf-tab-${q.tab}`} className="mf-subcats">
        {q.tab === "all" ? <p className="muted mf-fine">Every category: search and filter all mutual fund schemes AMFI lists.</p>
          : loading && !subs.length ? <div className="skeleton" style={{ height: 96 }} aria-busy="true" />
            : !subs.length ? <p className="muted mf-fine">No schemes in this group for the plan and option chosen below.</p> : (
              <fieldset>
                <legend className="sr-only">Sub-categories to show</legend>
                <SelectAll all={q.cats === null} some={!!q.cats?.length} n={subs.length} onChange={() => onCats(toggleAll(q.cats))} />
                <div className="mf-subgrid">
                  {subs.map((s) => (
                    <label key={s.key} className="mf-check" title={s.names.join(" · ")}>
                      <input type="checkbox" checked={on(s.key)} onChange={() => onCats(toggleCat(q.cats, s.key, keys))} />
                      <span>{s.label}</span><small>{s.count.toLocaleString("en-IN")}</small>
                    </label>))}
                </div>
              </fieldset>)}
      </div>
    </section>
  );
}
