// "Follow the score" on the fund page card (Gold): a message when the score band changes or moves by N points between two weekly runs.
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiGet, apiSend, ApiError } from "../lib/api";
import { Icon } from "../lib/icons";
import type { ScoreAlert } from "../lib/mfScoreUp";
import "../styles/mfup.css";

export function ScoreAlertButton({ code = 0, symbol = "", name }: { code?: number; symbol?: string; name: string }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false), [kind, setKind] = useState<"band" | "move">("band"), [pts, setPts] = useState("5"), [email, setEmail] = useState(false), [err, setErr] = useState("");
  const mine = useQuery<{ alerts: ScoreAlert[] }, ApiError>({ queryKey: ["mfscore", "alerts"], queryFn: () => apiGet("/api/mf/score-alerts"), staleTime: 60_000, retry: false });
  const key = code ? `mf:${code}` : `etf:${symbol.toUpperCase()}`;
  const have = (mine.data?.alerts || []).filter((a) => a.key === key);
  const add = useMutation({
    mutationFn: () => apiSend("POST", "/api/mf/score-alerts", { ...(code ? { code } : { symbol }), kind, ...(kind === "move" ? { points: Number(pts) } : {}), channels: email ? ["app", "email"] : ["app"] }),
    onSuccess: () => { setErr(""); qc.invalidateQueries({ queryKey: ["mfscore", "alerts"] }); }, onError: (e) => setErr(e instanceof ApiError ? e.body.detail || "Could not save." : "Could not save."),
  });
  const drop = useMutation({ mutationFn: (id: string) => apiSend("DELETE", `/api/mf/score-alerts/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["mfscore", "alerts"] }) });
  return (
    <div className="mfu-alert">
      <button type="button" className="btn ghost sm" aria-expanded={open} onClick={() => setOpen(!open)}><Icon name="bell" /> {have.length ? `Following score (${have.length})` : "Follow this score"}</button>
      {open && (
        <div className="mfu-pop" role="dialog" aria-label={`Score alerts for ${name}`}>
          <p className="faint">Get a message when the FinLit Mutual Fund Health Score of {name} changes. It describes the past; it is not advice.</p>
          <label><input type="radio" name="sak" checked={kind === "band"} onChange={() => setKind("band")} /> Its band changes (for example Healthy to Average)</label>
          <label><input type="radio" name="sak" checked={kind === "move"} onChange={() => setKind("move")} /> It moves by <input type="number" min={1} max={50} value={pts} onChange={(e) => setPts(e.target.value)} aria-label="Points" className="mfu-n" /> points or more between weekly runs</label>
          <label><input type="checkbox" checked={email} onChange={() => setEmail(!email)} /> Also email me</label>
          {err && <p className="formerr" role="alert">{err}</p>}
          <button type="button" className="btn sm" disabled={add.isPending} onClick={() => add.mutate()}>Follow</button>
          {have.length > 0 && <ul className="mfu-mine">{have.map((a) => <li key={a.id}>{a.kind === "band" ? "Band changes" : `Moves ${a.points}+ points`}<button type="button" className="mf-linkbtn" onClick={() => drop.mutate(a.id)}>Remove</button></li>)}</ul>}
        </div>)}
    </div>
  );
}
