import { bannerLines, useJobsStatus } from "../lib/jobsStatus";

/** Admin Console, Data health tab: everything the background jobs and the freshness checks consider wrong, in one box. Green when nothing is. */
export function JobsBanner() {
  const q = useJobsStatus();
  if (q.isError) return <div className="jobs-banner warn" role="status" data-testid="jobs-banner"><b>Background jobs</b>The job status could not be read.</div>;
  if (!q.data) return null;
  const lines = bannerLines(q.data);
  const bad = lines.some((l) => l.level === "bad");
  return (
    <div className={"jobs-banner " + (bad ? "" : lines.length ? "warn" : "ok")} role={bad ? "alert" : "status"} data-testid="jobs-banner">
      <b>{bad ? "Background jobs need attention" : lines.length ? "Background jobs: notes" : "Background jobs and data are healthy"}</b>
      {lines.length > 0 && <ul>{lines.map((l, i) => <li key={i} className={l.level === "bad" ? "neg" : ""}>{l.text}</li>)}</ul>}
      <span className="muted" style={{ fontSize: 12 }}>Full detail: /api/jobs/status. Checked {q.data.data.checkedAt ? new Date(q.data.data.checkedAt).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" }) + " IST" : "not yet"}.</span>
    </div>
  );
}
