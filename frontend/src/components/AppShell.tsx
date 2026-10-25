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
import { MORE, SECTIONS, type NavItem } from "../lib/nav";

type Item = { to: string; label: string; icon: string; badge?: string; end?: boolean; gold?: boolean; sub?: boolean };
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
  useEffect(() => { const o = () => setOpen((v) => !v); addEventListener("finlit:open-side", o); return () => removeEventListener("finlit:open-side", o); }, []);
  useEffect(() => { try { localStorage.setItem("finlit-side", collapsed ? "1" : "0"); } catch { /* private mode */ } }, [collapsed]);
  useEffect(() => { if (!open) return; const k = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false); addEventListener("keydown", k); return () => removeEventListener("keydown", k); }, [open]);
  const followed = new Set(wl.lists.flatMap((l) => l.symbols)).size;

  // The rail follows the site map (lib/nav.ts): the same five headings and groups as the header, plus the extras and the account.
  const badges: Record<string, string | undefined> = {
    "/screener": saved.length ? String(saved.length) : undefined, "/watchlist": followed ? String(followed) : undefined, "/holdings": held ? String(held) : undefined,
    "/alerts": unread ? `${unread} new` : live ? String(live) : undefined,
  };
  const toItem = (n: NavItem): Item => ({ to: n.to, label: n.label, icon: n.icon, end: n.end, gold: n.gold, badge: badges[n.to] });
  const mine = (id: string, extra: Item[] = []) => [...SECTIONS.find((x) => x.id === id)!.groups.flatMap((g) => g.items).map(toItem), ...extra];
  const groups: Group[] = [
    { title: "Overview", items: [{ to: "/dashboard", label: "Dashboard", icon: "home" }] },
    ...SECTIONS[0].groups.map((g) => ({ title: g.title || SECTIONS[0].label, items: g.items.map(toItem) })),
    { title: "Markets", items: mine("markets") },
    { title: "News & events", items: mine("news") },
    { title: "Funds", items: mine("funds") },
    { title: "My FinLit", items: mine("myfinlit", [{ to: "/baskets", label: "My baskets", icon: "layers" }]) },
    { title: MORE.groups[0].title!, items: MORE.groups[0].items.map(toItem) },
    { title: "Learn", items: [{ to: "/glossary", label: "Glossary", icon: "book" }, { to: "/blog", label: "Insights & blog", icon: "spark" }, { to: "/documents", label: "Documents", icon: "layers" }, { to: "/forum", label: "Forums", icon: "users" }] },
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
                <NavLink key={i.to} to={i.to} end={i.end ?? false} className={({ isActive }) => "side-i" + (i.sub ? " sub" : "") + (isActive ? " on" : "")} title={collapsed ? i.label : undefined}>
                  <span className="side-ic"><Icon name={i.icon} /></span><span className="side-l">{i.label}{i.gold && <em className="gtag" title="Gold plan" aria-label="Gold plan">Gold</em>}</span>{i.badge && <span className="side-b">{i.badge}</span>}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="side-foot">
          <div className="side-plan" style={{ "--tc": `var(${TIER[plan].tc})` } as React.CSSProperties}>
            <span className={"tier " + plan}><Icon name={TIER[plan].ic} />{TIER[plan].n}</span>
            {plan !== "gold" ? <><p>{plan === "basic" ? "Unlock the FinLit score, watchlists and more." : "Gold adds FinLit Prism and deeper analysis."}</p><Link className="btn primary" to={user ? "/account/plan?want=" + (plan === "basic" ? "silver" : "gold") : "/plans"}>{plan === "basic" ? "See Silver" : "See Gold"}</Link></> : <p>Everything is unlocked.</p>}
          </div>
        </div>
      </aside>
      <div className="shell-main"><Outlet /></div>
    </div>
  );
}
