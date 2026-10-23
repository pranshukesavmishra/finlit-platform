// The category chooser of /funds: six quick cards, the fund-type tabs and the sub-category tick boxes with "Select All". State lives in the address.
import { useEffect, useRef } from "react";
import { Icon } from "../lib/icons";
import { toggleAll, toggleCat, type ListQuery, type SubCat } from "../lib/mf";
import { CARDS, TABS, type Card, type TabKey } from "../lib/mfCategories";

/** One card per popular category; the pressed one is the category shown on its own. */
export function CategoryCards({ q, onPick }: { q: ListQuery; onPick: (c: Card) => void }) {
  return (
    <section aria-label="Popular categories">
      <ul className="mf-cards">
        {CARDS.map((c) => {
          const on = q.tab === c.tab && q.cats?.length === 1 && q.cats[0] === c.key;
          return (
            <li key={c.key}>
              <button type="button" className="mf-qcard" aria-pressed={on} onClick={() => onPick(c)}>
                <span className="ci" aria-hidden="true"><Icon name={c.icon} /></span>
                <b>{c.title}</b>
                <span>{c.lines[0]}</span>
                <span title={c.note}>{c.lines[1]}{c.note && <><sup aria-hidden="true">*</sup><span className="sr-only"> ({c.note})</span></>}</span>
              </button>
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
