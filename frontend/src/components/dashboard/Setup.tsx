// The "Setup 2 of 5" chip in the greeting row and the drawer with the checklist (it replaces the mid-page "Get started" card). The chip is hidden at 5 of 5.
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { useAlerts } from "../../lib/alerts";
import { Icon } from "../../lib/icons";

const SEEN = "finlit-welcome-report";
type Step = { done: boolean; t: string; d: string; to: string; cta: string; onClick?: () => void };

export function useSetup(followed: number, palette: string, plan: string) {
  const { alerts } = useAlerts();
  const [seen, setSeen] = useState(() => { try { return localStorage.getItem(SEEN) === "1"; } catch { return false; } });
  const mark = () => { setSeen(true); try { localStorage.setItem(SEEN, "1"); } catch { /* private mode */ } };
  const steps: Step[] = [
    { done: true, t: "Create your account", d: "You are in. Your plan, lists and colours now follow you across devices.", to: "/account", cta: "Review account" },
    { done: seen, t: "Open a company report", d: "Every listed stock has one: statements, ratios, peers, ownership and price.", to: "/research", cta: "Find a company", onClick: mark },
    { done: followed > 0, t: "Follow a stock", d: plan === "basic" ? "Watchlists are part of Silver. Unlock them any time." : "Add stocks to a watchlist to see them here every day.", to: plan === "basic" ? "/plans" : "/watchlist", cta: plan === "basic" ? "See Silver" : "Open watchlist" },
    { done: alerts.length > 0, t: "Set your first alert", d: "Be told when a price, RSI, score, result or filing crosses your line.", to: "/alerts", cta: "Create an alert" },
    { done: palette !== "gold", t: "Make it yours", d: "Pick a colour palette and choose the dashboard blocks you want.", to: "/account/appearance", cta: "Open appearance" },
  ];
  return { steps, n: steps.filter((s) => s.done).length };
}

export function SetupChip({ steps, n }: { steps: Step[]; n: number }) {
  const [open, setOpen] = useState(false);
  const btn = useRef<HTMLButtonElement>(null), close = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    close.current?.focus();
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); btn.current?.focus(); } };
    document.addEventListener("keydown", k); return () => document.removeEventListener("keydown", k);
  }, [open]);
  if (n >= steps.length) return null;
  return (
    <>
      <button ref={btn} type="button" className="dsh-chip setup" aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(true)}>
        Setup {n} of {steps.length}<span className="bar" role="progressbar" aria-valuemin={0} aria-valuemax={steps.length} aria-valuenow={n} aria-label="Setup progress"><i style={{ width: `${(n / steps.length) * 100}%` }} /></span>
      </button>
      {open && <>
        <div className="dsh-scrim" onClick={() => setOpen(false)} />
        <aside className="dsh-drawer" role="dialog" aria-modal="true" aria-label="Setup checklist">
          <div className="dh"><div><h2>Get started with FinLit</h2><p className="dsh-sub">{n} of {steps.length} done. A few minutes to get the most from your account.</p></div>
            <button ref={close} type="button" className="dsh-ib" aria-label="Close" onClick={() => { setOpen(false); btn.current?.focus(); }}>×</button></div>
          <ol>{steps.map((s) => (
            <li key={s.t} className={s.done ? "is-done" : ""}><span className="c" aria-hidden="true">{s.done ? <Icon name="check" /> : null}</span><div><b>{s.t}</b><span>{s.d}</span></div>
              {!s.done && <Link className="dsh-btn" to={s.to} onClick={() => { s.onClick?.(); setOpen(false); }}>{s.cta}</Link>}</li>))}</ol>
        </aside></>}
    </>
  );
}
