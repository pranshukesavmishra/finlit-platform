import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { faqForPath } from "../lib/pageFaqs";
import { bankGroups, bankSuggestions, isLenderSector, SECOND, STARTERS } from "../lib/questionBank";
import { ASSISTANT } from "../content/site";
import { askAssistant } from "../lib/siteApi";
import { Icon } from "../lib/icons";
import { useEnquiry } from "./Enquiry";

/** Fired by the header button; the assistant panel listens for it. */
export const OPEN_AI = "finlit:open-ai";
type Msg = { role: "user" | "assistant"; content: string };

/** FinLit AI: guided menus first (instant, no cost), free-text chat via the site backend (Gemini) second. */
export function Assistant({ sector }: { sector?: string | null } = {}) {
  const [open, setOpen] = useState(false);
  const [node, setNode] = useState("main");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [more, setMore] = useState(false);          // the "More questions" list is open
  const [group, setGroup] = useState<number | null>(null);   // which of its groups is open
  const end = useRef<HTMLDivElement>(null);
  const field = useRef<HTMLInputElement>(null);
  const [pick, setPick] = useState(0);                 // bumps when the input must select XYZ
  const nav = useNavigate();
  const enquire = useEnquiry();
  const loc = useLocation();

  useEffect(() => { const o = () => setOpen(true); addEventListener(OPEN_AI, o); return () => removeEventListener(OPEN_AI, o); }, []);   // the "Ask FinLit AI" button in the header bar
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [msgs, node, open, busy]);
  useEffect(() => {   // Esc closes the panel (a dialog must)
    if (!open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", k); return () => document.removeEventListener("keydown", k);
  }, [open]);
  useEffect(() => {   // a question about two companies lands in the input with XYZ selected, ready to be typed over
    const el = field.current;
    if (!pick || !el) return;
    const at = el.value.indexOf(SECOND);
    el.focus();
    if (at >= 0) el.setSelectionRange(at, at + SECOND.length);
  }, [pick]);
  if (loc.pathname.startsWith("/admin")) return null;

  const cur = ASSISTANT[node];
  const menuOptions = [...cur.options, ...(cur.additionalOptions || [])];   // empty on the main menu: no service buttons, so no empty row either
  const pageFaq = faqForPath(loc.pathname);   // suggested questions = this page's FAQ set
  const bank = bankSuggestions(loc.pathname);  // on a company page: the question bank's most used questions about that company
  const groups = bankGroups(loc.pathname, { lender: isLenderSector(sector) });   // the 40 company questions, by group
  const tapBank = (q: { text: string; needsSecondCompany?: boolean }) => {
    if (q.needsSecondCompany) { setText(q.text); setPick((n) => n + 1); return; }   // the second company is the user's to name: nothing is sent yet
    setMore(false); sendText(q.text);
  };
  const askPage = (q: string, a: string) => setMsgs((m) => [...m, { role: "user", content: q }, { role: "assistant", content: a }]);
  const run = (a: { type: string; to?: string; target?: string; service?: string }, label: string) => {
    if (a.type === "menu" && a.target) { setMsgs((m) => [...m, { role: "user", content: label }]); setNode(a.target); }
    if (a.type === "navigate" && a.to) { nav(a.to); setOpen(false); }
    if (a.type === "enquire") { setOpen(false); enquire(a.service); }
  };
  async function send(e: React.FormEvent) { e.preventDefault(); await sendText(text.trim()); }
  async function sendText(q: string) {
    if (!q || busy) return;
    setText(""); const history = msgs.filter((m) => m.content);
    setMsgs((m) => [...m, { role: "user", content: q }]); setBusy(true);
    try { const r = await askAssistant(q, history); setMsgs((m) => [...m, { role: "assistant", content: r.response }]); }
    catch (er) { setMsgs((m) => [...m, { role: "assistant", content: (er as Error).message || "I couldn't answer that just now. Please try again or use the contact form." }]); }
    finally { setBusy(false); }
  }

  return (
    <>
      {open && (
        <section className="ai" role="dialog" aria-label="FinLit AI assistant">
          <header><div><b>FinLit AI</b><span>Guided help and market concepts</span></div><button onClick={() => setOpen(false)} aria-label="Close">×</button></header>
          <div className="ai-body">
            <div className="bub bot">{ASSISTANT.main.greeting}</div>
            {msgs.map((m, i) => <div key={i} className={"bub " + (m.role === "user" ? "me" : "bot")} style={{ whiteSpace: "pre-wrap" }}>{m.content}</div>)}
            {busy && <div className="bub bot typing"><i /><i /><i /></div>}
            {cur.answer && node !== "main" && <div className="bub bot" style={{ whiteSpace: "pre-wrap" }}>{cur.answer}</div>}
            {node === "main" && bank.length > 0 && <div className="chips" aria-label="Questions you can ask about this company">
              {bank.map((b) => <button key={b.id} onClick={() => sendText(b.text)}>{b.text}</button>)}
            </div>}
            {node === "main" && groups.length > 0 && <div className="ai-more">
              <button type="button" className="ai-more-btn" aria-expanded={more} aria-controls="ai-more-list" onClick={() => setMore((v) => !v)}>
                <span>More questions</span><i aria-hidden="true">{more ? "−" : "+"}</i>
              </button>
              {more && <div id="ai-more-list" className="ai-more-list" role="group" aria-label="More questions about this company, by topic">
                {groups.map((g) => {
                  const on = group === g.n;
                  return <div key={g.n} className={"ai-grp" + (on ? " on" : "")}>
                    <button type="button" className="ai-grp-h" aria-expanded={on} aria-controls={`ai-grp-${g.n}`} onClick={() => setGroup(on ? null : g.n)}>
                      <span>{g.title}</span><em>{g.items.length}</em>
                    </button>
                    {on && <div id={`ai-grp-${g.n}`} className="ai-grp-q">
                      {g.items.map((q) => <button type="button" key={q.id} onClick={() => tapBank(q)} title={q.needsSecondCompany ? `Replace ${SECOND} with the second company, then send` : undefined}>{q.text}</button>)}
                    </div>}
                  </div>;
                })}
              </div>}
            </div>}
            {node === "main" && !bank.length && !pageFaq && <div className="chips" aria-label="Questions you can ask">
              {STARTERS.map((x) => <button key={x.q} onClick={() => askPage(x.q, x.a)}>{x.q}</button>)}
            </div>}
            {node === "main" && pageFaq && <div className="chips" aria-label={`Questions about ${pageFaq.title}`}>
              {pageFaq.items.slice(0, 4).map((it) => <button key={it.q} onClick={() => askPage(it.q, it.a)}>{it.q}</button>)}
            </div>}
            {(menuOptions.length > 0 || node !== "main") && <div className="chips">
              {menuOptions.map((o) => <button key={o.label} onClick={() => run(o.action, o.label)}>{o.label}</button>)}
              {node !== "main" && <button className="back" onClick={() => setNode("main")}>← {cur.backLabel || "Main menu"}</button>}
            </div>}
            <div ref={end} />
          </div>
          <form onSubmit={send}>
            <input ref={field} value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} placeholder="Ask about investing or our services" aria-label="Your question" />
            <button disabled={busy || !text.trim()} aria-label="Send"><Icon name="arrow" /></button>
          </form>
          <p className="ai-fine">General information, not investment advice.</p>
        </section>
      )}
    </>
  );
}
