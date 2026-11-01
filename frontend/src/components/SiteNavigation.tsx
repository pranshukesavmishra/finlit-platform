import { useEffect, useRef } from "react";
import { Link, NavLink } from "react-router";
import { HEADER_MORE, HEADER_SECTIONS, PRICING, isHere, sectionHere, type NavSection } from "../lib/nav";
import { Icon } from "../lib/icons";

/** Click/keyboard disclosure navigation. Visibility follows React state, never CSS hover. */
export function HeaderMenu({ section, open, setOpen, path }: { section: NavSection; open: boolean; setOpen: (id: string | null) => void; path: string }) {
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const panelId = `site-nav-${section.id}`;
  useEffect(() => {
    if (!open) return;
    const outside = (e: PointerEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(null); };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open, setOpen]);
  return <div ref={root} className="site-menu" onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOpen(null); }} onKeyDown={(e) => {
    if (e.key === "Escape" && open) { e.preventDefault(); e.stopPropagation(); setOpen(null); trigger.current?.focus(); }
  }}>
    <button ref={trigger} className={"ddb" + (sectionHere(path, section) ? " hl" : "")} aria-expanded={open} aria-controls={panelId} onClick={() => setOpen(open ? null : section.id)}>{section.label}<Icon name="arrow" /></button>
    <div id={panelId} className="site-nav-panel" data-menu={section.id} hidden={!open} aria-label={`${section.label} navigation`}>
      {section.groups.map((group, n) => <div key={group.title ?? n} className="site-nav-group">{group.title && <p className="site-nav-group-title">{group.title}</p>}{group.items.map((item) => <Link key={item.to} to={item.to} className={isHere(path, item) ? "here" : undefined} aria-current={isHere(path, item) ? "page" : undefined} onClick={() => setOpen(null)}><span className="site-nav-icon"><Icon name={item.icon} /></span><span><b>{item.label}{item.gold && <em className="gtag">Gold</em>}</b><small>{item.sub}</small></span></Link>)}</div>)}
    </div>
  </div>;
}

/** Native block disclosures keep every destination readable and reachable in the scrollable phone menu. */
export function MobileNavigation({ signedIn, onClose }: { signedIn: boolean; onClose: () => void }) {
  const links = (section: NavSection) => section.groups.map((group, n) => {
    const items = <div className="mobile-nav-links">{group.items.filter(item => item.to !== "/dashboard").map(item => <NavLink key={item.to} to={item.to} end={item.end}>{item.label}{item.gold && <em className="gtag">Gold</em>}</NavLink>)}</div>;
    return group.title ? <details className="mobile-nav-subsection" key={group.title}><summary>{group.title}<Icon name="arrow" /></summary>{items}</details> : <div className="mobile-nav-group" key={n}>{items}</div>;
  });
  const section = (s: NavSection) => <details key={s.id} className="mobile-nav-section"><summary>{s.label}<Icon name="arrow" /></summary><div className="mobile-nav-content">{links(s)}</div></details>;
  return <nav id="mobile-site-navigation" className="mobile-site-navigation" aria-label="Mobile" onClick={e => { if ((e.target as Element).closest("a")) onClose(); }}>
    {signedIn && <NavLink className="mobile-nav-dashboard" to="/dashboard">Dashboard<Icon name="arrow" /></NavLink>}
    {HEADER_SECTIONS.map(section)}
    <NavLink className="mobile-nav-direct" to="/services">Services</NavLink>
    <NavLink className="mobile-nav-direct" to={PRICING.to}>{PRICING.label}</NavLink>
    {section(HEADER_MORE)}
    <div className="mobile-nav-account">{signedIn ? <NavLink to="/account">Account</NavLink> : <><Link to="/login">Sign in</Link><Link to="/login?mode=signup">Create free account</Link></>}<button onClick={() => { onClose(); dispatchEvent(new Event("finlit:help")); }}>Help and assistant</button></div>
  </nav>;
}
