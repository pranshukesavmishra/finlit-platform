import { useEffect, useState } from "react";
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
import { Assistant } from "./Assistant";
import { EnquiryProvider, useEnquiry } from "./Enquiry";
import { InfoProvider } from "./Info";
import { DEMO } from "../lib/demo";
import { useAuth } from "../lib/auth";

type Item = readonly [to: string, label: string, sub: string, icon: string];
/** The company site map: what we sell (Products, Services, Pricing), what we publish (Resources) and who we are (Company). */
export const MENUS: { label: string; wide?: boolean; groups: { title?: string; items: Item[] }[] }[] = [
  { label: "Products", wide: true, groups: [
    { title: "Research", items: [["/graphs", "Graph Studio", "Combine metrics in side-by-side charts", "bars"], ["/graphs/advanced", "Advanced charts", "Correlations with tested regression lines", "spark"], ["/research", "Stock research", "A report for every listed company", "search"], ["/screener", "Screener", "Filter every company by your rules", "table"], ["/score-screener", "Score screener", "Size, sector and score ranges, simply", "quality"], ["/compare", "Compare companies", "Side by side, in charts", "compare"], ["/etfs", "ETFs", "Exchange-traded funds: price, returns and risk", "bars"], ["/funds", "Mutual funds", "NAV, returns and risk for every scheme", "pie"], ["/funds/insights", "Mutual Fund Insights", "Industry AUM, net flows and folios, monthly", "line"], ["/premium", "Gold dashboards", "Fundamentals, market events, premium reports", "crown"]] },
    { title: "Your workspace", items: [["/watchlist", "Watchlists", "Follow stocks in named lists", "wallet"], ["/sip-calculator", "SIP calculator", "Plan a monthly investment, free", "spark"], ["/dcf", "DCF calculator", "Intrinsic value, margin of safety (Gold)", "rupee"], ["/holdings", "Portfolio tracker", "Value, profit and loss, allocation", "pie"], ["/alerts", "Alerts", "Price, signals, scores and filings", "bell"]] },
    { title: "Market", items: [["/commodities", "Commodity prices", "Gold, silver, crude and metals: MCX, global and import parity", "activity"], ["/macro", "India macro insights", "Inflation, growth, rates, reserves", "activity"], ["/fii-dii", "FII/DII data", "Institutional buying and selling, streaks, history", "bars"], ["/results", "Results calendar", "Who reports and when", "calendar"], ["/results/quarter", "Quarter results", "Every company, newest first", "notes"], ["/ipo", "IPO calendar", "Open, upcoming and listed", "activity"], ["/news", "News & filings", "Exchange filings and headlines", "notes"]] },
  ] },
  { label: "Resources", groups: [{ items: [["/forum", "Discussion forums", "Talk about listed companies: information and opinion only, moderated", "users"], ["/blog", "Insights & blog", "Research notes and explainers", "spark"], ["/glossary", "Glossary", "313 terms in plain words, with formulas", "book"], ["/documents", "Documents", "Annual reports and presentations", "layers"]] }] },
  { label: "Company", groups: [{ items: [["/about", "About FinLit", "Who we are and how we work", "users"], ["/why-we-exist", "Why we exist", "The problem we set out to fix", "quality"], ["/contact", "Contact", "Talk to the team", "notes"]] }] },
];
const TOP: [string, string][] = [["/services", "Services"], ["/plans", "Pricing"]];

function Menu({ m, open, setOpen, path }: { m: (typeof MENUS)[number]; open: boolean; setOpen: (v: string | null) => void; path: string }) {
  const here = m.groups.some((g) => g.items.some(([to]) => path === to || path.startsWith(to + "/")));
  return (
    <div className="dd" onMouseLeave={() => open && setOpen(null)}>
      <button className={"ddb" + (here ? " hl" : "")} aria-haspopup="true" aria-expanded={open} onClick={() => setOpen(open ? null : m.label)} onKeyDown={(e) => e.key === "Escape" && setOpen(null)}
        onBlur={(e) => { if (!e.currentTarget.parentElement?.contains(e.relatedTarget as Node)) setOpen(null); }}>{m.label}<Icon name="arrow" /></button>
      <div className={"ddm" + (open ? " open" : "") + (m.wide ? " wide" : "")} role="menu">
        {m.groups.map((g, i) => (
          <div className="ddg" key={i}>{g.title && <span className="ddt">{g.title}</span>}
            {g.items.map(([to, label, sub, ic]) => <Link key={to} to={to} role="menuitem" onClick={() => setOpen(null)}><span className="ddi"><Icon name={ic} /></span><span><b>{label}</b><small>{sub}</small></span></Link>)}</div>
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
          {MENUS.slice(0, 1).map((m) => <Menu key={m.label} m={m} open={open === m.label} setOpen={setOpen} path={loc.pathname} />)}
          {TOP.map(([to, label]) => <NavLink key={to} to={to} className={({ isActive }) => (isActive ? "hl" : "")}>{label}</NavLink>)}
          {MENUS.slice(1).map((m) => <Menu key={m.label} m={m} open={open === m.label} setOpen={setOpen} path={loc.pathname} />)}
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
        <button className="icon-btn burger" aria-label="Menu" aria-expanded={menu} onClick={() => setMenu((m) => !m)}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 7h16M4 12h16M4 17h16" /></svg></button>
      </div>
      {menu && (
        <nav className="mnav" aria-label="Mobile">
          {MENUS.map((m) => <div key={m.label} className="mg"><span className="mt">{m.label}</span>{m.groups.flatMap((g) => g.items).map(([to, label]) => <NavLink key={to} to={to}>{label}</NavLink>)}</div>)}
          <div className="mg"><span className="mt">More</span>{TOP.map(([to, label]) => <NavLink key={to} to={to}>{label}</NavLink>)}</div>
          <div className="mg">{user ? <><NavLink to="/dashboard">Dashboard</NavLink><NavLink to="/account">Account</NavLink></> : <><Link to="/login">Sign in</Link><Link to="/login?mode=signup" className="gold">Create free account</Link></>}</div>
        </nav>
      )}
    </header>
  );
}

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
          <div><b>Products</b><Link to="/research">Stock research</Link><Link to="/screener">Screener</Link><Link to="/score-screener">Score screener</Link><Link to="/compare">Compare</Link><Link to="/premium">Gold dashboards</Link><Link to="/watchlist">Watchlists</Link><Link to="/macro">India macro</Link><Link to="/commodities">Commodity prices</Link><Link to="/fii-dii">FII/DII data</Link><Link to="/sip-calculator">SIP calculator</Link><Link to="/dcf">DCF calculator</Link><Link to="/alerts">Alerts</Link><Link to="/holdings">Portfolio tracker</Link></div>
          <div><b>Market</b><Link to="/results">Results calendar</Link><Link to="/results/quarter">Quarter results</Link><Link to="/ipo">IPO calendar</Link><Link to="/news">News &amp; filings</Link><Link to="/documents">Documents</Link><Link to="/plans">Pricing</Link></div>
          <div><b>Company</b><Link to="/about">About</Link><Link to="/why-we-exist">Why we exist</Link><Link to="/services">Services</Link><Link to="/blog">Blog</Link><Link to="/contact">Contact</Link></div>
          <div><b>Legal</b><Link to="/legal/terms">Terms</Link><Link to="/legal/privacy">Privacy</Link><Link to="/legal/disclosures">Research disclosures</Link>{!user && <Link to="/login">Sign in</Link>}</div>
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
