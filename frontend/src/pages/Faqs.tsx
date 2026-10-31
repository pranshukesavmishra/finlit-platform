import { useMemo, useState } from "react";
import { Link } from "react-router";
import { PAGE_FAQS } from "../content/pageFaqs";
import { faqHref } from "../lib/pageFaqs";
import { FaqAccordion, FaqPlan } from "../components/PageFaqs";
import { useDocTitle } from "../lib/title";

/** Every page's questions in one place, grouped as the sidebar groups the pages. Each page's own set also sits at the bottom of that page. */
export function FaqsPage() {
  useDocTitle("All FAQs", "Questions and answers for every FinLit page, grouped by section. Information only, not investment advice.");
  const sections = [...new Set(PAGE_FAQS.map((f) => f.section))];
  const total = PAGE_FAQS.reduce((n, f) => n + f.items.length, 0);
  const [qry, setQry] = useState("");
  const words = qry.toLowerCase().split(/\s+/).filter(Boolean);
  // per page: the questions whose text (or page title) contains every word; null query = everything
  const hits = useMemo(() => {
    const m = new Map<string, Set<string>>(); let n = 0;
    if (!words.length) return { m, n: -1 };
    for (const f of PAGE_FAQS) {
      const keep = new Set(f.items.filter((it) => { const t = (f.title + " " + it.q + " " + it.a).toLowerCase(); return words.every((w) => t.includes(w)); }).map((it) => it.q));
      if (keep.size) { m.set(f.id, keep); n += keep.size; }
    }
    return { m, n };
  }, [qry]); // eslint-disable-line react-hooks/exhaustive-deps
  const searching = hits.n >= 0;
  return (
    <div className="wrap pfq-hub">
      <header className="pfq-hub-h">
        <span className="pfq-k">FAQs</span>
        <h1>Questions about every page</h1>
        <p>{total} questions for {PAGE_FAQS.length} pages. Each page also shows its own questions at the bottom. Information only, not investment advice.</p>
        <div className="pfq-search" role="search">
          <label htmlFor="pfq-s" className="sr-only">Search the questions</label>
          <input id="pfq-s" type="search" value={qry} onChange={(e) => setQry(e.target.value)} placeholder="Search all questions" autoComplete="off" />
          <p className="pfq-count" role="status" aria-live="polite">{searching ? (hits.n ? `${hits.n} of ${total} questions match` : "No question matches. Try fewer or different words.") : ""}</p>
        </div>
        <nav aria-label="Sections" className="pfq-jump">{sections.map((s) => <a key={s} href={"#sec-" + s.toLowerCase().replace(/\W+/g, "-")}>{s}</a>)}</nav>
      </header>
      {sections.map((s) => (!searching || PAGE_FAQS.some((f) => f.section === s && hits.m.has(f.id))) && (
        <section key={s} id={"sec-" + s.toLowerCase().replace(/\W+/g, "-")} className="pfq-sec" aria-label={s}>
          <h2 className="pfq-sech">{s}</h2>
          {PAGE_FAQS.filter((f) => f.section === s && (!searching || hits.m.has(f.id))).map((f) => (
            <div key={f.id} id={f.id} className="pfq-pg">
              <div className="pfq-pgh"><h3><Link to={faqHref(f)}>{f.title}</Link> <small>{f.items.length} questions</small></h3><FaqPlan plan={f.plan} /></div>
              <FaqAccordion faq={f} level={4} only={searching ? hits.m.get(f.id) : undefined} force={searching} />
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}
