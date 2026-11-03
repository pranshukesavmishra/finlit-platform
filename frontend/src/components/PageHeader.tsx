// The heading of every feature page: plan badge, serif title (the page's one h1), a short description, quick links to the related pages,
// up to three key-figure tiles and a line illustration. Styles: styles/page-header.css (class prefix ph-).
//   plan         "free" | "silver" | "gold" (or "basic", the same as "free"): the plan that gates the page. Leave out when the page is open to everyone and not a plan feature.
//   stats        tiles { icon, value, label }. A tile is drawn only when its value is real data (not null / empty / NaN / a dash): never a placeholder number.
//   links        up to four related pages, as addresses ("/score-screener") or { to, label?, primary? }. Each must exist in lib/nav.ts (or the short extras list in
//                lib/pageHeader.ts), takes its name from there, and is left out when it does not: a quick link can never be broken.
//   learn        true (the default): scroll to the page's own questions (#faq) when it has some, else no button. false: none. { to } opens a page (methodology), { onClick } runs a handler, label renames the button.
//   art          one of 12 line illustrations; hidden under 760 px.
//   back / meta / actions / children   a back link or breadcrumb above the title, a note under the description ("Updated ..."), extra buttons after the links, and anything
//                that sits in the header (tabs, notices) below the row.
//   wrap         draw the page container around the card (for pages that had a full-width .pagehead band).
import { useId, type ReactNode } from "react";
import { Link, useInRouterContext, useLocation } from "react-router";
import { Icon } from "../lib/icons";
import { faqForPath } from "../lib/pageFaqs";
import { realValue, resolveLinks, type PhLink } from "../lib/pageHeader";
import { PageArt, type PhArtKind } from "./PageHeaderArt";
import "../styles/page-header.css";

export type PhPlan = "free" | "basic" | "silver" | "gold";
export type PhStat = { icon: string; value: ReactNode; label: string };
export type PhLearn = { to?: string; onClick?: () => void; label?: string };
export type PageHeaderProps = {
  plan?: PhPlan; title: ReactNode; description?: ReactNode; eyebrow?: ReactNode;
  stats?: PhStat[]; links?: PhLink[]; learn?: boolean | PhLearn; art?: PhArtKind;
  back?: ReactNode; meta?: ReactNode; actions?: ReactNode; children?: ReactNode; wrap?: boolean; className?: string; id?: string;
};

const PLAN: Record<string, { n: string; ic: string; cls: string }> = {
  free: { n: "Free", ic: "sprout", cls: "free" }, basic: { n: "Free", ic: "sprout", cls: "free" },
  silver: { n: "Silver", ic: "medal", cls: "silver" }, gold: { n: "Gold", ic: "crown", cls: "gold" },
};

/** A router link, or a plain anchor when the header is drawn outside a router (previews, tests). */
function HLink({ to, className, children }: { to: string; className: string; children: ReactNode }) {
  return useInRouterContext() ? <Link to={to} className={className}>{children}</Link> : <a href={to} className={className}>{children}</a>;
}

export function PageHeader({ plan, title, description, eyebrow, stats, links, learn = true, art, back, meta, actions, children, wrap, className = "", id }: PageHeaderProps) {
  const uid = useId(), tid = id ?? "ph-t" + uid.replace(/:/g, "");
  const inRouter = useInRouterContext();   // the header also renders on its own (tests, previews): plain anchors then
  const pathname = inRouter ? useLocation().pathname : (typeof window !== "undefined" ? window.location.pathname : "/");   // eslint-disable-line react-hooks/rules-of-hooks
  // the figure tiles and the line illustration are no longer drawn (they said nothing the page does not already say); the props stay so no page has to change
  const tiles: PhStat[] = [];
  void stats; void art; void realValue;
  const btns = resolveLinks(links, 4);
  const hasFaq = learn === true && !!faqForPath(pathname);
  const lo: PhLearn | null = learn === true ? (hasFaq ? {} : null) : learn ? learn : null;
  const label = lo?.label ?? "Learn more";
  const p = plan ? PLAN[plan] : undefined;
  const sided = false;
  const learnEl = !lo ? null : lo.to
    ? <HLink className="ph-learn" to={lo.to}><Icon name="info" />{label}</HLink>
    : lo.onClick
      ? <button type="button" className="ph-learn ph-link-btn" onClick={lo.onClick}><Icon name="info" />{label}</button>
      : <a className="ph-learn" href="#faq" onClick={(e) => { const el = document.getElementById("faq"); if (el) { e.preventDefault(); el.scrollIntoView?.({ behavior: typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" }); } }}><Icon name="info" />{label}</a>;
  const card = (
    <section className={"ph" + (sided ? "" : " ph-solo") + (className ? " " + className : "")} aria-labelledby={tid} data-plan={plan ?? undefined}>
      <div className="ph-main">
        {back ? <div className="ph-back">{back}</div> : null}
        {(p || eyebrow) ? <div className="ph-top">{p ? <span className={"ph-plan " + p.cls}><Icon name={p.ic} />{p.n}</span> : null}{eyebrow ? <span className="ph-eyebrow">{eyebrow}</span> : null}</div> : null}
        <h1 className="ph-title" id={tid}>{title}</h1>
        {description ? <p className="ph-desc">{description}</p> : null}
        {meta ? <p className="ph-meta">{meta}</p> : null}
        {(btns.length > 0 || learnEl || actions) ? (
          <div className="ph-row">
            {btns.length > 0 ? <nav className="ph-links" aria-label="Related pages" style={{ display: "contents" }}>
              {btns.map((l) => <HLink key={l.to} to={l.to} className={"ph-lk" + (l.primary ? " primary" : "")}>{l.label}<span aria-hidden="true">→</span></HLink>)}
            </nav> : null}
            {actions}{learnEl}
          </div>) : null}
      </div>
      {sided ? (
        <div className="ph-side">
          {tiles.length > 0 ? <ul className="ph-stats" aria-label="Key figures">{tiles.map((s) => <li className="ph-stat" key={s.label}><span className="ph-si"><Icon name={s.icon} /></span><span className="ph-sv"><b>{s.value}</b><small>{s.label}</small></span></li>)}</ul> : null}
          {art ? <div className="ph-art-box"><PageArt kind={art} /></div> : null}
        </div>) : null}
      {children ? <div className="ph-sub">{children}</div> : null}
    </section>);
  return wrap ? <div className="wrap ph-wrap">{card}</div> : card;
}
