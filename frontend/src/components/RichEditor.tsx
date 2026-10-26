import { useEffect, useRef } from "react";
import sanitize from "../lib/sanitize";
import { linkOk, normaliseHtml, textToHtml } from "../lib/richHtml";

// A small rich-text editor: contentEditable + a toolbar. No editor library, so nothing extra is shipped to visitors
// (this component loads only with the admin pages). Output goes through normaliseHtml and is sanitised again by the content service.
type Cmd = { label: string; text: string; run: () => void };
const run = (c: string, v?: string) => document.execCommand(c, false, v);

export function RichEditor({ initial, resetKey, onChange, label = "Article body" }: { initial: string; resetKey: string; onChange: (html: string) => void; label?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { if (ref.current) ref.current.innerHTML = sanitize(initial); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [resetKey]);
  const emit = () => { if (ref.current) onChange(normaliseHtml(ref.current.innerHTML)); };
  const link = () => {
    const href = window.prompt("Link address (must start with https://)", "https://");
    if (href === null) return;
    if (!linkOk(href)) { window.alert("Use a full link that starts with https://"); return; }
    run("createLink", href.trim()); emit();
  };
  const cmds: Cmd[] = [
    { label: "Heading", text: "H2", run: () => run("formatBlock", "h2") },
    { label: "Subheading", text: "H3", run: () => run("formatBlock", "h3") },
    { label: "Paragraph", text: "¶", run: () => run("formatBlock", "p") },
    { label: "Bold", text: "B", run: () => run("bold") },
    { label: "Italic", text: "I", run: () => run("italic") },
    { label: "Underline", text: "U", run: () => run("underline") },
    { label: "Bulleted list", text: "• List", run: () => run("insertUnorderedList") },
    { label: "Numbered list", text: "1. List", run: () => run("insertOrderedList") },
    { label: "Quote", text: "“ ”", run: () => run("formatBlock", "blockquote") },
    { label: "Add link", text: "Link", run: link },
    { label: "Remove link", text: "Unlink", run: () => run("unlink") },
    { label: "Divider", text: "―", run: () => run("insertHorizontalRule") },
  ];
  return (
    <div className="rte">
      <div className="rte-bar" role="toolbar" aria-label="Text formatting">
        {cmds.map((c) => <button key={c.label} type="button" className={"rte-b" + (c.label === "Bold" ? " b" : c.label === "Italic" ? " i" : c.label === "Underline" ? " u" : "")} aria-label={c.label} title={c.label}
          onMouseDown={(e) => e.preventDefault()} onClick={() => { ref.current?.focus(); c.run(); emit(); }}>{c.text}</button>)}
      </div>
      <div ref={ref} className="rte-area article" contentEditable suppressContentEditableWarning role="textbox" aria-multiline="true" aria-label={label} spellCheck
        onInput={emit} onBlur={emit}
        onPaste={(e) => { e.preventDefault(); const t = e.clipboardData.getData("text/plain"); if (t) { run("insertHTML", textToHtml(t)); emit(); } }} />
    </div>
  );
}
