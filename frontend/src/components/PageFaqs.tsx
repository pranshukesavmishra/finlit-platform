import { useEffect, useId, useRef, useState } from "react";
import { Link, useLocation } from "react-router";
import type { PageFaq } from "../content/pageFaqs";
import { faqForPath } from "../lib/pageFaqs";

/** Stable deep-link id of one question: #faq-<set id>-<number>. */
export const faqAnchor = (setId: string, i: number) => `faq-${setId}-${i + 1}`;

/** The questions of one page as an accordion: real buttons with aria-expanded and aria-controls, several can be open; Tab/Enter/Space toggle, Up/Down/Home/End move between questions.
 *  A #faq-<id>-<n> address opens and scrolls to that question. `only` limits the list to some questions (hub search), `force` opens every shown answer. */
export function FaqAccordion({ faq, openFirst = false, level = 3, only, force = false, bulk = true }: { faq: PageFaq; openFirst?: boolean; level?: 3 | 4; only?: Set<string>; force?: boolean; bulk?: boolean }) {
  const H = ("h" + level) as "h3" | "h4";
  const uid = useId();
  const { hash } = useLocation();
  const root = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState<Set<string>>(() => new Set(openFirst ? [faq.items[0].q] : []));
  const shown = faq.items.map((it, i) => ({ it, i })).filter(({ it }) => !only || only.has(it.q));
  const flip = (q: string) => setOpen((s) => { const n = new Set(s); if (n.has(q)) n.delete(q); else n.add(q); return n; });
  const allOn = shown.length > 0 && shown.every(({ it }) => force || open.has(it.q));
  const setAll = (on: boolean) => setOpen((s) => { const n = new Set(s); for (const { it } of shown) { if (on) n.add(it.q); else n.delete(it.q); } return n; });
  useEffect(() => {
    const m = /^#faq-(.+)-(\d+)$/.exec(hash);
    if (!m || m[1] !== faq.id) return;
    const it = faq.items[Number(m[2]) - 1];
    if (!it) return;
    setOpen((s) => (s.has(it.q) ? s : new Set(s).add(it.q)));
    const t = setTimeout(() => document.getElementById(faqAnchor(faq.id, Number(m[2]) - 1))?.scrollIntoView({ behavior: "smooth", block: "center" }), 150);
    return () => clearTimeout(t);
  }, [hash, faq]);
  const onKey = (e: React.KeyboardEvent) => {
    const keys = ["ArrowDown", "ArrowUp", "Home", "End"];
    if (!keys.includes(e.key)) return;
    const qs = [...(root.current?.querySelectorAll<HTMLButtonElement>("button.pfq-q") ?? [])];
    const at = qs.indexOf(e.target as HTMLButtonElement);
    if (at < 0) return;
    e.preventDefault();
    const to = e.key === "Home" ? 0 : e.key === "End" ? qs.length - 1 : (at + (e.key === "ArrowDown" ? 1 : -1) + qs.length) % qs.length;
    qs[to]?.focus();
  };
  return (
    <div className="pfq-list" ref={root} onKeyDown={onKey}>
      {bulk && shown.length > 1 && !force && <div className="pfq-bulk"><button type="button" className="pfq-all" onClick={() => setAll(!allOn)}>{allOn ? "Collapse all" : "Expand all"}</button></div>}
      {shown.map(({ it, i }) => {
        const on = force || open.has(it.q), bid = `${uid}-q${i}`, pid = `${uid}-a${i}`;
        return (
          <div key={it.q} id={faqAnchor(faq.id, i)} className={"pfq-i" + (on ? " on" : "")}>
            <H><button type="button" id={bid} className="pfq-q" aria-expanded={on} aria-controls={pid} onClick={() => flip(it.q)}>
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
