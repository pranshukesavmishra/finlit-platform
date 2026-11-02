// Console > Data health: expense ratios and fund sizes from AMFI, for a server AMFI's website does not answer.
// The nightly job downloads these two files itself; from the AWS address www.amfiindia.com times out, so no expense ratio or fund size is stored. An administrator can
// download the same two files in a normal browser and upload them here. The server checks them exactly as it checks the nightly download (expected columns, sane
// percentages, enough rows) and refuses a file older than the figures already held. Nothing is guessed; the dates shown with each figure are AMFI's own.
import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ApiError, apiSend } from "../../lib/api";
import { useUI } from "../../lib/ui";

const AMFI = "https://www.amfiindia.com/api";
/** The expense-ratio workbook's address for a month ("MM-YYYY", the form AMFI lists), newest first: this month and the one before. */
export function terLinks(today: Date): { month: string; url: string }[] {
  return [0, 1].map((back) => {
    const d = new Date(today.getFullYear(), today.getMonth() - back, 1);
    const month = `${String(d.getMonth() + 1).padStart(2, "0")}-${d.getFullYear()}`;
    return { month, url: `${AMFI}/populate-te-rdata-revised?MF_ID=All&Month=${month}&strCat=-1&strType=-1&excel=true` };
  });
}
/** The four (financial year, quarter) pairs AMFI's average-AUM page takes, newest first; the one that names the latest finished quarter is the one to save. */
export const AUM_LINKS = [[1, 1], [1, 2], [2, 1], [2, 2]].map(([fy, per]) => ({ label: `Year ${fy}, quarter ${per}`, url: `${AMFI}/average-aum-schemewise?strType=Typewise&fyId=${fy}&periodId=${per}` }));

const why = (e: unknown) => {
  if (e instanceof ApiError) { const b = e.body as { why?: string; detail?: string; status?: string }; return b.why || b.detail || b.status || "Failed"; }
  return (e as Error).message || "Could not reach the server.";
};
type Done = { status: string; schemes?: number; day?: string; period?: string; codes?: number; industryCrore?: number };

function toBase64(f: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onerror = () => reject(new Error("The file could not be read."));
    r.onload = () => resolve(String(r.result).split(",")[1] || "");
    r.readAsDataURL(f);
  });
}

function Pick({ id, label, accept, busy, onFile }: { id: string; label: string; accept: string; busy: boolean; onFile: (f: File) => void }) {
  const ref = useRef<HTMLInputElement>(null);
  return (<>
    <button className="btn primary" disabled={busy} onClick={() => ref.current?.click()}>{busy ? "Checking…" : label}</button>
    <input ref={ref} id={id} type="file" hidden accept={accept} aria-label={label} onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) onFile(f); }} />
  </>);
}

export function AmfiImport() {
  const { toast } = useUI();
  const [terMsg, setTerMsg] = useState(""), [aumMsg, setAumMsg] = useState(""), [terErr, setTerErr] = useState(""), [aumErr, setAumErr] = useState("");
  const ter = useMutation({
    mutationFn: async (f: File) => apiSend<Done>("POST", "/api/admin/amfi/ter", { file: await toBase64(f) }),
    onSuccess: (r) => { setTerErr(""); setTerMsg(`Stored the expense ratios of ${r.schemes?.toLocaleString("en-IN")} schemes, newest day ${r.day}.`); toast("Expense ratios stored."); },
    onError: (e) => { setTerMsg(""); setTerErr(why(e)); },
  });
  const aum = useMutation({
    mutationFn: async (f: File) => {
      let payload: unknown;
      try { payload = JSON.parse(await f.text()); } catch { throw new Error("This file is not the page's answer. Open the link, then save the page exactly as it shows (Ctrl+S), without editing it."); }
      return apiSend<Done>("POST", "/api/admin/amfi/aum", { payload });
    },
    onSuccess: (r) => { setAumErr(""); setAumMsg(`Stored the fund sizes of ${r.codes?.toLocaleString("en-IN")} schemes for ${r.period} (industry ₹${r.industryCrore?.toLocaleString("en-IN")} Cr).`); toast("Fund sizes stored."); },
    onError: (e) => { setAumMsg(""); setAumErr(why(e)); },
  });
  const months = terLinks(new Date());
  return (
    <section className="card acct-c" aria-label="AMFI expense ratios and fund sizes">
      <h2>Expense ratios and fund sizes (AMFI)</h2>
      <p className="muted">The server downloads these every night, but AMFI's website (www.amfiindia.com) does not answer from the server's address, so the mutual fund pages show no expense ratio or fund size.
        Download the two files below in your own browser and upload them here. They are checked the same way as the nightly download, and a file older than what is stored is refused. Describes data only; nothing is guessed.</p>
      <h3>1. Expense ratios (Excel)</h3>
      <p className="muted">Open the newest month that downloads a file, and save it:{" "}
        {months.map((m, i) => <span key={m.month}>{i > 0 && " · "}<a href={m.url} target="_blank" rel="noopener noreferrer">{m.month}</a></span>)}</p>
      <div className="row"><Pick id="amfi-ter" label="Upload the expense-ratio file" accept=".xlsx" busy={ter.isPending} onFile={(f) => { setTerMsg(""); setTerErr(""); ter.mutate(f); }} /></div>
      {terMsg && <p role="status" className="ok">{terMsg}</p>}{terErr && <div className="formerr" role="alert">{terErr}</div>}
      <h3>2. Fund sizes (average assets of the latest quarter)</h3>
      <p className="muted">Each link shows a page of data. Use the one that lists many schemes and names the latest finished quarter (<code>selectedPeriod</code>), then save the page as it is (Ctrl+S, as a text file):{" "}
        {AUM_LINKS.map((l, i) => <span key={l.url}>{i > 0 && " · "}<a href={l.url} target="_blank" rel="noopener noreferrer">{l.label}</a></span>)}</p>
      <div className="row"><Pick id="amfi-aum" label="Upload the fund-size file" accept=".json,.txt,application/json,text/plain" busy={aum.isPending} onFile={(f) => { setAumMsg(""); setAumErr(""); aum.mutate(f); }} /></div>
      {aumMsg && <p role="status" className="ok">{aumMsg}</p>}{aumErr && <div className="formerr" role="alert">{aumErr}</div>}
    </section>
  );
}
