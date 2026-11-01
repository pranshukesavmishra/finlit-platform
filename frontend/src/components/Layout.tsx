import { useEffect, useRef, useState } from "react";
import { ErrorBoundary } from "./ErrorBoundary";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";
import { useUI } from "../lib/ui";
import { Icon } from "../lib/icons";
import { Tape } from "./Tape";
import { SearchPalette } from "./SearchPalette";
import { useWarmMyCompanies } from "../lib/mycompanies";
import { AlertToasts, NotificationBell } from "./Notifications";
import { SystemControl } from "./SystemControl";
import { Assistant } from "./Assistant";
import { PageFaqs } from "./PageFaqs";
import { EnquiryProvider } from "./Enquiry";
import { InfoProvider } from "./Info";
import { DEMO } from "../lib/demo";
import { useAuth } from "../lib/auth";
import { HEADER_MORE, HEADER_SECTIONS, PRICING } from "../lib/nav";
import { HeaderMenu, MobileNavigation } from "./SiteNavigation";
import { SiteFooter } from "./SiteFooter";

function Header({ onSearch }: { onSearch: () => void }) {
  const { theme, toggleTheme, plan, setPlan } = useUI();
  const { user, ready, isAdmin, signOut } = useAuth();
  const nav = useNavigate();
  const [acct, setAcct] = useState(false);
  const accountRoot = useRef<HTMLDivElement>(null);
  const [menu, setMenu] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const loc = useLocation();
  const onStock = loc.pathname.startsWith("/stocks/");
  const commercial = ["/", "/platform", "/services", "/plans", "/about"].includes(loc.pathname);
  useEffect(() => { setMenu(false); setOpen(null); setAcct(false); }, [loc.pathname]);
  useEffect(() => {
    if (!acct) return;
    const outside = (e: PointerEvent) => { if (!accountRoot.current?.contains(e.target as Node)) setAcct(false); };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [acct]);
  useEffect(() => {
    if (!menu) return;
    const close = (e: KeyboardEvent) => { if (e.key === "Escape") { setMenu(false); document.querySelector<HTMLButtonElement>(".burger")?.focus(); } };
    addEventListener("keydown", close); return () => removeEventListener("keydown", close);
  }, [menu]);
  useEffect(() => {
    const wide = matchMedia("(min-width: 1100px)");
    const close = () => { setMenu(false); setOpen(null); setAcct(false); };
    wide.addEventListener("change", close);
    return () => wide.removeEventListener("change", close);
  }, []);
  useEffect(() => { const o = () => setMenu((m) => !m); addEventListener(OPEN_MENU, o); return () => removeEventListener(OPEN_MENU, o); }, []);
  return (
    <header className={"top" + (commercial ? " top-commercial" : "")}>
      <div className="wrap">
        <Link className="logo" to="/" aria-label="FinLit home"><span className="lg-mark" role="img" aria-label="FinLit" /></Link>
        <nav className="topnav" aria-label="Site">
          {HEADER_SECTIONS.map((m) => <HeaderMenu key={m.id} section={m} open={open === m.id} setOpen={setOpen} path={loc.pathname} />)}
          <NavLink to="/services">Services</NavLink>
          <NavLink to={PRICING.to} className={({ isActive }) => (isActive ? "hl" : "")}>{PRICING.label}</NavLink>
          <HeaderMenu section={HEADER_MORE} open={open === HEADER_MORE.id} setOpen={setOpen} path={loc.pathname} />
        </nav>
        <div className="grow" />
        <button className="search" onClick={onSearch} aria-label="Search stocks" aria-haspopup="dialog">
          <Icon name="search" /><span className="t">Search stocks, funds, ETFs</span><span className="kbd">Ctrl K</span>
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
        {!["/login", "/forgot-password", "/reset-password", "/verify-email"].includes(loc.pathname) && <button className="icon-btn header-help" aria-label="Open help" onClick={() => dispatchEvent(new Event("finlit:help"))}><Icon name="info" /></button>}
        {isAdmin && <SystemControl />}
        {user && <NotificationBell />}
        {user ? (
          <div ref={accountRoot} className="dd acct-dd" onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setAcct(false); }} onKeyDown={e => {
            if (e.key === "Escape" && acct) { e.preventDefault(); setAcct(false); accountRoot.current?.querySelector<HTMLButtonElement>(".av-btn")?.focus(); }
          }}>
            <button className="av-btn" aria-haspopup="true" aria-expanded={acct} aria-label={`Account menu for ${user.email}`} onClick={() => setAcct(!acct)}>
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
          <Link className="btn primary hide-sm signin" to="/login">Sign in</Link>
        ) : <span className="signin-ph" aria-hidden="true" />}
        {!user && (ready || DEMO) ? <Link className="btn primary mob-only mob-cta" to="/login">Sign in</Link> : null}
        <button className="icon-btn burger" aria-label="Menu" aria-controls="mobile-site-navigation" aria-expanded={menu} onClick={() => setMenu((m) => !m)}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 7h16M4 12h16M4 17h16" /></svg></button>
      </div>
      {menu && <MobileNavigation signedIn={!!user} onClose={() => setMenu(false)} />}
    </header>
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

export function Layout({ workspace = false }: { workspace?: boolean }) {
  useWarmMyCompanies();
  const [search, setSearch] = useState(false);
  const loc = useLocation();
  useEffect(() => { if (!loc.hash) window.scrollTo({ top: 0 }); }, [loc.pathname, loc.hash]);
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      const typing = /input|textarea|select/i.test((document.activeElement as HTMLElement | null)?.tagName || "");
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setSearch(true); }
      else if (e.key === "/" && !typing) { e.preventDefault(); setSearch(true); }
    };
    addEventListener("keydown", k); return () => removeEventListener("keydown", k);
  }, []);
  const publicPage = ["/", "/services", "/platform", "/about", "/contact", "/why-we-exist", "/plans", "/faq", "/documents"].includes(loc.pathname) || /^\/(?:legal|blog)(?:\/|$)/.test(loc.pathname);
  const bare = ["/login", "/forgot-password", "/reset-password", "/verify-email"].includes(loc.pathname);
  return (
    <InfoProvider>
      <EnquiryProvider>
        <a className="skip" href="#main">Skip to content</a>
        {DEMO && <div className="demo-bar" role="note"><b>Demo preview</b> · saved sample data, no servers. Forms are not sent. The live site loads every stock.</div>}
        <Tape />
        <Header onSearch={() => setSearch(true)} />
        <main id="main" className={workspace ? "workspace-main" : undefined} data-page-kind={/^\/(?:stocks|research|dashboard|screener|score-screener|advanced-score-screener|prism|premium|graphs|compare|query-builder|funds|etfs|outlook|dcf|eps-calculator|sip-calculator|watchlist|holdings|alerts|account|results|news|ipo|macro|fii-dii|commodities|mf-portfolio|baskets)(?:\/|$)/.test(loc.pathname) ? "product" : "editorial"}><ErrorBoundary key={loc.pathname}><Outlet /></ErrorBoundary>{!workspace && !bare && loc.pathname !== "/" && loc.pathname !== "/platform" && <PageFaqs />}</main>
        {!bare && <SiteFooter />}
        <SearchPalette open={search} onClose={() => setSearch(false)} />
        <AlertToasts />
        {!bare && <Assistant />}
        {!bare && !publicPage && <MobileTabs onSearch={() => setSearch(true)} />}
      </EnquiryProvider>
    </InfoProvider>
  );
}
