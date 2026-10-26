import { describe, expect, it, vi } from "vitest";
import { ApiError } from "./api";
import { asOfLabel, describeUploadError, loadState, uploadStatement, usableReport, validateStatement, winRatePct } from "./portfolioView";

const report: any = {
  sourceFileName: "realizedPnL.pdf", generatedAt: "2026-09-29T17:01:25+00:00",
  profile: { reportPeriod: "01 Apr 2026 – 26 Sep 2026", financialYear: "FY 2026-27", deployedCapital: "₹30,00,000.00" },
  headline: { grossPnl: "₹6,05,374.77", netPnl: "₹5,56,195.73", grossRoi: "20.18%", netRoi: "18.54%" },
  charges: { total: 1, totalFormatted: "₹49,179.04", breakdown: {} },
  summary: { tradeCount: 455, winningTrades: 384, losingTrades: 71, zeroPnlTrades: 0 },
  charts: { monthlyRealizedPnl: [{ month: "Sep", realizedPnl: 10 }] },
};

describe("usableReport", () => {
  it("accepts a complete report and rejects anything with a gap (we never fill one)", () => {
    expect(usableReport(report)).toBe(true);
    expect(usableReport(null)).toBe(false);
    expect(usableReport({})).toBe(false);
    expect(usableReport({ ...report, headline: { ...report.headline, netPnl: "" } })).toBe(false);
    expect(usableReport({ ...report, summary: { ...report.summary, tradeCount: 0 } })).toBe(false);
    expect(usableReport({ ...report, charts: {} })).toBe(false);
  });
});

describe("asOfLabel and winRatePct", () => {
  it("uses the last day the statement covers", () => expect(asOfLabel(report)).toBe("26 Sep 2026"));
  it("falls back to the generated date, then to the period text", () => {
    expect(asOfLabel({ ...report, profile: { ...report.profile, reportPeriod: "FY 2026-27" } })).toMatch(/2026/);
    expect(asOfLabel({ generatedAt: "nope", profile: { ...report.profile, reportPeriod: "FY 2026-27" } })).toBe("FY 2026-27");
  });
  it("computes the win rate from the trade counts", () => { expect(winRatePct(report)).toBe("84.4%"); expect(winRatePct({ summary: { ...report.summary, tradeCount: 0 } })).toBe("–"); });
});

describe("loadState: the page copes when the API cannot be reached", () => {
  it("is ready with a good report", () => expect(loadState(report, null)).toBe("ready"));
  it("is offline for a network failure or a server error, never a blank page", () => {
    expect(loadState(undefined, new TypeError("Failed to fetch"))).toBe("offline");
    expect(loadState(undefined, new ApiError(502, {}))).toBe("offline");
    expect(loadState(undefined, new ApiError(503, { detail: "x" }))).toBe("offline");
  });
  it("is missing when nothing is published (404) or nothing has loaded", () => {
    expect(loadState(undefined, new ApiError(404, { detail: "No uploaded portfolio report is published yet." }))).toBe("missing");
    expect(loadState(undefined, null)).toBe("missing");
  });
  it("is invalid when the server answered with something unusable", () => expect(loadState({ headline: {} }, null)).toBe("invalid"));
});

describe("validateStatement", () => {
  it("accepts a PDF under 15 MB", () => expect(validateStatement({ name: "realizedPnL.PDF", size: 1000 })).toBeNull());
  it("explains each refusal", () => {
    expect(validateStatement(null)).toMatch(/Choose/);
    expect(validateStatement({ name: "pnl.xlsx", size: 10 })).toMatch(/PDF/);
    expect(validateStatement({ name: "a.pdf", size: 0 })).toMatch(/empty/);
    expect(validateStatement({ name: "a.pdf", size: 16 * 1024 * 1024 })).toMatch(/15 MB/);
  });
});

describe("uploadStatement", () => {
  const pdf = () => new File([new Uint8Array([37, 80, 68, 70])], "realizedPnL.pdf", { type: "application/pdf" });
  it("reports progress and returns the new report", async () => {
    const seen: number[] = [];
    const send = vi.fn(async (_fd: FormData, p: (n: number) => void) => { p(40); p(100); return { status: 200, body: report }; });
    const r = await uploadStatement(pdf(), (n) => seen.push(n), send);
    expect(seen).toEqual([40, 100]); expect(r.headline.netPnl).toBe(report.headline.netPnl);
    expect(send.mock.calls[0][0].get("file")).toBeInstanceOf(File);
  });
  it("does not send a wrong file at all", async () => {
    const send = vi.fn();
    await expect(uploadStatement(new File(["x"], "pnl.csv"), () => {}, send as any)).rejects.toThrow(/PDF/);
    expect(send).not.toHaveBeenCalled();
  });
  it("shows the server's validation message, and handles an expired session", async () => {
    await expect(uploadStatement(pdf(), () => {}, async () => ({ status: 400, body: { detail: "File contents do not match a PDF report." } }))).rejects.toThrow("File contents do not match a PDF report.");
    await expect(uploadStatement(pdf(), () => {}, async () => ({ status: 401, body: {} }))).rejects.toThrow(/expired/);
  });
  it("rejects a reply that has no trades in it", async () => {
    await expect(uploadStatement(pdf(), () => {}, async () => ({ status: 200, body: { ...report, summary: { ...report.summary, tradeCount: 0 } } }))).rejects.toThrow(/no trades/);
  });
  it("passes a network failure on", async () => {
    await expect(uploadStatement(pdf(), () => {}, async () => { throw new Error("Could not reach the server."); })).rejects.toThrow(/reach/);
  });
});

describe("describeUploadError", () => {
  it("reads strings, lists and falls back to plain words", () => {
    expect(describeUploadError(400, { detail: "bad" })).toBe("bad");
    expect(describeUploadError(422, { detail: [{ msg: "field required" }] })).toBe("field required");
    expect(describeUploadError(413, {})).toMatch(/15 MB/);
    expect(describeUploadError(500, {})).toMatch(/failed/);
  });
});
