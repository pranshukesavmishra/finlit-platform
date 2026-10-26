// What the Portfolio page and the Home "Performance" section need from the portfolio report, as plain functions
// (so they are tested without a browser): is a report usable, what is its "as of" date, what happened when the
// server could not be reached, and the checks and upload for the admin "Upload latest statement" control.
import { ApiError, apiUrl } from "./api";
import type { PortfolioReport } from "./siteApi";
import { adminToken } from "./adminSession";

export const MAX_STATEMENT_BYTES = 15 * 1024 * 1024;   // the server refuses anything larger (413)

/** A report we are willing to show numbers from: every figure the page prints must be present. Never fill a gap. */
export function usableReport(r: unknown): r is PortfolioReport {
  const d = r as Partial<PortfolioReport> | null | undefined;
  return !!d && typeof d === "object"
    && !!d.headline?.netPnl && !!d.headline?.netRoi && !!d.profile?.reportPeriod
    && typeof d.summary?.tradeCount === "number" && d.summary.tradeCount > 0 && typeof d.summary.winningTrades === "number"
    && Array.isArray(d.charts?.monthlyRealizedPnl) && !!d.charges?.totalFormatted;
}

/** The last day the statement covers ("26 Sep 2026" from "01 Apr 2026 – 26 Sep 2026"), else the day it was generated. */
export function asOfLabel(r: Pick<PortfolioReport, "profile" | "generatedAt">): string {
  const end = r.profile.reportPeriod.split(/\s[–-]\s/)[1]?.trim();
  if (end) return end;
  const g = new Date(r.generatedAt);
  return isNaN(+g) ? r.profile.reportPeriod : g.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export const winRatePct = (r: Pick<PortfolioReport, "summary">): string => r.summary.tradeCount ? ((r.summary.winningTrades / r.summary.tradeCount) * 100).toFixed(1) + "%" : "–";

export type LoadState = "ready" | "offline" | "missing" | "invalid";
/** Why the report is not on screen: the server could not be reached (network error / 5xx), has none published (404), or sent something unusable. */
export function loadState(data: unknown, error: unknown): LoadState {
  if (usableReport(data)) return "ready";
  if (error instanceof ApiError) return error.status === 404 ? "missing" : "offline";
  if (error) return "offline";
  return data ? "invalid" : "missing";
}

/** Null when the file can be sent; otherwise a sentence for the person. Mirrors the server's checks (it checks again). */
export function validateStatement(f: { name: string; size: number } | null | undefined): string | null {
  if (!f) return "Choose the realised P&L statement (a PDF) first.";
  if (!/\.pdf$/i.test(f.name)) return "The statement must be a PDF file (.pdf).";
  if (f.size <= 0) return "That file is empty.";
  if (f.size > MAX_STATEMENT_BYTES) return "That file is larger than 15 MB, the most we accept.";
  return null;
}

/** POST the statement with upload progress (fetch cannot report it). Resolves with the parsed report; rejects with Error(message for the person). */
export function uploadStatement(file: File, onProgress: (pct: number) => void, send: (fd: FormData, onProgress: (pct: number) => void) => Promise<{ status: number; body: any }> = xhrSend): Promise<PortfolioReport> {
  const bad = validateStatement(file);
  if (bad) return Promise.reject(new Error(bad));
  const fd = new FormData(); fd.append("file", file);
  return send(fd, onProgress).then(({ status, body }) => {
    if (status === 401) throw new Error("Your admin session has expired. Open the content tools again, then retry.");
    if (status < 200 || status >= 300) throw new Error(describeUploadError(status, body));
    if (!usableReport(body)) throw new Error("The server read the file but found no trades in it. Check that it is the realised P&L statement.");
    return body;
  });
}

/** FastAPI sends {detail: "..."} or a list of validation problems; anything else gets a plain sentence. */
export function describeUploadError(status: number, body: any): string {
  const d = body?.detail;
  if (typeof d === "string" && d.trim()) return d;
  if (Array.isArray(d) && d[0]?.msg) return String(d[0].msg);
  if (status === 413) return "That file is larger than 15 MB, the most we accept.";
  if (status === 422) return "The file could not be read as a realised P&L statement.";
  return "The upload failed. Please try again.";
}

function xhrSend(fd: FormData, onProgress: (pct: number) => void): Promise<{ status: number; body: any }> {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open("POST", apiUrl("/api/portfolio/admin/upload"));
    x.setRequestHeader("Accept", "application/json");
    const t = adminToken(); if (t) x.setRequestHeader("Authorization", `Bearer ${t}`);
    x.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100)); };
    x.onload = () => { let body: any = {}; try { body = x.responseText ? JSON.parse(x.responseText) : {}; } catch { /* not JSON */ } resolve({ status: x.status, body }); };
    x.onerror = () => reject(new Error("Could not reach the server. Check your connection and try again."));
    x.ontimeout = () => reject(new Error("The upload took too long. Please try again."));
    x.timeout = 120_000;
    x.send(fd);
  });
}
