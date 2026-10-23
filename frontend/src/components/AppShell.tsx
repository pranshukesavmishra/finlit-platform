import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import { Icon } from "../lib/icons";
import { useAuth } from "../lib/auth";
import { TIER, useUI } from "../lib/ui";
import { useSavedScreens } from "../lib/screens";
import { useWatchlist } from "../lib/watchlist";
import { usePortfolio } from "../lib/portfolio";
import { DEMO } from "../lib/demo";
import { useAlerts, useNotices } from "../lib/alerts";

type Item = { to: string; label: string; icon: string; badge?: string; end?: boolean };
type Group = { title: string; items: Item[] };

/** The left rail for every product page: where you are, what you follow, and what else the platform offers, in the order people use it. */
export function AppShell() {
  const { pathname } = useLocation();
  const { user, isAdmin } = useAuth();
  const { plan } = useUI();
  const wl = useWatchlist();
  const saved = useSavedScreens();
  const held = usePortfolio().holdings.length;
  const { unread } = useNotices();
  const live = useAlerts().alerts.filter((a) => a.status === "active").length;
  const [collapsed, setCollapsed] = useState(() => { try { return localStorage.getItem("finlit-side") === "1"; } catch { return false; } });
  const [open, setOpen] = useState(false); // mobile drawer
  useEffect(() => { setOpen(false); }, [pathname]);
  useEffect(() => { try { localStorage.setItem("finlit-side", collapsed ? "1" : "0"); } catch { /* private mode */ } }, [collapsed]);
  useEffect(() => { if (!open) return; const k = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false); addEventListener("keydown", k); return () => removeEventListener("keydown", k); }, [open]);
  const followed = new Set(wl.lists.flatMap((l) => l.symbols)).size;

  const groups: Group[] = [
    { title: "Overview", items: [
      { to: "/dashboard", label: "Dashboard", icon: "home" },
      { to: "/dcf", label: "DCF calculator", icon: "rupee" },
    ] },
    { title: "Research", items: [
      { to: "/research", label: "Stock research", icon: "search" },
      { to: "/screener", label: "Screener", icon: "table", badge: saved.length ? String(saved.length) : undefined },
      { to: "/score-screener", label: "Score screener", icon: "quality" },
      { to: "/compare", label: "Compare companies", icon: "compare" },
      { to: "/graphs", label: "Graph Studio", icon: "bars" },
      { to: "/etfs", label: "ETFs", icon: "activity" },
      { to: "/funds", label: "Mutual funds", icon: "pie" },
    ] },
    { title: "Gold dashboards", items: [
      { to: "/premium/fundamentals", label: "Stock fundamentals", icon: "table" },
      { to: "/premium/markets", label: "Market events & index", icon: "activity" },
      { to: "/premium/report", label: "Premium report", icon: "notes" },
    ] },
    { title: "My lists", items: [
      { to: "/watchlist", label: "Watchlist", icon: "wallet", badge: followed ? String(followed) : undefined },
      { to: "/holdings", label: "My portfolio", icon: "pie", badge: held ? String(held) : undefined },
      { to: "/alerts", label: "Alerts", icon: "bell", badge: unread ? `${unread} new` : live ? String(live) : undefined },
    ] },
    { title: "Market", items: [
      { to: "/results", label: "Results calendar", icon: "calendar", end: true },
      { to: "/results/quarter", label: "Quarter results", icon: "notes" },
      { to: "/ipo", label: "IPO calendar", icon: "activity" },
      { to: "/news", label: "News & filings", icon: "notes" },
      { to: "/documents", label: "Documents", icon: "layers" },
    ] },
    { title: "Learn", items: [{ to: "/glossary", label: "Glossary", icon: "book" }, { to: "/blog", label: "Insights & blog", icon: "spark" }] },
    ...(user ? [{ title: "Account", items: [
      { to: "/account", label: "Profile & security", icon: "users", end: true },
      { to: "/account/appearance", label: "Appearance", icon: "spark" },
      ...(DEMO ? [] : [{ to: "/account/plan", label: "Plan", icon: "crown" }]),
      ...(isAdmin ? [{ to: "/console", label: "Admin console", icon: "lock" }] : []),
    ] }] : []),
  ];

  return (
    <div className={"shell" + (collapsed ? " is-collapsed" : "") + (open ? " is-open" : "")}>
      <button className="shell-fab" onClick={() => setOpen(true)} aria-label="Open the product menu" aria-expanded={open}><Icon name="panel" /><span>Menu</span></button>
      {open && <div className="shell-scrim" onClick={() => setOpen(false)} aria-hidden="true" />}
      <aside className="side" aria-label="Product navigation">
        <div className="side-top">
          <span className="side-t">Workspace</span>
          <button className="side-toggle hide-sm" onClick={() => setCollapsed(!collapsed)} aria-label={collapsed ? "Expand the side menu" : "Collapse the side menu"} aria-pressed={collapsed} title={collapsed ? "Expand" : "Collapse"}><Icon name="panel" /></button>
          <button className="side-toggle show-sm" onClick={() => setOpen(false)} aria-label="Close the product menu">✕</button>
        </div>
        <nav>
          {groups.map((g) => (
            <div className="side-g" key={g.title}>
              <div className="side-gt">{g.title}</div>
              {g.items.map((i) => (
                <NavLink key={i.to} to={i.to} end={i.end ?? false} className={({ isActive }) => "side-i" + (isActive ? " on" : "")} title={collapsed ? i.label : undefined}>
                  <span className="side-ic"><Icon name={i.icon} /></span><span className="side-l">{i.label}</span>{i.badge && <span className="side-b">{i.badge}</span>}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="side-foot">
          <div className="side-plan" style={{ "--tc": `var(${TIER[plan].tc})` } as React.CSSProperties}>
            <span className={"tier " + plan}><Icon name={TIER[plan].ic} />{TIER[plan].n}</span>
            {plan !== "gold" ? <><p>{plan === "basic" ? "Unlock the FinLit score, watchlists and more." : "Gold adds advanced scoring and deeper analysis."}</p><Link className="btn primary" to={user ? "/account/plan?want=" + (plan === "basic" ? "silver" : "gold") : "/plans"}>{plan === "basic" ? "See Silver" : "See Gold"}</Link></> : <p>Everything is unlocked.</p>}
          </div>
        </div>
      </aside>
      <div className="shell-main"><Outlet /></div>
    </div>
  );
}
