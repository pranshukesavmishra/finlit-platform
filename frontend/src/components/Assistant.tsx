import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { faqForPath } from "../lib/pageFaqs";
import { ASSISTANT } from "../content/site";
import { askAssistant } from "../lib/siteApi";
import { Icon } from "../lib/icons";
import { useEnquiry } from "./Enquiry";

type Msg = { role: "user" | "assistant"; content: string };

/** FinLit AI: guided menus first (instant, no cost), free-text chat via the site backend (Gemini) second. */
export function Assistant() {
  const [open, setOpen] = useState(false);
  const [node, setNode] = useState("main");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  const nav = useNavigate();
  const enquire = useEnquiry();
  const loc = useLocation();

  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [msgs, node, open, busy]);
  if (loc.pathname.startsWith("/admin")) return null;

  const cur = ASSISTANT[node];
  const pageFaq = faqForPath(loc.pathname);   // suggested questions = this page's FAQ set
  const askPage = (q: string, a: string) => setMsgs((m) => [...m, { role: "user", content: q }, { role: "assistant", content: a }]);
  const run = (a: { type: string; to?: string; target?: string; service?: string }, label: string) => {
    if (a.type === "menu" && a.target) { setMsgs((m) => [...m, { role: "user", content: label }]); setNode(a.target); }
    if (a.type === "navigate" && a.to) { nav(a.to); setOpen(false); }
    if (a.type === "enquire") { setOpen(false); enquire(a.service); }
  };
  async function send(e: React.FormEvent) {
    e.preventDefault();
    const q = text.trim();
    if (!q || busy) return;
    setText(""); const history = msgs.filter((m) => m.content);
    setMsgs((m) => [...m, { role: "user", content: q }]); setBusy(true);
    try { const r = await askAssistant(q, history); setMsgs((m) => [...m, { role: "assistant", content: r.response }]); }
    catch (er) { setMsgs((m) => [...m, { role: "assistant", content: (er as Error).message || "I couldn't answer that just now. Please try again or use the contact form." }]); }
    finally { setBusy(false); }
  }

  return (
    <>
      <button className={"ai-fab" + (open ? " hide" : "")} onClick={() => setOpen(true)} aria-label="Open FinLit AI assistant"><Icon name="spark" /><span>Ask FinLit AI</span></button>
      {open && (
        <section className="ai" role="dialog" aria-label="FinLit AI assistant">
          <header><div><b>FinLit AI</b><span>Guided help and market concepts</span></div><button onClick={() => setOpen(false)} aria-label="Close">×</button></header>
          <div className="ai-body">
            <div className="bub bot">{ASSISTANT.main.greeting}</div>
            {msgs.map((m, i) => <div key={i} className={"bub " + (m.role === "user" ? "me" : "bot")} style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>)}
            {busy && <div className="bub bot typing"><i /><i /><i /></div>}
            {cur.answer && node !== "main" && <div className="bub bot" style={{ whiteSpace: "pre-wrap" }}>{cur.answer}</div>}
            {node === "main" && pageFaq && <div className="chips" aria-label={`Questions about ${pageFaq.title}`}>
              {pageFaq.items.slice(0, 4).map((it) => <button key={it.q} onClick={() => askPage(it.q, it.a)}>{it.q}</button>)}
            </div>}
            <div className="chips">
              {[...cur.options, ...(cur.additionalOptions || [])].map((o) => <button key={o.label} onClick={() => run(o.action, o.label)}>{o.label}</button>)}
              {node !== "main" && <button className="back" onClick={() => setNode("main")}>← {cur.backLabel || "Main menu"}</button>}
            </div>
            <div ref={end} />
          </div>
          <form onSubmit={send}>
            <input value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} placeholder="Ask about investing or our services" aria-label="Your question" />
            <button disabled={busy || !text.trim()} aria-label="Send"><Icon name="arrow" /></button>
          </form>
          <p className="ai-fine">General information, not investment advice.</p>
        </section>
      )}
    </>
  );
}
