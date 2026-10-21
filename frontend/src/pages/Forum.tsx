import { useState, type FormEvent, type ReactNode } from "react";
import { Link, Navigate, Route, Routes, useNavigate, useParams, useSearchParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiGet } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useDocTitle } from "../lib/title";
import { DISCLAIMER, ago, draftProblem, forumMe, linkify, pageWindow, send, validHandle, type Page, type Post, type QueueItem } from "../lib/forum";
import "../styles/forum.css";

const msg = (e: unknown) => (e instanceof ApiError ? e.body.detail || e.body.status || "Failed" : "Could not reach the server.");
const Disclaimer = () => <p className="fo-disc" role="note"><b>Not investment advice.</b> {DISCLAIMER} <Link to="/forum/guidelines">Community guidelines</Link></p>;
const Shell = ({ title, children }: { title: string; children: ReactNode }) => <div className="wrap fo"><div className="eyebrow">Discussion</div><h1>{title}</h1><Disclaimer />{children}</div>;

export function Body({ text }: { text: string }) {
  return <div className="fo-body">{linkify(text).map((t, i) => t.t === "text" ? <span key={i}>{t.v}</span> : <a key={i} href={t.href} target="_blank" rel="nofollow noopener noreferrer ugc">{t.label}</a>)}</div>;
}

function Pager({ page, pages, go }: { page: number; pages: number; go: (n: number) => void }) {
  if (pages <= 1) return null;
  return <nav className="fo-pager" aria-label="Pages">{pageWindow(page, pages).map((n, i) => n === "…" ? <span key={i}>…</span> : <button key={n} className={"btn" + (n === page ? " on" : "")} aria-current={n === page ? "page" : undefined} onClick={() => go(n)}>{n}</button>)}</nav>;
}

/** Choose the public name (once) and accept the guidelines. */
function JoinForm() {
  const qc = useQueryClient();
  const [handle, setHandle] = useState(""), [ok, setOk] = useState(false);
  const m = useMutation({ mutationFn: () => send("POST", "/api/forum/profile", { handle, accept: ok }), onSuccess: () => qc.invalidateQueries({ queryKey: ["forum", "me"] }) });
  return (
    <form className="fo-form" onSubmit={(e: FormEvent) => { e.preventDefault(); m.mutate(); }}>
      <label>Choose a public name (shown instead of your email or account name; it cannot be changed later)
        <input value={handle} onChange={(e) => setHandle(e.target.value)} maxLength={20} autoComplete="off" /></label>
      <label style={{ display: "flex", gap: 8, alignItems: "center" }}><input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} />
        <span>I have read the <Link to="/forum/guidelines">community guidelines</Link> and understand nothing here is investment advice.</span></label>
      <button className="btn primary" disabled={!validHandle(handle) || !ok || m.isPending}>Join the discussion</button>
      {m.isError && <div className="fo-err" role="alert">{msg(m.error)}</div>}
    </form>
  );
}

/** Gate for writing: visitors sign in, members without a name pick one. */
function Writer({ children }: { children: ReactNode }) {
  const { data: me } = forumMe();
  const loc = typeof window !== "undefined" ? window.location.pathname : "/forum";
  if (!me) return null;
  if (!me.signedIn) return <p className="muted"><Link to={`/login?next=${encodeURIComponent(loc)}`}>Sign in</Link> (free) to join the discussion. Reading is open to everyone.</p>;
  if (me.banned) return <p className="fo-err">Posting is paused on your account.</p>;
  if (!me.canPost) return <JoinForm />;
  return <>{children}</>;
}

function Composer({ symbol, thread, onDone }: { symbol?: string; thread?: number; onDone: (p: Post) => void }) {
  const [sym, setSym] = useState(symbol || ""), [title, setTitle] = useState(""), [body, setBody] = useState("");
  const kind = thread ? "reply" : "thread", problem = draftProblem(kind, title, body) || (!thread && !sym.trim() ? "Enter the company symbol." : "");
  const m = useMutation({
    mutationFn: () => send<{ post: Post; status: string; detail?: string }>("POST", thread ? `/api/forum/threads/${thread}/replies` : "/api/forum/threads", thread ? { body } : { symbol: sym.trim().toUpperCase(), title, body }),
    onSuccess: (r) => { setBody(""); setTitle(""); onDone(r.post); },
  });
  return (
    <form className="fo-form" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
      {!thread && !symbol && <label>Company symbol<input value={sym} onChange={(e) => setSym(e.target.value)} placeholder="e.g. RELIANCE" maxLength={24} /></label>}
      {!thread && <label>Title<input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={140} /></label>}
      <label>{thread ? "Your reply" : "What would you like to discuss? Share data and reasoning, not what others should buy or sell."}
        <textarea value={body} onChange={(e) => setBody(e.target.value)} /></label>
      <div className="fo-act"><button className="btn primary" disabled={!!problem || m.isPending}>{thread ? "Reply" : "Post discussion"}</button>{problem && (title || body) && <span className="muted">{problem}</span>}</div>
      {m.data?.status === "held" && <div className="fo-note" role="status">{m.data.detail}</div>}
      {m.isError && <div className="fo-err" role="alert">{msg(m.error)}</div>}
    </form>
  );
}

function List({ symbol }: { symbol?: string }) {
  const [sp, setSp] = useSearchParams();
  const page = Number(sp.get("page")) || 1, sort = sp.get("sort") || "active", q = sp.get("q") || "";
  const [text, setText] = useState(q);
  const nav = useNavigate(), qc = useQueryClient();
  const set = (k: string, v: string) => { const n = new URLSearchParams(sp); v ? n.set(k, v) : n.delete(k); if (k !== "page") n.delete("page"); setSp(n); };
  const key = ["forum", "threads", symbol || "", sort, q, page];
  const list = useQuery<Page<{ threads: Post[] }>>({ queryKey: key, queryFn: () => apiGet(`/api/forum/threads?sort=${sort}&page=${page}${symbol ? `&symbol=${symbol}` : ""}${q ? `&q=${encodeURIComponent(q)}` : ""}`) });
  const companies = useQuery<{ companies: { symbol: string; name: string; threads: number }[] }>({ queryKey: ["forum", "companies"], queryFn: () => apiGet("/api/forum/companies"), enabled: !symbol });
  return (
    <>
      <Writer><details><summary className="btn primary" style={{ display: "inline-flex" }}>Start a discussion</summary>
        <Composer symbol={symbol} onDone={(p) => { qc.invalidateQueries({ queryKey: ["forum"] }); if (p.status === "visible") nav(`/forum/t/${p.id}`); }} /></details></Writer>
      {!symbol && !!companies.data?.companies.length && <div className="fo-chips" aria-label="Active companies">{companies.data.companies.map((c) => <Link key={c.symbol} className="chip ghost" to={`/forum/c/${c.symbol}`}>{c.symbol} · {c.threads}</Link>)}</div>}
      <form className="fo-bar" role="search" onSubmit={(e) => { e.preventDefault(); set("q", text.trim()); }}>
        <input aria-label="Search discussion titles" placeholder="Search titles" value={text} onChange={(e) => setText(e.target.value)} maxLength={60} />
        <div className="seg" role="group" aria-label="Sort">{(["active", "recent", "top"] as const).map((s) => <button type="button" key={s} aria-pressed={sort === s} onClick={() => set("sort", s)}>{{ active: "Most active", recent: "Newest", top: "Top" }[s]}</button>)}</div>
      </form>
      {list.isPending ? <div className="skeleton" style={{ height: 80 }} /> : list.isError ? <div className="fo-err">{msg(list.error)}</div> : !list.data.threads.length ? (
        <p className="muted">{q ? "Nothing matches that search." : symbol ? "No discussions about this company yet. Be the first to start one." : "No discussions yet. Be the first to start one."}</p>
      ) : (
        <ul className="fo-list">{list.data.threads.map((t) => (
          <li key={t.id}><Link className="fo-row" to={`/forum/t/${t.id}`}>
            <div className="fo-meta"><b>{t.symbol}</b><span>{t.company}</span></div>
            <h3>{t.title}</h3><p>{t.body}</p>
            <div className="fo-meta"><span>{t.author.handle}{t.author.staff && " (FinLit team)"}</span><span>{ago(t.createdAt)}</span><span>{t.replies} repl{t.replies === 1 ? "y" : "ies"}</span><span>{t.upvotes} upvote{t.upvotes === 1 ? "" : "s"}</span></div>
          </Link></li>))}</ul>
      )}
      {list.data && <Pager page={page} pages={list.data.pages} go={(n) => set("page", String(n))} />}
    </>
  );
}

function PostView({ p, onChange }: { p: Post; onChange: () => void }) {
  const { data: me } = forumMe();
  const [edit, setEdit] = useState(false), [title, setTitle] = useState(p.title || ""), [body, setBody] = useState(p.body || ""), [rep, setRep] = useState(false);
  const act = useMutation({ mutationFn: (f: () => Promise<unknown>) => f(), onSuccess: onChange });
  const gone = p.body === null;
  return (
    <article className={"fo-post" + (gone ? " is-gone" : "")} id={`p${p.id}`}>
      <div className="fo-meta"><b>{p.author.handle}</b>{p.author.staff && <span className="fo-staff">FinLit team</span>}<span>{ago(p.createdAt)}</span>{p.editedAt && <span>edited</span>}</div>
      {p.note && <div className="fo-note">{p.note}</div>}
      {!gone && !edit && <Body text={p.body!} />}
      {edit && <form className="fo-form" onSubmit={(e) => { e.preventDefault(); act.mutate(() => send("PATCH", `/api/forum/posts/${p.id}`, { title: p.kind === "thread" ? title : undefined, body }).then(() => setEdit(false))); }}>
        {p.kind === "thread" && <input aria-label="Title" value={title} onChange={(e) => setTitle(e.target.value)} />}<textarea aria-label="Text" value={body} onChange={(e) => setBody(e.target.value)} />
        <div className="fo-act"><button className="btn primary">Save</button><button type="button" className="btn" onClick={() => setEdit(false)}>Cancel</button></div></form>}
      {!gone && me?.signedIn && (
        <div className="fo-act">
          {!p.mine && p.status === "visible" && <button className={"btn" + (p.voted ? " on" : "")} aria-pressed={p.voted} onClick={() => act.mutate(() => send(p.voted ? "DELETE" : "PUT", `/api/forum/posts/${p.id}/vote`))}>▲ {p.upvotes}</button>}
          {p.mine && p.canEdit && <button className="btn" onClick={() => setEdit(true)}>Edit ({Math.max(1, Math.ceil(p.editableSeconds / 60))} min left)</button>}
          {p.mine && <button className="btn" onClick={() => { if (confirm("Delete this post?")) act.mutate(() => send("DELETE", `/api/forum/posts/${p.id}`)); }}>Delete</button>}
          {!p.mine && p.status === "visible" && <button className="btn" onClick={() => { const reason = prompt("Report this post. Reason: advice, promotion, contact, abuse, spam, misleading, other", "advice"); if (reason) act.mutate(() => send("POST", `/api/forum/posts/${p.id}/report`, { reason: reason.trim().toLowerCase() })); }}>Report</button>}
          {p.kind === "thread" && p.status === "visible" && <button className="btn" onClick={() => setRep(!rep)}>Reply</button>}
        </div>)}
      {!gone && !me?.signedIn && p.upvotes > 0 && <div className="fo-meta">▲ {p.upvotes}</div>}
      {rep && <Writer><Composer thread={p.id} onDone={() => { setRep(false); onChange(); }} /></Writer>}
      {act.isError && <div className="fo-err" role="alert">{msg(act.error)}</div>}
    </article>
  );
}

function Thread() {
  const { id } = useParams(), [sp, setSp] = useSearchParams(), page = Number(sp.get("page")) || 1, qc = useQueryClient();
  const q = useQuery<Page<{ thread: Post; replies: Post[] }>>({ queryKey: ["forum", "thread", id, page], queryFn: () => apiGet(`/api/forum/threads/${id}?page=${page}`), retry: false });
  useDocTitle(q.data?.thread.title || "Discussion");
  const refresh = () => qc.invalidateQueries({ queryKey: ["forum"] });
  if (q.isPending) return <Shell title="Discussion"><div className="skeleton" style={{ height: 80 }} /></Shell>;
  if (q.isError) return <Shell title="Discussion"><p className="muted">{q.error instanceof ApiError && q.error.status === 410 ? "This discussion was removed." : "This discussion is not available."}</p><Link className="btn" to="/forum">All discussions</Link></Shell>;
  const { thread, replies } = q.data;
  return (
    <Shell title={thread.title || "Discussion"}>
      <p className="muted"><Link to={`/forum/c/${thread.symbol}`}>{thread.company} ({thread.symbol})</Link> · <Link to={`/stocks/${thread.symbol}`}>Company report</Link></p>
      <PostView p={thread} onChange={refresh} />
      <h2 style={{ fontSize: 18 }}>{q.data.total} repl{q.data.total === 1 ? "y" : "ies"}</h2>
      {replies.map((r) => <PostView key={r.id} p={r} onChange={refresh} />)}
      <Pager page={page} pages={q.data.pages} go={(n) => setSp({ page: String(n) })} />
      {thread.status === "visible" && <Writer><h3>Add a reply</h3><Composer thread={thread.id} onDone={refresh} /></Writer>}
    </Shell>
  );
}

function Guidelines() {
  useDocTitle("Community guidelines", "Rules for FinLit discussions: information and opinion only.");
  return (
    <Shell title="Community guidelines and terms">
      <p>FinLit Ventures is a research platform. We are not a SEBI-registered investment adviser or research analyst, and nothing posted here is a recommendation. Members post in their own name (a chosen handle) and are responsible for what they write.</p>
      <h2 style={{ fontSize: 18 }}>What is welcome</h2>
      <ul><li>Questions and views about a company's business, results, balance sheet, valuation and risks, with the data or source behind them.</li><li>Links (up to {2} per post) to filings, annual reports or news articles.</li></ul>
      <h2 style={{ fontSize: 18 }}>What is not allowed</h2>
      <ul><li>Tips and calls: telling others to buy or sell, price targets, stop-losses, or promises of returns or "guaranteed" gains.</li><li>Promoting stocks, groups, channels, courses or paid services; pump-and-dump style hype.</li><li>Phone numbers, email addresses, WhatsApp/Telegram handles or invitations to move the conversation elsewhere.</li><li>Link shorteners, chat-group links, social profiles; abuse, harassment or personal attacks; repeating the same message.</li></ul>
      <h2 style={{ fontSize: 18 }}>How moderation works</h2>
      <p>Posts that look like hype are held until a moderator reads them. Posts reported by 3 different members are hidden until a moderator decides. Moderators may remove posts and pause accounts. You can edit a post for 15 minutes and delete it at any time. Reading is open to everyone; posting needs a free FinLit account. Posts are public. We never show your email or account name.</p>
      <p className="muted">{DISCLAIMER}</p>
    </Shell>
  );
}

/** Administrators only (server re-checks role and two-step sign-in on every call). */
function Moderation() {
  const { user, ready, isAdmin } = useAuth(), qc = useQueryClient();
  const [kind, setKind] = useState<"open" | "recent">("open");
  const q = useQuery<{ items: QueueItem[]; counts: { held: number; hidden: number } }>({ queryKey: ["forum", "queue", kind], queryFn: () => apiGet(`/api/admin/forum/queue?kind=${kind}`), enabled: isAdmin && !!user?.mfaOk, retry: false });
  const act = useMutation({ mutationFn: (f: () => Promise<unknown>) => f(), onSuccess: () => qc.invalidateQueries({ queryKey: ["forum", "queue"] }) });
  if (!ready) return null;
  if (!user) return <Navigate to="/login?next=%2Fforum%2Fmoderation" replace />;
  if (!isAdmin || !user.mfaOk) return <Shell title="Moderation"><p className="muted">Administrators only, signed in with the authenticator code.</p></Shell>;
  return (
    <Shell title="Moderation queue">
      <div className="seg" role="group" aria-label="Show">{(["open", "recent"] as const).map((k) => <button key={k} aria-pressed={kind === k} onClick={() => setKind(k)}>{k === "open" ? `Needs a decision (${(q.data?.counts.held ?? 0) + (q.data?.counts.hidden ?? 0)})` : "Latest posts"}</button>)}</div>
      {q.isError && <div className="fo-err">{msg(q.error)}</div>}
      {q.data && !q.data.items.length && <p className="muted">Nothing waiting.</p>}
      {q.data?.items.map((i) => (
        <div className="fo-q" key={i.id}>
          <div className="fo-meta"><b>{i.status}</b><span>{i.symbol}</span><span>{i.author.handle} ({i.author.email}){i.author.banned && " · paused"}</span><Link to={`/forum/t/${i.threadId}`}>open</Link></div>
          {i.title && <h3>{i.title}</h3>}<pre>{i.body}</pre>
          {i.flagReasons.length > 0 && <div className="fo-note">Held: {i.flagReasons.join("; ")}</div>}
          {i.reports.map((r, n) => <div key={n} className="fo-meta">Report by {r.by}: {r.reason}{r.note ? ` – ${r.note}` : ""}</div>)}
          <div className="fo-act">
            {i.status !== "visible" && <button className="btn" onClick={() => act.mutate(() => send("POST", `/api/admin/forum/posts/${i.id}/approve`, {}))}>Approve</button>}
            {i.status !== "removed" && <button className="btn" onClick={() => act.mutate(() => send("POST", `/api/admin/forum/posts/${i.id}/remove`, { note: prompt("Reason (optional)") || "" }))}>Remove</button>}
            <button className="btn" onClick={() => { const d = Number(prompt("Pause this member's posting for how many days?", "7")); if (d > 0) act.mutate(() => send("POST", `/api/admin/forum/users/${i.author.userId}/ban`, { days: d, reason: prompt("Reason") || "" })); }}>Pause member</button>
          </div>
        </div>))}
      {act.isError && <div className="fo-err">{msg(act.error)}</div>}
    </Shell>
  );
}

function Index() {
  useDocTitle("Discussion forum", "Discuss listed companies: information and opinion only, moderated.");
  return <Shell title="Discussion forum"><List /></Shell>;
}
function Company() {
  const { symbol = "" } = useParams(), s = symbol.toUpperCase();
  useDocTitle(`${s} discussion`);
  return <Shell title={`${s} discussion`}><p className="muted"><Link to={`/stocks/${s}`}>Company report</Link> · <Link to="/forum">All discussions</Link></p><List symbol={s} /></Shell>;
}

export function ForumPage() {
  return <Routes><Route index element={<Index />} /><Route path="c/:symbol" element={<Company />} /><Route path="t/:id" element={<Thread />} /><Route path="guidelines" element={<Guidelines />} /><Route path="moderation" element={<Moderation />} /><Route path="*" element={<Navigate to="/forum" replace />} /></Routes>;
}
