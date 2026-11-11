// "Raise a Query" (in a page's banner) and "Share Feedback" (a button at the foot of every page), with the one dialog both open.
// Every message goes to the team tagged with the page it was written on (lib/pageFeedback.ts). Styles: styles/pagefeedback.css (pf-).
import { useEffect, useId, useMemo, useRef, useState, useSyncExternalStore, type FormEvent } from "react";
import { createPortal } from "react-dom";
import { useInRouterContext, useLocation } from "react-router";
import { useMutation } from "@tanstack/react-query";
import { ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useFocusTrap } from "../lib/focusTrap";
import { Icon } from "../lib/icons";
import { FEEDBACK_TYPES, MESSAGE_MAX, QUERY_MIN, QUERY_TYPES, RATING_WORDS, banner, draftProblem, pageTag, panel, sendPageFeedback, type Kind } from "../lib/pageFeedback";
import "../styles/pagefeedback.css";

const openKind = () => useSyncExternalStore(panel.sub, panel.get, () => null);
const bannerCount = () => useSyncExternalStore(banner.sub, banner.get, () => 0);

/** The button in the page banner, after the page's own buttons. Counting it tells the dock the page already has one. */
export function RaiseQueryButton() {
  useEffect(() => banner.add(), []);
  return <button type="button" className="ph-qbtn" onClick={() => panel.set("query")} aria-haspopup="dialog"><Icon name="bubble" />Raise a Query</button>;
}

const msg = (e: unknown) => (e instanceof ApiError ? e.body.detail || e.body.status || "We could not send that." : "Could not reach the server. Please try again.");

function Chips({ label, options, value, onChange }: { label: string; options: readonly (readonly [string, string])[]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="pf-chips" role="radiogroup" aria-label={label}>
      {options.map(([k, l]) => <button type="button" key={k} role="radio" aria-checked={value === k} className={value === k ? "on" : ""} onClick={() => onChange(k)}>{l}</button>)}
    </div>
  );
}

function Stars({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  return (
    <div className="pf-stars" role="radiogroup" aria-label="Your rating of this page, 1 to 5">
      {[1, 2, 3, 4, 5].map((n) => (
        <button type="button" key={n} role="radio" aria-checked={value === n} aria-label={`${n} of 5, ${RATING_WORDS[n]}`} className={n <= value ? "on" : ""} onClick={() => onChange(value === n ? 0 : n)}><Icon name="star" /></button>
      ))}
      <span className="pf-rw" aria-live="polite">{value ? RATING_WORDS[value] : "Tap a star"}</span>
    </div>
  );
}

export function FeedbackDialog({ kind, pathname, plan, onClose }: { kind: Kind; pathname: string; plan: string | null; onClose: () => void }) {
  const { user } = useAuth();
  const signedIn = !!user;
  const tag = useMemo(() => pageTag(pathname, plan), [pathname, plan]);   // read once when the dialog opens: it describes the page the member was on
  const ref = useRef<HTMLDivElement>(null), tid = useId(), mid = useId();
  const [category, setCategory] = useState<string>(kind === "query" ? "question" : "suggestion");
  const [message, setMessage] = useState(""), [rating, setRating] = useState(0), [email, setEmail] = useState(""), [tried, setTried] = useState(false);
  useFocusTrap(ref, true);
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); onClose(); } };
    document.addEventListener("keydown", k, true);
    return () => document.removeEventListener("keydown", k, true);
  }, [onClose]);
  const m = useMutation({ mutationFn: () => sendPageFeedback({ kind, tag, category, message, rating, email }) });
  const problem = draftProblem({ kind, message, rating, email }, signedIn);
  const submit = (e: FormEvent) => { e.preventDefault(); setTried(true); if (!problem && !m.isPending) m.mutate(); };
  const isQ = kind === "query", left = MESSAGE_MAX - message.length;
  return createPortal(
    <>
      <div className="scrim pf-scrim" onClick={onClose} aria-hidden="true" />
      <div className="pf-modal" role="dialog" aria-modal="true" aria-labelledby={tid} ref={ref} tabIndex={-1}>
        <div className="pf-h">
          <h2 id={tid}>{isQ ? "Raise a query" : "Share feedback"}</h2>
          <button type="button" className="pf-x" aria-label="Close" onClick={onClose}>×</button>
        </div>
        <p className="pf-about"><Icon name="info" />About: <b>{tag.pageName}</b><span className="faint"> · {tag.page}</span></p>
        {m.isSuccess ? (
          <div className="pf-done" role="status">
            <span className="pf-ok" aria-hidden="true"><Icon name="check" /></span>
            <h3>{isQ ? "Query sent" : "Thank you"}</h3>
            <p>{isQ ? `The team has it, tagged to ${tag.pageName}. ${signedIn ? "We will reply to your account email" : "We will reply by email"}, usually within one working day.` : `Your feedback is saved against ${tag.pageName}. It goes straight to the team.`}</p>
            <button type="button" className="btn primary" onClick={onClose}>Close</button>
          </div>
        ) : (
          <form onSubmit={submit} noValidate>
            {!isQ && <Stars value={rating} onChange={setRating} />}
            <Chips label={isQ ? "What kind of query" : "What kind of feedback"} options={isQ ? QUERY_TYPES : FEEDBACK_TYPES} value={category} onChange={setCategory} />
            <label htmlFor={mid}>{isQ ? "Your question, the problem you saw, or what you would like explained" : "What would make this page better? (optional if you chose a rating)"}</label>
            <textarea id={mid} rows={5} value={message} maxLength={MESSAGE_MAX} onChange={(e) => setMessage(e.target.value)} autoFocus
              placeholder={isQ ? "For example: how is the Sector filter counted together with Market cap?" : "A suggestion, something confusing, a number that looks wrong, or what you like"} />
            <div className="pf-meta"><span>{isQ && message.trim().length < QUERY_MIN ? `At least ${QUERY_MIN} characters` : ""}</span><span className={left < 100 ? "warn" : ""}>{left} left</span></div>
            {!signedIn && <label className="pf-em">Your email, so we can reply<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" maxLength={254} /></label>}
            {signedIn && <p className="pf-who faint">Sent as your account. Do not include passwords or card details.</p>}
            {(tried && problem) && <div className="pf-err" role="alert">{problem}</div>}
            {m.isError && <div className="pf-err" role="alert">{msg(m.error)}</div>}
            <div className="pf-act">
              <button type="button" className="btn" onClick={onClose}>Cancel</button>
              <button className="btn primary" disabled={m.isPending}>{m.isPending ? "Sending…" : isQ ? "Send query" : "Send feedback"}</button>
            </div>
          </form>
        )}
      </div>
    </>, document.body);
}

/** Always on screen, bottom right: "Share feedback" for the page, and "Raise a Query" when the page has no banner to carry it. Also draws the dialog. */
export function PageFeedbackDock() {
  const inRouter = useInRouterContext();
  const pathname = inRouter ? useLocation().pathname : "/";   // eslint-disable-line react-hooks/rules-of-hooks
  const { user, plan } = useAuth();
  const open = openKind(), banners = bannerCount();
  useEffect(() => { panel.set(null); }, [pathname]);   // moving to another page closes it: it was about the page left behind
  if (/^\/admin(\/|$)/.test(pathname)) return null;
  return (
    <>
      <div className="pf-dock" data-no-banner={banners === 0 || undefined}>
        {banners === 0 && <button type="button" className="pf-fab pf-fab-q" aria-label="Raise a Query" onClick={() => panel.set("query")} aria-haspopup="dialog"><Icon name="bubble" /><span>Raise a Query</span></button>}
        <button type="button" className="pf-fab" aria-label="Share feedback" onClick={() => panel.set("feedback")} aria-haspopup="dialog"><Icon name="pencil" /><span>Share feedback</span></button>
      </div>
      {open && <FeedbackDialog key={open + pathname} kind={open} pathname={pathname} plan={user ? plan : null} onClose={() => panel.set(null)} />}
    </>
  );
}
