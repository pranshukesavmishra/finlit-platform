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

/** "14:35 IST" (with the date when it is not today in IST), from an ISO instant. */
export function istClock(iso: string, now: Date = new Date()): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const fmt = (o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", ...o }).format(d);
  const day = (x: Date) => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(x);
  const time = `${fmt({ hour: "2-digit", minute: "2-digit", hour12: false })} IST`;
  return day(d) === day(now) ? time : `${fmt({ day: "numeric", month: "short" })} ${time}`;
}

export function pauseText(s: Pick<SystemStatus, "loadsEnabled" | "pausedUntil" | "pausedBy" | "pauseWasLegacy">, now: Date = new Date()): string | null {
  if (s.loadsEnabled || !s.pausedUntil) return null;
  return `Paused until ${istClock(s.pausedUntil, now)}, resumes automatically.` + (s.pauseWasLegacy ? " (An old switch with no end time was found; it ends 30 minutes after it was first seen.)" : "") + (s.pausedBy ? ` Set by ${s.pausedBy}.` : "");
}

export const PAUSE_CHOICES: { minutes: number; label: string }[] = [{ minutes: 30, label: "30 minutes" }, { minutes: 120, label: "2 hours" }, { minutes: 720, label: "12 hours" }];

export function loadsText(s: Pick<SystemStatus, "loadsEnabled" | "bootEnvOff" | "fundEnvOff"> & Partial<Pick<SystemStatus, "pausedUntil" | "pausedBy" | "pauseWasLegacy">>): string {
  if (!s.loadsEnabled) return pauseText({ loadsEnabled: false, pausedUntil: s.pausedUntil ?? null, pausedBy: s.pausedBy ?? null, pauseWasLegacy: s.pauseWasLegacy }) ?? "Heavy data loads are paused.";
  return s.bootEnvOff || s.fundEnvOff ? "Switch is on; some loads are still off in the server settings." : "Heavy data loads are running.";
}
