import { describe, expect, it } from "vitest";
import { loadsText, memoryText, uptimeText } from "./systemStatus";

describe("systemStatus", () => {
  it("formats uptime", () => {
    expect(uptimeText(20)).toBe("under a minute");
    expect(uptimeText(720)).toBe("12 min");
    expect(uptimeText(3 * 3600 + 300)).toBe("3 h 5 min");
    expect(uptimeText(2 * 86400 + 3600)).toBe("2 d 1 h");
  });
  it("formats memory and loads", () => {
    expect(memoryText({ totalMb: 512, usedMb: 400, availableMb: 112 })).toBe("Memory: 400 MB used, 112 MB free of 512 MB.");
    expect(memoryText({ totalMb: null, usedMb: null, availableMb: null })).toBe("Memory: not available.");
    expect(loadsText({ loadsEnabled: false, bootEnvOff: false, fundEnvOff: false })).toMatch(/paused/);
    expect(loadsText({ loadsEnabled: true, bootEnvOff: false, fundEnvOff: false })).toMatch(/running/);
  });
});
