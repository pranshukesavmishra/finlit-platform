import { describe, expect, it } from "vitest";
import { fundJobLine, fundPollMs } from "./fundJobs";

describe("fundJobs", () => {
  it("polls only while running", () => {
    expect(fundPollMs({ running: true })).toBe(5000);
    expect(fundPollMs({ running: false })).toBe(false);
    expect(fundPollMs(undefined)).toBe(false);
  });
  it("words each state", () => {
    expect(fundJobLine(null)).toMatch(/Never/);
    expect(fundJobLine({ state: "running", startedAt: "t" })).toBe("Running since t.");
    expect(fundJobLine({ state: "done", finishedAt: "t", result: "ok" })).toBe("Finished t. ok");
    expect(fundJobLine({ state: "failed", rc: 1 })).toBe("Failed (exit code 1).");
  });
});
