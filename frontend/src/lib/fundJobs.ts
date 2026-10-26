import type { FundJobRow, FundStatus } from "./account";

/** Poll every 5 seconds only while a load runs; otherwise not at all. */
export const fundPollMs = (s?: Pick<FundStatus, "running"> | null): number | false => (s?.running ? 5000 : false);

/** Plain-words line for one job's last result. */
export function fundJobLine(r: FundJobRow | undefined, fmt: (iso: string) => string = (x) => x): string {
  if (!r) return "Never run from here.";
  if (r.state === "starting" || r.state === "running") return r.startedAt ? `Running since ${fmt(r.startedAt)}.` : "Running.";
  const when = r.finishedAt ? ` ${fmt(r.finishedAt)}` : "";
  if (r.state === "done") return `Finished${when}.${r.result ? " " + r.result : ""}`;
  return `Failed${when}${r.rc !== undefined ? ` (exit code ${r.rc})` : ""}.${r.result ? " " + r.result : ""}`;
}
