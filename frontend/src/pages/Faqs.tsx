import { Link } from "react-router";
import { PAGE_FAQS } from "../content/pageFaqs";
import { faqHref } from "../lib/pageFaqs";
import { FaqAccordion, FaqPlan } from "../components/PageFaqs";
import { useDocTitle } from "../lib/title";

/** Every page's questions in one place, grouped as the sidebar groups the pages. Each page's own set also sits at the bottom of that page. */
export function FaqsPage() {
  useDocTitle("All FAQs", "Questions and answers for every FinLit page, grouped by section. Information only, not investment advice.");
  const sections = [...new Set(PAGE_FAQS.map((f) => f.section))];
  return (
    <div className="wrap pfq-hub">
      <header className="pfq-hub-h">
        <span className="pfq-k">FAQs</span>
        <h1>Questions about every page</h1>
        <p>{PAGE_FAQS.reduce((n, f) => n + f.items.length, 0)} questions for {PAGE_FAQS.length} pages. Each page also shows its own questions at the bottom. Information only, not investment advice.</p>
        <nav aria-label="Sections" className="pfq-jump">{sections.map((s) => <a key={s} href={"#sec-" + s.toLowerCase().replace(/\W+/g, "-")}>{s}</a>)}</nav>
      </header>
      {sections.map((s) => (
        <section key={s} id={"sec-" + s.toLowerCase().replace(/\W+/g, "-")} className="pfq-sec" aria-label={s}>
          <h2 className="pfq-sech">{s}</h2>
          {PAGE_FAQS.filter((f) => f.section === s).map((f) => (
            <div key={f.id} id={f.id} className="pfq-pg">
              <div className="pfq-pgh"><h3><Link to={faqHref(f)}>{f.title}</Link> <small>{f.items.length} questions</small></h3><FaqPlan plan={f.plan} /></div>
              <FaqAccordion faq={f} level={4} />
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}
