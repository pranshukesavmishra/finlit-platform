import { describe, expect, it } from "vitest";
import { bannerLines, resultsDelayedNote, type JobsStatus } from "./jobsStatus";

const ok: JobsStatus = { healthy: true, overdue: [], resultsDelayed: false, dataFresh: true, supervisor: { alive: true, heartbeatAgeSeconds: 20 }, pause: { paused: false, until: null, untilIST: null, resumesAutomatically: true },
  disabledByConfig: [], jobs: [], data: { checkedAt: "2026-10-31T08:00:00Z", dataFresh: true, datasets: [] }, canary: { checkedAt: null, ok: null, mismatches: [] } };
const job = (o: object) => ({ name: "technicals", state: "waiting", reason: "waiting for memory", ageHours: 456, slaHours: 12, late: true, overdue: true, consecutiveFailures: 0, disabledByConfig: false, disabledReason: null, lastSuccessAt: null, nextDueAt: null, ...o });

describe("results line", () => {
  it("is neutral and only appears when the results jobs are late", () => {
    expect(resultsDelayedNote({ resultsDelayed: true })).toBe("Results refresh is delayed; we are retrying.");
    expect(resultsDelayedNote({ resultsDelayed: false })).toBeNull();
    expect(resultsDelayedNote(undefined)).toBeNull();
  });
});

describe("admin banner lines", () => {
  it("is empty when everything is fine", () => expect(bannerLines(ok)).toEqual([]));
  it("lists overdue jobs, stale datasets, a dead supervisor and refused keys as problems", () => {
    const lines = bannerLines({ ...ok, supervisor: { alive: false, heartbeatAgeSeconds: 900 }, credentials: [{ provider: "dhan", detail: "HTTP 401" }], jobs: [job({}) as never],
      data: { checkedAt: null, dataFresh: false, datasets: [{ key: "technicals", label: "Technical views", status: "stale", expected: "2026-10-30", actual: "2026-10-12", lag: 18, lagUnit: "days", jobs: ["technicals"], detail: "506 of 510 behind" }] } });
    expect(lines.every((l) => l.level === "bad")).toBe(true);
    expect(lines.map((l) => l.text).join("\n")).toMatch(/supervisor is not reporting[\s\S]*Dhan key is not accepted[\s\S]*technicals is overdue: last success 456\.0 h ago, promised every 12 h[\s\S]*Technical views is stale: expected 2026-10-30, found 2026-10-12/);
  });
  it("lists the pause and config switches as notes, not problems", () => {
    const lines = bannerLines({ ...ok, pause: { paused: true, until: "x", untilIST: "31 Oct 14:35 IST", resumesAutomatically: true }, disabledByConfig: [{ name: "mf", reason: "ETF and fund loads are switched off: set FUND_LOADS_ENABLED=1" }] });
    expect(lines.map((l) => l.level)).toEqual(["warn", "warn"]);
    expect(lines[1].text).toContain("paused until 31 Oct 14:35 IST; they resume automatically");
  });
});
