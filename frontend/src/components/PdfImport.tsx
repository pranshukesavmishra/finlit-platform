import { useEffect, useMemo, useState } from "react";
import type { SearchRow } from "../lib/api";
import type { Found } from "../lib/holdingsMatch";
import { PdfPasswordError, readPdfHoldings, type PdfFinds } from "../lib/holdingsPdf";
import "../styles/pdfimport.css";

const WHY: Record<Found["how"], { label: string; sure: boolean }> = {
  exact: { label: "Exact match", sure: true },
  alias: { label: "Old ticker, same company", sure: true },
  split: { label: "Demerged: you now hold all its parts", sure: true },
  close: { label: "Name starts the same: please check", sure: false },
  scan: { label: "Found in the text: please check", sure: false },
};

/** Reads a holdings PDF in the browser and shows what it found next to the PDF's own words, so nothing is added until the person confirms.
 *  The file and any password stay on the device. */
export function PdfImport({ file, index, held, room, onAdd, onClose }: { file: File; index: SearchRow[]; held: string[]; room: number; onAdd: (symbols: string[]) => void; onClose: () => void }) {
  const [state, setState] = useState<"reading" | "password" | "review" | "error">("reading");
  const [wrong, setWrong] = useState(false), [pw, setPw] = useState(""), [msg, setMsg] = useState("");
  const [finds, setFinds] = useState<PdfFinds | null>(null), [pick, setPick] = useState<Record<string, boolean>>({});

  const run = async (password?: string) => {
    setState("reading");
    try {
      const r = await readPdfHoldings(file, index, password);
      setFinds(r); setPick(Object.fromEntries(r.found.map((f) => [f.symbol, WHY[f.how].sure && !held.includes(f.symbol)]))); setState("review");
    } catch (e) {
      if (e instanceof PdfPasswordError) { setWrong(e.wrong); setState("password"); return; }
      setMsg(e instanceof Error ? e.message : "That PDF could not be read."); setState("error");
    }
  };
  useEffect(() => { void run(); }, [file]); // eslint-disable-line react-hooks/exhaustive-deps

  const chosen = useMemo(() => (finds?.found || []).filter((f) => pick[f.symbol] && !held.includes(f.symbol)), [finds, pick, held]);
  const over = Math.max(0, chosen.length - room);

  if (state === "reading") return <div className="pdfi card" role="status"><div className="skeleton" style={{ height: 14, width: 200 }} /><p className="muted">Reading {file.name} on your device…</p></div>;
  if (state === "password") return (
    <form className="pdfi card" onSubmit={(e) => { e.preventDefault(); if (pw) void run(pw); }}>
      <h3>This PDF is password protected</h3>
      <p className="muted">Depository and some broker statements use your PAN (in capitals) or date of birth as the password. It is used here only to open the file, on your device, and is not stored or sent anywhere.</p>
      <div className="row"><input type="password" autoComplete="off" value={pw} onChange={(e) => setPw(e.target.value)} placeholder="PDF password" aria-label="PDF password" autoFocus /><button className="btn primary" disabled={!pw}>Open</button><button type="button" className="btn" onClick={onClose}>Cancel</button></div>
      {wrong && <p className="formerr" role="alert">That password is not correct. Try again.</p>}
    </form>
  );
  if (state === "error" || !finds) return <div className="pdfi card" role="alert"><h3>Could not read this PDF</h3><p>{msg}</p><button className="btn" onClick={onClose}>Close</button></div>;
  if (!finds.found.length) return (
    <div className="pdfi card" role="status"><h3>No listed companies found in {file.name}</h3>
      <p className="muted">The PDF has text, but none of it matched a listed company's name or ticker. Check that this is the holdings page, or download the Excel or CSV version of the statement from your broker.</p>
      <button className="btn" onClick={onClose}>Close</button></div>
  );
  return (
    <section className="pdfi card" aria-label="Review companies found in the PDF">
      <div className="card-h"><h3>Found {finds.found.length} {finds.found.length === 1 ? "company" : "companies"} in {file.name}</h3>
        <span className="s">{finds.mode === "table" ? "Read from the statement's table" : "Found in the text of the statement"}</span></div>
      <p className="muted">Check each line against your statement, then add them. Only the company names are used: quantities, prices and everything else in the PDF are ignored and nothing leaves your device. Lines marked "please check" are not ticked.</p>
      <div className="pdfi-list" role="list">{finds.found.map((f) => {
        const already = held.includes(f.symbol), why = WHY[f.how];
        return (
          <label className={"pdfi-row" + (why.sure ? "" : " warn") + (already ? " done" : "")} key={f.symbol} role="listitem">
            <input type="checkbox" checked={!!pick[f.symbol] && !already} disabled={already} onChange={(e) => setPick({ ...pick, [f.symbol]: e.target.checked })} />
            <span className="in" title="The words in your PDF">{f.input}</span><span aria-hidden="true">→</span>
            <span className="co"><b>{f.symbol}</b> <small>{f.name}</small></span>
            <span className="tag">{already ? "Already in your portfolio" : why.label}</span>
          </label>);
      })}</div>
      {finds.missing.length > 0 && <details className="pdfi-miss"><summary>{finds.missing.length} {finds.missing.length === 1 ? "line" : "lines"} in the table not matched to a listed company</summary>
        <p>{finds.missing.slice(0, 30).join(" · ")}{finds.missing.length > 30 ? ` · and ${finds.missing.length - 30} more` : ""}</p><p className="faint">Mutual funds, bonds and unlisted holdings are not scored. For a share that should be here, add it by its NSE ticker above.</p></details>}
      {over > 0 && <p className="pf-miss" role="status">Your plan holds up to {room + held.length} shares, so only the first {room} ticked here will be added.</p>}
      <div className="row">
        <button className="btn primary" disabled={!chosen.length} onClick={() => { onAdd(chosen.slice(0, room).map((f) => f.symbol)); onClose(); }}>Add {Math.min(chosen.length, room)} selected</button>
        <button className="btn" onClick={() => setPick(Object.fromEntries(finds.found.map((f) => [f.symbol, !held.includes(f.symbol)])))}>Select all</button>
        <button className="btn" onClick={onClose}>Cancel</button>
      </div>
    </section>
  );
}
