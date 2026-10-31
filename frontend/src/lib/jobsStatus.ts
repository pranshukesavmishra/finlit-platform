import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "./api";

/** What GET /api/jobs/status says (public, read-only): every background job, every dataset's freshness, the admin pause. */
export type JobRow = { name: string; state: string; reason: string | null; ageHours: number | null; slaHours: number | null; late: boolean; overdue: boolean; consecutiveFailures: number; disabledByConfig: boolean; disabledReason: string | null; lastSuccessAt: string | null; nextDueAt: string | null; description?: string };
export type Dataset = { key: string; label: string; status: "fresh" | "late" | "stale" | "unknown"; expected: string | null; actual: string | null; lag: number | null; lagUnit: string | null; jobs: string[]; detail: string };
export type JobsStatus = {
  healthy: boolean; healthNote?: string; overdue: string[]; failing?: string[]; resultsDelayed: boolean; dataFresh: boolean | null;
  supervisor: { alive: boolean; heartbeatAgeSeconds: number | null };
  pause: { paused: boolean; until: string | null; untilIST: string | null; resumesAutomatically: boolean };
  disabledByConfig: { name: string; reason: string }[];
  jobs: JobRow[];
  data: { checkedAt: string | null; dataFresh: boolean | null; datasets: Dataset[]; system?: { diskPercent?: number | null; diskOk?: boolean } };
  canary: { checkedAt: string | null; ok: boolean | null; mismatches: { symbol: string; field: string; ours: number; provider: number; diffPercent: number }[] };
  credentials?: { provider: string; detail: string }[];
};
export const useJobsStatus = (enabled = true) => useQuery({ queryKey: ["jobs-status"], enabled, staleTime: 60_000, refetchInterval: 300_000, retry: 0, queryFn: () => apiGet<JobsStatus>("/api/jobs/status") });

/** The neutral public line when the results jobs are late; null otherwise (no admin detail, no job names). */
export const resultsDelayedNote = (s?: Pick<JobsStatus, "resultsDelayed"> | null): string | null => (s?.resultsDelayed ? "Results refresh is delayed; we are retrying." : null);

export type BannerLine = { level: "bad" | "warn"; text: string };
/** The admin banner: what is wrong, in plain words, most serious first. Empty when everything is fine. */
export function bannerLines(s?: JobsStatus | null): BannerLine[] {
  if (!s) return [];
  const out: BannerLine[] = [];
  if (!s.supervisor.alive) out.push({ level: "bad", text: "The background job supervisor is not reporting. Data jobs may have stopped." });
  for (const c of s.credentials || []) out.push({ level: "bad", text: `The ${c.provider === "dhan" ? "Dhan" : c.provider === "finedge" ? "FinEdge" : c.provider} key is not accepted (${c.detail}). Update it in /opt/finlit/.env.aws.` });
  for (const j of s.jobs.filter((x) => x.overdue)) out.push({ level: "bad", text: `${j.name} is overdue: last success ${j.ageHours == null ? "never" : `${j.ageHours.toFixed(1)} h ago`}, promised every ${j.slaHours} h. ${j.reason || ""}`.trim() });
  for (const d of s.data.datasets.filter((x) => x.status === "stale")) out.push({ level: "bad", text: `${d.label} is stale: expected ${d.expected}, found ${d.actual ?? "nothing"}. ${d.detail}`.trim() });
  if (s.canary.ok === false) out.push({ level: "bad", text: `Canary: ${s.canary.mismatches.slice(0, 3).map((m) => `${m.symbol} ${m.field} differs from the provider by ${m.diffPercent}%`).join("; ")}.` });
  if (s.data.system && s.data.system.diskOk === false) out.push({ level: "bad", text: `Server disk is ${s.data.system.diskPercent}% full.` });
  for (const d of s.disabledByConfig) out.push({ level: "warn", text: `${d.name} is switched off by configuration: ${d.reason}.` });
  if (s.pause.paused) out.push({ level: "warn", text: `Heavy data loads are paused until ${s.pause.untilIST}; they resume automatically.` });
  for (const d of s.data.datasets.filter((x) => x.status === "late")) out.push({ level: "warn", text: `${d.label} is a little late (expected ${d.expected}, found ${d.actual ?? "nothing"}).` });
  return out;
}

/** The same line for pages that are rendered without a query client (a plain fetch, once; an error simply shows nothing). */
export function useResultsDelayedNote(): string | null {
  const [note, setNote] = useState<string | null>(null);
  useEffect(() => { let live = true; apiGet<JobsStatus>("/api/jobs/status").then((s) => { if (live) setNote(resultsDelayedNote(s)); }).catch(() => undefined); return () => { live = false; }; }, []);
  return note;
}
