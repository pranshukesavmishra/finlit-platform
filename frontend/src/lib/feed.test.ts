import { describe, expect, it } from "vitest";
import { inResultsSeason, staleResultsNote } from "./feed";

describe("staleResultsNote", () => {
  it("warns on a weekday in results season when the newest result is more than 2 days old", () => {
    expect(staleResultsNote({ todayIST: "2026-10-30", newestResultInDb: "2026-10-26" })).toBe("The latest results have not been refreshed since 26 Oct 2026. We are checking again every hour.");
  });
  it("stays quiet when fresh, at weekends and outside the season", () => {
    expect(staleResultsNote({ todayIST: "2026-10-30", newestResultInDb: "2026-10-28" })).toBeNull();
    expect(staleResultsNote({ todayIST: "2026-10-31", newestResultInDb: "2026-10-20" })).toBeNull();
    expect(staleResultsNote({ todayIST: "2026-09-10", newestResultInDb: "2026-08-01" })).toBeNull();
    expect(staleResultsNote(undefined)).toBeNull();
  });
  it("says so when nothing is held in season", () => {
    expect(staleResultsNote({ todayIST: "2026-10-30", newestResultInDb: null })).toBe("No results are held yet. We are checking again every hour.");
  });
  it("season windows", () => { expect(inResultsSeason("2026-10-14")).toBe(false); expect(inResultsSeason("2026-10-15")).toBe(true); expect(inResultsSeason("2026-05-31")).toBe(true); expect(inResultsSeason("2026-06-01")).toBe(false); });
});
