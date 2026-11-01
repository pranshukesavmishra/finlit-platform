// Console > Data health: which listed companies show an initials tile instead of a logo, largest first, with the reason, and a way to set one by hand.
// Logos are fetched from each company's own website by a nightly job; a site that blocks bots or has no usable icon stays blank. An official brand image can be added here.
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, apiGet, apiSend } from "../../lib/api";
import { useUI } from "../../lib/ui";

type Missing = { items: { symbol: string; name: string; marketCapCr: number | null; status: string; reason: string }[]; companies: number; withLogo: number; top500WithLogo: number; top500: number };
const MAX_BYTES = 64 * 1024;
const msg = (e: unknown) => (e instanceof ApiError ? e.body.detail || e.body.status || "Failed" : "Could not reach the server.");

/** The file as base64 (the part after the comma of a data URL); refused here when it is over the server's 64 KB limit, so the person gets the reason at once. */
export function readImage(f: File): Promise<string> {
  return new Promise((resolve, reject) => {
    if (f.size > MAX_BYTES) { reject(new Error(`This file is ${Math.ceil(f.size / 1024)} KB. A logo can be at most 64 KB.`)); return; }
    const r = new FileReader();
    r.onerror = () => reject(new Error("The file could not be read."));
    r.onload = () => resolve(String(r.result).split(",")[1] || "");
    r.readAsDataURL(f);
  });
}

function Row({ r, onDone }: { r: Missing["items"][number]; onDone: () => void }) {
  const ref = useRef<HTMLInputElement>(null);
  const { toast } = useUI();
  const [err, setErr] = useState("");
  const send = useMutation({
    mutationFn: async (f: File) => apiSend("POST", "/api/logos/admin/manual", { symbol: r.symbol, image: await readImage(f) }),
    onSuccess: () => { toast(`Logo saved for ${r.symbol}.`); onDone(); },
    onError: (e) => setErr(e instanceof ApiError ? msg(e) : (e as Error).message),
  });
  return (
    <tr>
      <td><b>{r.symbol}</b><br /><small className="muted">{r.name}</small></td>
      <td className="num">{r.marketCapCr == null ? "—" : r.marketCapCr.toLocaleString("en-IN")}</td>
      <td><small>{r.reason}</small>{err && <div className="formerr" role="alert">{err}</div>}</td>
      <td>
        <button className="btn" disabled={send.isPending} onClick={() => ref.current?.click()}>{send.isPending ? "Saving…" : "Add logo"}</button>
        <input ref={ref} type="file" hidden accept="image/png,image/jpeg,image/webp,image/gif,image/x-icon" aria-label={`Logo file for ${r.symbol}`}
          onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; setErr(""); if (f) send.mutate(f); }} />
      </td>
    </tr>
  );
}

export function LogoCoverage() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin-logos"], queryFn: () => apiGet<Missing>("/api/logos/admin/missing?limit=50"), retry: false });
  const d = q.data;
  return (
    <section className="card acct-c">
      <h2>Company logos</h2>
      {q.isError ? <div className="formerr">{msg(q.error)}</div> : !d ? <div className="skeleton" style={{ height: 60 }} /> : (
        <>
          <p className="muted">{d.withLogo.toLocaleString("en-IN")} of {d.companies.toLocaleString("en-IN")} companies have a logo. Of the {d.top500} largest, {d.top500WithLogo} do. The others show their initials.
            Logos come from each company's own website; a site that blocks automated requests or has no usable icon stays blank. Add an official image (PNG, JPEG, WebP, GIF or ICO, square-ish, at most 64 KB) for the largest ones first.</p>
          {d.items.length === 0 ? <p className="muted">Every company has a logo.</p> : (
            <div className="tw"><table className="qtt"><thead><tr><th>Company</th><th>Market cap (₹ Cr)</th><th>Why there is no logo</th><th /></tr></thead>
              <tbody>{d.items.map((r) => <Row key={r.symbol} r={r} onDone={() => qc.invalidateQueries({ queryKey: ["admin-logos"] })} />)}</tbody></table></div>
          )}
        </>
      )}
    </section>
  );
}
