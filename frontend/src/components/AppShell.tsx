import { useEffect, useMemo, useRef, useState, type KeyboardEvent as RKeyEvent } from "react";
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
import { badgeFor } from "../lib/sideGroups";
import { isBool, isBoolMap, loadUi, saveUi } from "../lib/persist";

const RESEARCH = SECTIONS.find((x) => x.id === "research")!;   // by id: the header order changes (Workspace comes first)

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
  const [collapsed, setCollapsed] = useState(() => loadUi("side-collapsed", 1, isBool, false));
  const [open, setOpen] = useState(false); // mobile drawer
  useEffect(() => { setOpen(false); }, [pathname]);
  useEffect(() => { const o = () => setOpen((v) => !v); addEventListener("finlit:open-side", o); return () => removeEventListener("finlit:open-side", o); }, []);
  useEffect(() => { saveUi("side-collapsed", 1, collapsed); }, [collapsed]);
  useEffect(() => { if (!open) return; const k = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false); addEventListener("keydown", k); return () => removeEventListener("keydown", k); }, [open]);
  // Each group is a drop-down: a header you click to show or hide its pages. The group holding the current page is always open;
  // what you opened or closed by hand is remembered.
  const [folded, setFolded] = useState<Record<string, boolean>>(() => loadUi("side-groups", 1, isBoolMap, {}));
  const toggleGroup = (t: string, isOpen: boolean) => setFolded((f) => { const n = { ...f, [t]: isOpen }; saveUi("side-groups", 1, n); return n; });
  // "Find a page": filters the links by name and opens the groups that match (Ctrl+/ focuses it).
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();
  const searchRef = useRef<HTMLInputElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const [scrolled, setScrolled] = useState(false);
  const [tip, setTip] = useState<{ label: string; top: number; left: number } | null>(null);
  useEffect(() => {
    const k = (e: KeyboardEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.key !== "/") return;
      e.preventDefault();
      if (collapsed && matchMedia("(min-width: 961px)").matches) setCollapsed(false);
      setOpen(true);
      requestAnimationFrame(() => searchRef.current?.focus());
    };
    addEventListener("keydown", k); return () => removeEventListener("keydown", k);
  }, [collapsed]);
  const showTip = (el: HTMLElement, label: string) => {
    if (!collapsed || !matchMedia("(min-width: 961px)").matches) return;
    const r = el.getBoundingClientRect();
    setTip({ label, top: r.top + r.height / 2, left: r.right + 10 });
  };
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
    ...RESEARCH.groups.map((g) => ({ title: g.title || RESEARCH.label, items: g.items.map(toItem) })),
    { title: "Markets", items: mine("markets") },
    { title: "News & events", items: mine("news") },
    { title: "Funds", items: mine("funds") },
    { title: "Your workspace", items: mine("myfinlit", [{ to: "/baskets", label: "My baskets", icon: "layers" }]).filter((x) => x.to !== "/dashboard") },
    { title: MORE.groups[0].title!, items: MORE.groups[0].items.map(toItem) },
    { title: "Learn", items: [{ to: "/glossary", label: "Glossary", icon: "book" }, { to: "/blog", label: "Insights & blog", icon: "spark" }, { to: "/documents", label: "Documents", icon: "layers" }, { to: "/forum", label: "Forums", icon: "users" }] },
    ...(user ? [{ title: "Account", items: [
      { to: "/account", label: "Profile & security", icon: "users", end: true },
      { to: "/account/appearance", label: "Appearance", icon: "spark" },
      ...(DEMO ? [] : [{ to: "/account/plan", label: "Plan", icon: "crown" }]),
      ...(isAdmin ? [{ to: "/console", label: "Admin console", icon: "lock" }] : []),
    ] }] : []),
  ];

  const here = (g: Group) => g.items.some((i) => (i.end ? pathname === i.to : pathname === i.to || pathname.startsWith(i.to + "/")));
  // open when the page you are on is inside it, otherwise what you chose; the one-page Overview group and the first visit start open for Find stocks
  const groupOpen = (g: Group) => here(g) || folded[g.title] === true || (folded[g.title] === undefined && (g.items.length === 1 || g.title === "Find stocks"));
  const shown = useMemo(() => groups.map((g) => ({ g, items: !q ? g.items : g.title.toLowerCase().includes(q) ? g.items : g.items.filter((i) => i.label.toLowerCase().includes(q)) })), [groups, q]);
  const hits = shown.reduce((n, x) => n + x.items.length, 0);
  // Arrow keys walk the visible group headers and links; Home/End jump to the ends; ArrowUp from the first row returns to the search box.
  const onNavKey = (e: RKeyEvent<HTMLElement>) => {
    const keys = ["ArrowDown", "ArrowUp", "Home", "End"];
    if (!keys.includes(e.key) || e.altKey || e.ctrlKey || e.metaKey) return;
    const rows = [...e.currentTarget.querySelectorAll<HTMLElement>(".side-gb, .side-i")].filter((el) => !el.closest("[inert]") && getComputedStyle(el).display !== "none");
    const at = rows.indexOf(document.activeElement as HTMLElement);
    if (at < 0) return;
    e.preventDefault();
    const to = e.key === "Home" ? 0 : e.key === "End" ? rows.length - 1 : e.key === "ArrowDown" ? Math.min(at + 1, rows.length - 1) : at - 1;
    if (to < 0) searchRef.current?.focus(); else rows[to].focus();
  };
  return (
    <div className={"shell" + (collapsed ? " is-collapsed" : "") + (open ? " is-open" : "")}>
      <button className="shell-fab" onClick={() => setOpen(true)} aria-label="Open the product menu" aria-expanded={open}><Icon name="panel" /><span>Menu</span></button>
      {open && <div className="shell-scrim" onClick={() => setOpen(false)} aria-hidden="true" />}
      <aside className="side" aria-label="Product navigation">
        <div className={"side-top" + (scrolled ? " is-scrolled" : "")}>
          <span className="side-t"><span className="side-tb" aria-hidden="true"><Icon name="grid" /></span><span className="side-tt">Workspace</span></span>
          <button className="side-toggle hide-sm" onClick={() => setCollapsed(!collapsed)} aria-label={collapsed ? "Expand the side menu" : "Collapse the side menu"} aria-pressed={collapsed} title={collapsed ? "Expand" : "Collapse"}><Icon name="panel" /></button>
          <button className="side-toggle show-sm" onClick={() => setOpen(false)} aria-label="Close the product menu">✕</button>
          <div className="side-find">
            <Icon name="search" />
            <input ref={searchRef} type="search" value={query} placeholder="Find a page" aria-label="Find a page" autoComplete="off" spellCheck={false}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape" && query) { e.stopPropagation(); setQuery(""); }
                else if (e.key === "ArrowDown") { e.preventDefault(); bodyRef.current?.querySelector<HTMLElement>(".side-i, .side-gb")?.focus(); }
              }} />
            {query ? <button type="button" className="side-clear" aria-label="Clear the search" onClick={() => { setQuery(""); searchRef.current?.focus(); }}>✕</button> : <kbd aria-hidden="true">Ctrl /</kbd>}
          </div>
        </div>
        <div className="side-body" ref={bodyRef} onScroll={(e) => { const v = e.currentTarget.scrollTop > 2; if (v !== scrolled) setScrolled(v); setTip(null); }}>
        <nav onKeyDown={onNavKey}>
          {q && hits === 0 && <p className="side-none" role="status">No page matches “{query.trim()}”.</p>}
          {shown.map(({ g, items }) => {
            if (q && !items.length) return null;
            const gid = "sg-" + g.title.replace(/\W+/g, "-"), isOpen = !!q || groupOpen(g), b = badgeFor(g.title), holds = here(g);
            return (
            <div className={"side-g" + (isOpen ? " is-open" : "") + (holds ? " has-here" : "")} key={g.title}>
              <button type="button" className="side-gt side-gb" aria-expanded={isOpen} aria-controls={gid} onClick={() => toggleGroup(g.title, !isOpen)}>
                <span className="side-gbd" aria-hidden="true"><Icon name={b.icon} /></span><span className="side-gname">{g.title}</span><span className="side-gn" aria-label={g.items.length + (g.items.length === 1 ? " page" : " pages")}>{g.items.length}</span><svg className="side-gc" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m7 10 5 5 5-5" /></svg>
              </button>
              <div id={gid} className="side-gi" role="region" aria-label={g.title} inert={!isOpen && !collapsed}>
              <div className="side-gin">
              {items.map((i) => (
                <NavLink key={i.to} to={i.to} end={i.end ?? false} className={({ isActive }) => "side-i" + (i.sub ? " sub" : "") + (isActive ? " on" : "")} aria-label={collapsed ? i.label : undefined}
                  onMouseEnter={(e) => showTip(e.currentTarget, i.label)} onFocus={(e) => showTip(e.currentTarget, i.label)} onMouseLeave={() => setTip(null)} onBlur={() => setTip(null)}>
                  <span className="side-ic"><Icon name={i.icon} /></span><span className="side-l"><span className="side-lt">{i.label}</span>{i.gold && <em className="gtag" title="Gold plan" aria-label="Gold plan">Gold</em>}</span>{i.badge && <span className="side-b">{i.badge}</span>}
                </NavLink>
              ))}
              </div>
              </div>
            </div>
            );
          })}
        </nav>
        <div className="side-foot">
          <div className="side-plan" style={{ "--tc": `var(${TIER[plan].tc})` } as React.CSSProperties}>
            <span className={"tier " + plan}><Icon name={TIER[plan].ic} />{TIER[plan].n}</span>
            {plan !== "gold" ? <><p>{plan === "basic" ? "Unlock the FinLit IQ, watchlists and more." : "Gold adds FinLit Prism and deeper analysis."}</p><Link className="btn primary" to={user ? "/account/plan?want=" + (plan === "basic" ? "silver" : "gold") : "/plans"}>{plan === "basic" ? "See Silver" : "See Gold"}</Link></> : <p>Everything is unlocked.</p>}
          </div>
        </div>
        </div>
      </aside>
      {tip && <div className="side-tip" role="presentation" style={{ top: tip.top, left: tip.left }}>{tip.label}</div>}
      <div className="shell-main"><Outlet /></div>
    </div>
  );
}
