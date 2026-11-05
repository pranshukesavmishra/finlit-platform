/** Show/hide rules of the earnings alert, as one small state machine (no separate "forced" flag that can go stale).
 *
 *  Modes (derived from three facts, so there is no way to be in two at once):
 *   - "dismissed": the reader pressed the x on the in-place card. Nothing shows, not even the edge icon, until a different alert or a reload.
 *   - "inplace":   the reader is on the alert's own section. The card shows.
 *   - "away":      the reader is on another section. The card is hidden and the edge icon shows.
 *   - "opened":    the reader clicked the edge icon while away. The card floats; it closes by Esc, a click outside, the x, or by scrolling back to its section.
 *
 *  The one rule that matters: every change of section (away <-> in place) clears "opened", and being in place never depends on any earlier click.
 *  Scrolling back into the section therefore always re-shows the in-place card, whatever happened before and however many times it is repeated. */
export type PlfState = { away: boolean; opened: boolean; dismissed: boolean };
export type PlfEvent =
  | { type: "scroll"; away: boolean }   // a fresh reading of where the reader is
  | { type: "open" }                    // edge icon clicked
  | { type: "close" }                   // Esc, click outside, or the x on the floating card: back to the edge icon
  | { type: "dismiss" }                 // the x on the in-place card
  | { type: "show" }                    // the "Show details" button of the results bar: brings a dismissed alert back
  | { type: "reset" };                  // a different alert or company
export type PlfMode = "inplace" | "away" | "opened" | "dismissed";

export const PLF_START: PlfState = { away: false, opened: false, dismissed: false };

export function plfReduce(s: PlfState, e: PlfEvent): PlfState {
  switch (e.type) {
    case "scroll": return e.away === s.away ? s : { ...s, away: e.away, opened: false };
    case "open": return s.away && !s.dismissed && !s.opened ? { ...s, opened: true } : s;
    case "close": return s.opened ? { ...s, opened: false } : s;
    case "dismiss": return s.dismissed && !s.opened ? s : { ...s, dismissed: true, opened: false };
    case "show": return { ...s, dismissed: false, opened: false };
    case "reset": return { ...s, dismissed: false, opened: false };
  }
}

export function plfMode(s: PlfState): PlfMode {
  return s.dismissed ? "dismissed" : !s.away ? "inplace" : s.opened ? "opened" : "away";
}
export const plfCardShown = (m: PlfMode) => m === "inplace" || m === "opened";
export const plfEdgeShown = (m: PlfMode) => m === "away";
