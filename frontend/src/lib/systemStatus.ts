import type { SystemStatus } from "./account";

/** "3 h 5 min", "12 min", "under a minute". */
export function uptimeText(s: number): string {
  const m = Math.floor(Math.max(s, 0) / 60);
  if (m < 1) return "under a minute";
  if (m < 60) return `${m} min`;
  if (m < 1440) return `${Math.floor(m / 60)} h ${m % 60} min`;
  return `${Math.floor(m / 1440)} d ${Math.floor((m % 1440) / 60)} h`;
}

export function memoryText(m: SystemStatus["memory"]): string {
  if (m.usedMb == null || m.availableMb == null) return "Memory: not available.";
  return `Memory: ${m.usedMb} MB used, ${m.availableMb} MB free${m.totalMb ? ` of ${m.totalMb} MB` : ""}.`;
}

export function loadsText(s: Pick<SystemStatus, "loadsEnabled" | "bootEnvOff" | "fundEnvOff">): string {
  if (!s.loadsEnabled) return "Heavy data loads are paused.";
  return s.bootEnvOff || s.fundEnvOff ? "Switch is on; some loads are still off in the server settings." : "Heavy data loads are running.";
}
