import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { COMPANY } from "../content/site";
import { useUI } from "../lib/ui";
import { Icon } from "../lib/icons";
import { Tape } from "./Tape";
import { SearchPalette } from "./SearchPalette";
import { Assistant } from "./Assistant";
import { EnquiryProvider, useEnquiry } from "./Enquiry";
import { InfoProvider } from "./Info";
import { DEMO } from "../lib/demo";
import { useAuth } from "../lib/auth";

const NAV = [
  ["/research", "Research"], ["/services", "Services"], ["/plans", "Plans"], ["/portfolio", "Portfolio"], ["/blog", "Blog"], ["/about", "About"],
] as const;
const TOOLS = [["/screener", "Stock screener", "Filter every company by your rules", "table"], ["/compare", "Compare companies", "Side by side, in charts", "layers"], ["/watchlist", "Watchlist", "Your lists, bucketed", "wallet"], ["/glossary", "Glossary", "95 terms in plain words", "notes"]] as const;

function Header({ onSearch }: { onSearch: () => void }) {
  const { theme, toggleTheme, plan, setPlan } = useUI();
  const { user, ready, isAdmin, signOut } = useAuth();
  const nav = useNavigate();
  const [acct, setAcct] = useState(false);
  const [menu, setMenu] = useState(false);
  const [tools, setTools] = useState(false);
  const loc = useLocation();
  const onStock = loc.pathname.startsWith("/stocks/");
  useEffect(() => { setMenu(false); setTools(false); setAcct(false); }, [loc.pathname]);
  return (
    <header className="top">
      <div className="wrap">
        <Link className="logo" to="/" aria-label="FinLit home"><span className="lg-mark" role="img" aria-label="FinLit" /></Link>
        <nav className="topnav" aria-label="Site">
          {NAV.slice(0, 1).map(([to, label]) => <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "hl" : "")}>{label}</NavLink>)}
          <div className="dd"><button className={"ddb" + (TOOLS.some(([to]) => loc.pathname.startsWith(to)) ? " hl" : "")} aria-haspopup="true" aria-expanded={tools} onClick={() => setTools(!tools)} onBlur={(e) => { if (!e.currentTarget.parentElement?.contains(e.relatedTarget as Node)) setTools(false); }}>Tools<Icon name="arrow" /></button>
            <div className={"ddm" + (tools ? " open" : "")} role="menu">{TOOLS.map(([to, label, sub, ic]) => <Link key={to} to={to} role="menuitem" onClick={() => setTools(false)}><span className="ddi"><Icon name={ic} /></span><span><b>{label}</b><small>{sub}</small></span></Link>)}</div></div>
          {NAV.slice(1).map(([to, label]) => <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "hl" : "")}>{label}</NavLink>)}
        </nav>
        <div className="grow" />
        <button className="search" onClick={onSearch} aria-label="Search stocks" aria-haspopup="dialog">
          <Icon name="table" /><span className="t">Search any stock</span><span className="kbd">Ctrl K</span>
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
        <button className="icon-btn burger" aria-label="Menu" aria-expanded={menu} onClick={() => setMenu((m) => !m)}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 7h16M4 12h16M4 17h16" /></svg></button>
      </div>
      {menu && (
        <nav className="mnav" aria-label="Mobile">
          {NAV.map(([to, label]) => <NavLink key={to} to={to}>{label}</NavLink>)}
          {TOOLS.map(([to, label]) => <NavLink key={to} to={to}>{label}</NavLink>)}
          <Link to="/contact">Contact</Link>{user ? <><NavLink to="/dashboard">Dashboard</NavLink><NavLink to="/account">Account</NavLink></> : <Link to="/login" className="gold">Sign in</Link>}
        </nav>
      )}
    </header>
  );
}

function Footer() {
  const enquire = useEnquiry();
  return (
    <footer className="band">
      <div className="wrap">
        <div className="fcta">
          <div><span className="lg-mark" role="img" aria-label="FinLit" style={{ marginBottom: 18 }} /><h2>Have a question about your portfolio?</h2><p>Talk to the FinLit research team.</p></div>
          <button className="btn primary" onClick={() => enquire()}>Get in touch</button>
        </div>
        <div className="fcols">
          <div><b>Explore</b><Link to="/research">Stock research</Link><Link to="/services">Services</Link><Link to="/plans">Plans</Link><Link to="/portfolio">Portfolio</Link><Link to="/blog">Blog</Link></div>
          <div><b>Company</b><Link to="/about">About</Link><Link to="/why-we-exist">Why we exist</Link><Link to="/contact">Contact</Link><a href={COMPANY.linkedin} target="_blank" rel="noopener noreferrer">LinkedIn</a></div>
          <div><b>Legal</b><Link to="/legal/terms">Terms</Link><Link to="/legal/privacy">Privacy</Link><Link to="/legal/disclosures">Research disclosures</Link><Link to="/admin/login">CMS admin</Link></div>
        </div>
        <div className="ffine">
          <span>{COMPANY.name} · Research-led perspectives across Indian and global markets.</span>
          <span>{COMPANY.disclaimer}</span>
          <span>© {new Date().getFullYear()} {COMPANY.name}. All rights reserved.</span>
        </div>
      </div>
    </footer>
  );
}

export function Layout() {
  const [search, setSearch] = useState(false);
  const loc = useLocation();
  useEffect(() => { if (!loc.hash) window.scrollTo({ top: 0 }); }, [loc.pathname, loc.hash]);
  useEffect(() => {
    // soft glow that follows the pointer on cards (one delegated listener)
    const mv = (e: PointerEvent) => {
      const el = (e.target as Element | null)?.closest<HTMLElement>(".feat, .bt .spot"); if (!el) return;
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
        <main id="main"><Outlet /></main>
        {!bare && <Footer />}
        <SearchPalette open={search} onClose={() => setSearch(false)} />
        <Assistant />
      </EnquiryProvider>
    </InfoProvider>
  );
}
