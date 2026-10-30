import { useEffect, useId, useState } from "react";
import { Link, useLocation } from "react-router";
import type { PageFaq } from "../content/pageFaqs";
import { faqForPath } from "../lib/pageFaqs";

/** The questions of one page as an accordion: real buttons with aria-expanded and aria-controls, several can be open, Tab/Enter/Space work. */
export function FaqAccordion({ faq, openFirst = false, level = 3 }: { faq: PageFaq; openFirst?: boolean; level?: 3 | 4 }) {
  const H = ("h" + level) as "h3" | "h4";
  const uid = useId();
  const [open, setOpen] = useState<Set<number>>(() => new Set(openFirst ? [0] : []));
  const flip = (i: number) => setOpen((s) => { const n = new Set(s); if (n.has(i)) n.delete(i); else n.add(i); return n; });
  return (
    <div className="pfq-list">
      {faq.items.map((it, i) => {
        const on = open.has(i), bid = `${uid}-q${i}`, pid = `${uid}-a${i}`;
        return (
          <div key={it.q} className={"pfq-i" + (on ? " on" : "")}>
            <H><button type="button" id={bid} className="pfq-q" aria-expanded={on} aria-controls={pid} onClick={() => flip(i)}>
              <span>{it.q}</span>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
            </button></H>
            <div id={pid} role="region" aria-labelledby={bid} className="pfq-a"><div><p>{it.a}</p></div></div>
          </div>
        );
      })}
    </div>
  );
}

export const FaqPlan = ({ plan }: { plan?: string }) => plan ? <span className={"pfq-plan " + plan.split(/[ ,]/)[0].toLowerCase()}>Plan: {plan}</span> : null;

/** "Questions about this page": shown at the bottom of every page that has a set in content/pageFaqs.ts, chosen by the address. Nothing otherwise. */
export function PageFaqs() {
  const { pathname, hash } = useLocation();
  const faq = faqForPath(pathname);
  useEffect(() => { if (faq && hash === "#faq") setTimeout(() => document.getElementById("faq")?.scrollIntoView({ behavior: "smooth" }), 150); }, [faq, hash]);
  if (!faq) return null;
  // first question open on a wide screen, all closed on a phone
  const wide = typeof matchMedia === "function" && matchMedia("(min-width: 721px)").matches;
  return (
    <section className="pfq pm-noprint pzr-noprint" id="faq" aria-labelledby="pfq-h" key={faq.id}>
      <div className="pfq-in">
        <header className="pfq-h">
          <div>
            <span className="pfq-k">Questions about this page</span>
            <h2 id="pfq-h">{faq.title} <small>{faq.items.length} questions</small></h2>
          </div>
          <FaqPlan plan={faq.plan} />
        </header>
        <FaqAccordion faq={faq} openFirst={wide} />
        <footer className="pfq-f"><span>Information only, not investment advice.</span><Link to="/faq">All FAQs</Link></footer>
      </div>
    </section>
  );
}
