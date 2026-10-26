import { Fragment, useEffect, useState } from "react";
import { initDepth } from "../lib/depth";
import { ErrorBoundary } from "./ErrorBoundary";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { COMPANY } from "../content/site";
import { useUI } from "../lib/ui";
import { Icon } from "../lib/icons";
import { Tape } from "./Tape";
import { SearchPalette } from "./SearchPalette";
import { useWarmMyCompanies } from "../lib/mycompanies";
import { AlertToasts, NotificationBell } from "./Notifications";
import { SystemControl } from "./SystemControl";
import { Assistant } from "./Assistant";
import { EnquiryProvider, useEnquiry } from "./Enquiry";
import { InfoProvider } from "./Info";
import { DEMO } from "../lib/demo";
import { useAuth } from "../lib/auth";
import { MORE, PRICING, SECTIONS, isHere, sectionHere, type NavSection } from "../lib/nav";

/** One header dropdown, built from lib/nav.ts. */
function Menu({ m, open, setOpen, path }: { m: NavSection; open: boolean; setOpen: (v: string | null) => void; path: string }) {
  const here = sectionHere(path, m);
  return (
    <div className="dd" onMouseLeave={() => open && setOpen(null)}>
      <button className={"ddb" + (here ? " hl" : "")} aria-haspopup="true" aria-expanded={open} onClick={() => setOpen(open ? null : m.id)} onKeyDown={(e) => e.key === "Escape" && setOpen(null)}
        onBlur={(e) => { if (!e.currentTarget.parentElement?.contains(e.relatedTarget as Node)) setOpen(null); }}>{m.label}<Icon name="arrow" /></button>
      <div className={"ddm" + (open ? " open" : "") + (m.wide ? " wide" : "") + (m.id === "more" ? " right" : "") + (m.groups.length === 1 && !m.groups[0].title ? " solo" : "")} role="menu">
        {m.groups.map((g, gi) => (
          <div className="ddg" key={gi}>{g.title && <span className="ddt">{g.title}</span>}
            {g.items.map((it) => <Link key={it.to} to={it.to} role="menuitem" className={isHere(path, it) ? "here" : undefined} aria-current={isHere(path, it) ? "page" : undefined} onClick={() => setOpen(null)}>
              <span className="ddi"><Icon name={it.icon} /></span><span><b>{it.label}{it.gold && <em className="gtag">Gold</em>}</b><small>{it.sub}</small></span></Link>)}</div>
        ))}
      </div>
    </div>
  );
}

function Header({ onSearch }: { onSearch: () => void }) {
  const { theme, toggleTheme, plan, setPlan } = useUI();
  const { user, ready, isAdmin, signOut } = useAuth();
  const nav = useNavigate();
  const [acct, setAcct] = useState(false);
  const [menu, setMenu] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const loc = useLocation();
  const onStock = loc.pathname.startsWith("/stocks/");
  useEffect(() => { setMenu(false); setOpen(null); setAcct(false); }, [loc.pathname]);
  useEffect(() => { const o = () => setMenu((m) => !m); addEventListener(OPEN_MENU, o); return () => removeEventListener(OPEN_MENU, o); }, []);
  return (
    <header className="top">
      <div className="wrap">
        <Link className="logo" to="/" aria-label="FinLit home"><span className="lg-mark" role="img" aria-label="FinLit" /></Link>
        <nav className="topnav" aria-label="Site">
          {SECTIONS.map((m) => <Menu key={m.id} m={m} open={open === m.id} setOpen={setOpen} path={loc.pathname} />)}
          <NavLink to={PRICING.to} className={({ isActive }) => (isActive ? "hl" : "")}>{PRICING.label}</NavLink>
          <Menu m={MORE} open={open === MORE.id} setOpen={setOpen} path={loc.pathname} />
        </nav>
        <div className="grow" />
        <button className="search" onClick={onSearch} aria-label="Search stocks" aria-haspopup="dialog">
          <Icon name="table" /><span className="t">Search stocks, funds, ETFs</span><span className="kbd">Ctrl K</span>
        </button>
        {DEMO && onStock && (
          <div className="seg planseg" role="group" aria-label="Preview plan">
            <span className="lbl">Preview</span>
            {(["basic", "silver", "gold"] as const).map((p) => (
              <button key={p} aria-pressed={plan === p} style={{ "--tc": `var(--t-${p})` } as React.CSSProperties} onClick={() => setPlan(p)}><i />{p[0].toUpperCase() + p.slice(1)}</button>
            ))}
          </div>
        )}
        <button className="icon-btn" onClick={toggleTheme} aria-label={theme === "light" ? "Switch to dark theme" : "Switch to light theme"}>
          {theme === "light" ? <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5Z" /></svg>
            : <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>}
        </button>
        {isAdmin && <SystemControl />}
        {user && <NotificationBell />}
        {user ? (
          <div className="dd acct-dd">
            <button className="av-btn" aria-haspopup="true" aria-expanded={acct} aria-label={`Account menu for ${user.email}`} onClick={() => setAcct(!acct)} onBlur={(e) => { if (!e.currentTarget.parentElement?.contains(e.relatedTarget as Node)) setAcct(false); }}>
              <span className="av sm" aria-hidden="true">{(user.name || user.email)[0].toUpperCase()}</span><span className={"tier " + plan}>{plan[0].toUpperCase() + plan.slice(1)}</span>
            </button>
            <div className={"ddm right" + (acct ? " open" : "")} role="menu">
              <div className="acct-who"><b>{user.name || "Signed in"}</b><small>{user.email}</small></div>
              <Link to="/dashboard" role="menuitem"><span className="ddi"><Icon name="table" /></span><span><b>Dashboard</b></span></Link>
              <Link to="/watchlist" role="menuitem"><span className="ddi"><Icon name="wallet" /></span><span><b>Watchlist</b></span></Link>
              <Link to="/account" role="menuitem"><span className="ddi"><Icon name="users" /></span><span><b>Account</b></span></Link>
              <Link to="/account/appearance" role="menuitem"><span className="ddi"><Icon name="spark" /></span><span><b>Appearance</b></span></Link>
              {isAdmin && <Link to="/console" role="menuitem"><span className="ddi"><Icon name="lock" /></span><span><b>Admin console</b></span></Link>}
              {!DEMO && <button role="menuitem" onClick={async () => { setAcct(false); await signOut(); nav("/"); }}><span className="ddi"><Icon name="arrow" /></span><span><b>Sign out</b></span></button>}
            </div>
          </div>
        ) : ready || DEMO ? (
          <><Link className="btn hide-sm signin-ghost" to="/login">Sign in</Link><Link className="btn primary hide-sm signin" to={DEMO ? "/login" : "/login?mode=signup"}>{DEMO ? "Sign in" : "Create account"}</Link></>
        ) : <span className="signin-ph" aria-hidden="true" />}
        {user ? <Link className="btn primary mob-only mob-cta" to="/dashboard">Dashboard</Link> : (ready || DEMO) ? <Link className="btn primary mob-only mob-cta" to="/login">Sign in</Link> : null}
        <button className="icon-btn burger" aria-label="Menu" aria-expanded={menu} onClick={() => setMenu((m) => !m)}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 7h16M4 12h16M4 17h16" /></svg></button>
      </div>
      {menu && (
        <nav className="mnav" aria-label="Mobile">
          {user && <div className="mg mg-first"><NavLink to="/dashboard" className="mdash">Dashboard</NavLink></div>}
          {[...SECTIONS, MORE].map((m) => <div key={m.id} className="mg"><span className="mt">{m.label}</span>
            {m.groups.map((g, gi) => <Fragment key={gi}>{g.title && m.id !== "more" && <span className="mt2">{g.title}</span>}{g.title && m.id === "more" && <span className="mt2">{g.title}</span>}
              {g.items.map((it) => <NavLink key={it.to} to={it.to} end={it.end}>{it.label}{it.gold && <em className="gtag">Gold</em>}</NavLink>)}</Fragment>)}</div>)}
          <div className="mg"><NavLink to={PRICING.to}>{PRICING.label}</NavLink>{user ? <><NavLink to="/dashboard">Dashboard</NavLink><NavLink to="/account">Account</NavLink></> : <><Link to="/login">Sign in</Link><Link to="/login?mode=signup" className="gold">Create free account</Link></>}</div>
        </nav>
      )}
    </header>
  );
}

const pick = (id: string) => SECTIONS.find((x) => x.id === id)!.groups.flatMap((g) => g.items);
const FOOT: { title: string; items: { to: string; label: string }[] }[] = [
  { title: "Research", items: pick("research") },
  { title: "Markets and news", items: [...pick("markets"), ...pick("news")] },
  { title: "Funds and Workspace", items: [...pick("funds"), ...pick("myfinlit")] },
];

function Footer() {
  const enquire = useEnquiry();
  const { user } = useAuth();
  return (
    <footer className="band">
      <div className="wrap">
        <div className="fcta">
          <div><span className="lg-mark" role="img" aria-label="FinLit" style={{ marginBottom: 18 }} /><h2>Follow the numbers, not the noise.</h2><p>Open a free account to follow stocks, set alerts and read the research reports we have built so far.</p></div>
          <div className="cta-row">{!user && <Link className="btn primary" to="/login?mode=signup">Create free account</Link>}<button className="btn" onClick={() => enquire()}>Talk to the team</button></div>
        </div>
        <div className="fcols fcols5">
          <div className="fbrand"><b>{COMPANY.name}</b><p>Research and tools for Indian stocks. We are a technology company and are not registered with SEBI or AMFI.</p>
            <a href={`mailto:${COMPANY.email}`}>{COMPANY.email}</a><a href={COMPANY.linkedin} target="_blank" rel="noopener noreferrer">LinkedIn</a></div>
          {FOOT.map((col) => <div key={col.title}><b>{col.title}</b>{col.items.map((it) => <Link key={it.to} to={it.to}>{it.label}</Link>)}</div>)}
          <div><b>Company</b><Link to="/about">About</Link><Link to="/why-we-exist">Why we exist</Link><Link to="/services">Services</Link><Link to="/plans">Pricing</Link><Link to="/blog">Blog</Link><Link to="/forum">Forums</Link><Link to="/glossary">Glossary</Link><Link to="/contact">Contact</Link>
            <Link to="/legal/terms">Terms</Link><Link to="/legal/privacy">Privacy</Link><Link to="/legal/disclosures">Research disclosures</Link>{!user && <Link to="/login">Sign in</Link>}</div>
        </div>
        <div className="ffine">
          <span>{COMPANY.disclaimer} Market data may be delayed. Past performance does not indicate future results.</span>
          <span>© {new Date().getFullYear()} {COMPANY.name}<br /><Link to="/legal/terms">Terms</Link> · <Link to="/legal/privacy">Privacy</Link> · <Link to="/legal/disclosures">Disclosures</Link></span>
        </div>
      </div>
    </footer>
  );
}

const OPEN_MENU = "finlit:open-menu", OPEN_SIDE = "finlit:open-side";

/** Phones: an app-style bar along the bottom, so the main places are one thumb-tap away and the header can stay small.
 *  "Menu" opens the product drawer on pages that have one, the site menu everywhere else. */
function MobileTabs({ onSearch }: { onSearch: () => void }) {
  const { user } = useAuth();
  const home = user ? "/dashboard" : "/";
  const menu = () => dispatchEvent(new Event(document.querySelector(".shell") ? OPEN_SIDE : OPEN_MENU));
  const tab = (to: string, icon: string, label: string, end = false) =>
    <NavLink to={to} end={end} className={({ isActive }) => "mt-i" + (isActive ? " on" : "")}><Icon name={icon} /><span>{label}</span></NavLink>;
  return (
    <nav className="mtabs" aria-label="Quick navigation">
      {tab(home, "home", user ? "Dashboard" : "Home", true)}
      {tab("/research", "quality", "Research")}
      <button type="button" className="mt-i mt-search" onClick={onSearch} aria-label="Search stocks, funds and ETFs"><span className="mt-orb"><Icon name="search" /></span><span>Search</span></button>
      {tab("/screener", "table", "Screener")}
      <button type="button" className="mt-i" onClick={menu} aria-label="Open the menu"><Icon name="panel" /><span>Menu</span></button>
    </nav>
  );
}

export function Layout() {
  useWarmMyCompanies();
  const [search, setSearch] = useState(false);
  const loc = useLocation();
  useEffect(() => { if (!loc.hash) window.scrollTo({ top: 0 }); }, [loc.pathname, loc.hash]);
  useEffect(() => initDepth(), []);
  useEffect(() => {
    // soft glow that follows the pointer on cards (one delegated listener)
    const mv = (e: PointerEvent) => {
      const el = (e.target as Element | null)?.closest<HTMLElement>(".feat, .bt .spot, .card, .mk-tile"); if (!el) return;
      const r = el.getBoundingClientRect(); el.style.setProperty("--mx", `${e.clientX - r.left}px`); el.style.setProperty("--my", `${e.clientY - r.top}px`);
    };
    document.addEventListener("pointermove", mv, { passive: true });
    return () => document.removeEventListener("pointermove", mv);
  }, []);
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      const typing = /input|textarea|select/i.test((document.activeElement as HTMLElement | null)?.tagName || "");
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setSearch(true); }
      else if (e.key === "/" && !typing) { e.preventDefault(); setSearch(true); }
    };
    addEventListener("keydown", k); return () => removeEventListener("keydown", k);
  }, []);
  const bare = ["/login", "/forgot-password", "/reset-password", "/verify-email"].includes(loc.pathname);
  return (
    <InfoProvider>
      <EnquiryProvider>
        <a className="skip" href="#main">Skip to content</a>
        {DEMO && <div className="demo-bar" role="note"><b>Demo preview</b> · saved sample data, no servers. Forms are not sent. The live site loads every stock.</div>}
        <Tape />
        <Header onSearch={() => setSearch(true)} />
        <main id="main"><ErrorBoundary key={loc.pathname}><Outlet /></ErrorBoundary></main>
        {!bare && <Footer />}
        <SearchPalette open={search} onClose={() => setSearch(false)} />
        <AlertToasts />
        <Assistant />
        {!bare && <MobileTabs onSearch={() => setSearch(true)} />}
      </EnquiryProvider>
    </InfoProvider>
  );
}
