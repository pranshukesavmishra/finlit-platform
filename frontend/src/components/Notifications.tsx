import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { Icon } from "../lib/icons";
import { useAuth } from "../lib/auth";
import { timeAgo, useAlerts, useBrowserNotify, useNotices, type Notice } from "../lib/alerts";
import { useUniverse } from "../lib/screener";
import { DEMO } from "../lib/demo";

/** Demo only: puts a few sample alerts and a notification in place so the bell and the alerts page have something to show. */
function DemoSeeder() { const { data } = useUniverse(); useAlerts(data?.rows); return null; }

/** The bell in the header: unread count, the latest alerts, and a way to the full list. */
export function NotificationBell() {
  const { items, unread, markRead, clear } = useNotices();
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const nav = useNavigate();
  useEffect(() => {
    if (!open) return;
    const h = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    const k = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", h); addEventListener("keydown", k);
    return () => { document.removeEventListener("mousedown", h); removeEventListener("keydown", k); };
  }, [open]);
  const go = (n: Notice) => { markRead([n.id]); setOpen(false); if (n.link) nav(n.link); };
  return (
    <div className="nt" ref={box}>
      <button className="icon-btn nt-btn" onClick={() => setOpen(!open)} aria-haspopup="dialog" aria-expanded={open} aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"}>
        <Icon name="bell" />{unread > 0 && <span className="nt-n" aria-hidden="true">{unread > 9 ? "9+" : unread}</span>}
      </button>
      {open && (
        <div className="nt-p" role="dialog" aria-label="Notifications">
          <div className="nt-h"><b>Notifications</b>{unread > 0 && <button className="alx-link" onClick={() => markRead()}>Mark all read</button>}</div>
          {items.length === 0 ? (
            <div className="nt-e"><span className="dw-ei"><Icon name="bell" /></span><b>Nothing yet</b><p>When one of your alerts fires, it shows up here.</p></div>
          ) : (
            <ul className="nt-l">
              {items.slice(0, 8).map((n) => (
                <li key={n.id}><button className={"nt-i" + (n.read ? "" : " is-new")} onClick={() => go(n)}>
                  <span className="nt-d" aria-hidden="true" /><span className="nt-t"><b>{n.title}</b><small>{timeAgo(n.createdAt)}</small></span>
                </button></li>
              ))}
            </ul>
          )}
          <div className="nt-f"><Link to="/alerts" onClick={() => setOpen(false)}>Manage alerts <Icon name="arrow" /></Link>{items.length > 0 && <button className="alx-link" onClick={() => clear()}>Clear all</button>}</div>
        </div>
      )}
    </div>
  );
}

/** Pops a card for each alert that fires while the site is open ("Alert Triggered … View Stock →"), and raises browser notifications if allowed. */
export function AlertToasts() {
  const { user } = useAuth();
  const { items, markRead } = useNotices();
  useBrowserNotify(user ? items : []);
  const seen = useRef<Set<number> | null>(null);
  const [shown, setShown] = useState<Notice[]>([]);
  const nav = useNavigate();
  useEffect(() => {
    if (!user) { seen.current = null; setShown([]); return; }
    if (seen.current === null) { seen.current = new Set(items.map((n) => n.id)); return; } // what was already there when the page opened is not "new"
    const fresh = items.filter((n) => !n.read && !seen.current!.has(n.id));
    if (!fresh.length) return;
    fresh.forEach((n) => seen.current!.add(n.id));
    setShown((s) => [...fresh.slice(0, 3), ...s].slice(0, 3));
    fresh.forEach((n) => setTimeout(() => setShown((s) => s.filter((x) => x.id !== n.id)), 9000));
  }, [items, user]);
  if (!shown.length) return DEMO && user ? <DemoSeeder /> : null;
  return (
    <>
    {DEMO && <DemoSeeder />}
    <div className="alx-toasts" role="region" aria-label="New alerts" aria-live="polite">
      {shown.map((n) => (
        <div className="alx-toast" key={n.id}>
          <span className="alx-ti"><Icon name="bell" /></span>
          <div className="alx-tb">
            <b>Alert triggered</b>
            <p>{n.title}</p>
            <div className="alx-tf"><button className="alx-link" onClick={() => { markRead([n.id]); setShown((s) => s.filter((x) => x.id !== n.id)); if (n.link) nav(n.link); }}>View stock <Icon name="arrow" /></button><small>{timeAgo(n.createdAt)}</small></div>
          </div>
          <button className="alx-x" aria-label="Dismiss" onClick={() => { markRead([n.id]); setShown((s) => s.filter((x) => x.id !== n.id)); }}>✕</button>
        </div>
      ))}
    </div>
    </>
  );
}
