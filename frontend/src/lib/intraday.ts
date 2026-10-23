// Intraday chart helpers: Indian time whatever the visitor's own time zone, the 1D time axis, session breaks, and the status line.
import type { Intraday } from "./api";

const TZ = "Asia/Kolkata";
export const OPEN_MIN = 9 * 60 + 15, CLOSE_MIN = 15 * 60 + 30;   // the continuous session, minutes after midnight IST

/** Minutes after midnight in Indian time (the server sends +05:30, but any offset is read correctly). */
export const istMinutes = (iso: string) => (((Math.floor(Date.parse(iso) / 60000) + 330) % 1440) + 1440) % 1440;

/** "09:15" in Indian time. */
export const hhmm = (min: number) => `${String(Math.floor(min / 60)).padStart(2, "0")}:${String(min % 60).padStart(2, "0")}`;
export const istTime = (iso: string) => hhmm(istMinutes(iso));

/** A trading day ("2026-10-23") or the date part of a time, as "Fri, 23 Oct" (with the year when asked). */
export function istDay(isoOrDay: string, year = false) {
  const d = new Date(isoOrDay.length === 10 ? isoOrDay + "T12:00:00+05:30" : isoOrDay);
  return Number.isNaN(d.getTime()) ? isoOrDay : d.toLocaleDateString("en-IN", { timeZone: TZ, weekday: "short", day: "numeric", month: "short", ...(year ? { year: "numeric" } : {}) });
}

/** The Indian date ("2026-10-23") of a time. */
export const istDate = (iso: string) => new Date(Date.parse(iso) + 330 * 60000).toISOString().slice(0, 10);

/** The span a bar covers, "11:41–11:42"; an hourly bar ends at the close at the latest ("15:15–15:30"). */
export function barSpan(iso: string, interval: number) {
  const s = istMinutes(iso), e = s < CLOSE_MIN ? Math.min(s + interval, CLOSE_MIN) : s + interval;
  return `${hhmm(s)}–${hhmm(e)}`;
}

/** 1D time axis: the whole session (09:15 to 15:30), widened to any bar outside it (the 09:07 pre-open auction bar), so a session in
 *  progress fills only the part of the day that has passed. */
export function dayDomain(t: string[], interval: number): [number, number] {
  const m = t.map(istMinutes);
  return [Math.min(OPEN_MIN, ...m), Math.max(CLOSE_MIN, ...m.map((x) => x + interval))];
}

/** Time labels for the 1D axis: fewer on a phone. */
export const dayTicks = (width: number) => (width < 520 ? [555, 660, 780, 930] : [555, 600, 660, 720, 780, 840, 930]);

/** A session's label on the multi-day axis: "Fri 23" for 5D, "23 Oct" for 1M. */
export function axisDay(iso: string, range: string) {
  const d = new Date(iso);
  return (range === "5D" ? d.toLocaleDateString("en-IN", { timeZone: TZ, weekday: "short", day: "numeric" }) : d.toLocaleDateString("en-IN", { timeZone: TZ, day: "numeric", month: "short" })).replace(",", "");
}

/** Index of the first bar of each session, for the multi-day axis (one label and a faint divider per session). */
export function sessionStarts(t: string[]): number[] {
  const out: number[] = [];
  t.forEach((x, i) => { if (i === 0 || istDate(x) !== istDate(t[i - 1])) out.push(i); });
  return out;
}

/** Change from the open of the first bar to the last close, in per cent. */
export function changePct(d: Intraday): number | null {
  const s = d.series;
  if (!s || s.c.length < 1 || !s.o[0]) return null;
  return (s.c[s.c.length - 1] / s.o[0] - 1) * 100;
}

const BAR = (n: number) => (n === 60 ? "hourly" : `${n}-minute`);

/** What the chart shows and how fresh it is, in words. Never claims a holiday: only what the data and the clock say. */
export function status(d: Intraday): { title: string; note: string | null; asOf: string } {
  const asOf = `${d.source} (${d.exchange}) · ${BAR(d.interval)} bars · as of ${istTime(d.asOf)} IST${istDate(d.asOf) !== d.session ? ", " + istDay(d.asOf) : ""}`;
  if (!d.session) return { title: "No recent trades", note: d.detail ?? null, asOf };
  const span = d.sessions.length > 1 ? `${istDay(d.sessions[0])} to ${istDay(d.session)}` : istDay(d.session, true);
  if (d.range !== "1D") return { title: span, note: d.stale ? d.detail ?? null : null, asOf };
  const today = d.session === d.today && !d.stale;
  const title = today ? (d.phase === "closed" ? `Today's session, closed · ${istDay(d.session)}` : d.phase === "pre_open" ? `Pre-open · ${istDay(d.session)}` : `Live · ${istDay(d.session)}`) : `Last session · ${istDay(d.session, true)}`;
  const note = d.stale ? d.detail ?? null
    : today ? null
      : d.phase === "open" ? "No trade in this stock today so far."
        : d.phase === "pre_open" ? "Today's session has not opened yet."
          : "The market is closed.";
  return { title, note, asOf };
}
