// Forgiving search over the measure list for the Compare page. Separate from the screener's own matching on purpose.
//   "EV / CFO", "ev/cfo", "ev cfo", "evcfo" all find EV / CFO; a small typo ("retun on equty") still finds the measure.
export type Searchable = { key: string; label: string; say?: string; group?: string; groupLabel?: string };

/** Lower-case letters and digits only: "EV / CFO" -> "evcfo", "P/E Ratio" -> "peratio". */
export const compact = (s: string): string => s.toLowerCase().normalize("NFKD").replace(/&/g, "and").replace(/[^a-z0-9]+/g, "");
const words = (s: string): string[] => s.toLowerCase().normalize("NFKD").replace(/&/g, " and ").split(/[^a-z0-9]+/).filter(Boolean);

/** Fewest edits (insert, delete, swap two neighbours counts as one) to turn `q` into any part of `hay`. */
export function approxIn(hay: string, q: string, max: number): number {
  const m = q.length;
  if (!m) return 0;
  let prev2: number[] | null = null;
  let prev = Array.from({ length: m + 1 }, (_, i) => i);
  let best = prev[m];
  for (let j = 1; j <= hay.length; j++) {
    const cur = new Array<number>(m + 1);
    cur[0] = 0;   // a match may start anywhere in `hay`
    for (let i = 1; i <= m; i++) {
      const cost = q[i - 1] === hay[j - 1] ? 0 : 1;
      let v = Math.min(prev[i] + 1, cur[i - 1] + 1, prev[i - 1] + cost);
      if (prev2 && i > 1 && q[i - 1] === hay[j - 2] && q[i - 2] === hay[j - 1]) v = Math.min(v, prev2[i - 2] + 1);
      cur[i] = v;
    }
    best = Math.min(best, cur[m]);
    prev2 = prev; prev = cur;
    if (best === 0) break;
  }
  return best <= max ? best : max + 1;
}

const allowed = (len: number) => (len <= 3 ? 0 : len <= 6 ? 1 : 2);

/** Higher is a better match; 0 means no match. */
export function scoreMetric(m: Searchable, query: string): number {
  const qc = compact(query), qw = words(query);
  if (!qc) return 1;
  const label = compact(m.label), key = compact(m.key);
  let s = 0;
  if (label === qc || key === qc) s = 1000;
  else if (label.startsWith(qc)) s = 800;
  else if (key.startsWith(qc)) s = 750;
  else if (label.includes(qc)) s = 600;
  else if (key.includes(qc)) s = 550;
  if (s) return s - Math.min(label.length, 60) / 10;
  // every word typed must be found somewhere in the label, key, group or hint (word start, or a small typo)
  const lw = words(m.label + " " + m.key.replace(/_/g, " ")), gw = words((m.groupLabel || "") + " " + (m.say || ""));
  let total = 0;
  for (const w of qw) {
    if (lw.some((x) => x.startsWith(w))) total += 60;
    else if (gw.some((x) => x.startsWith(w))) total += 25;
    else if (w.length >= 3 && lw.some((x) => x.includes(w))) total += 40;
    else if (w.length >= 4 && lw.some((x) => approxIn(x, w, allowed(w.length)) <= allowed(w.length))) total += 30;
    else if (w.length >= 5 && gw.some((x) => approxIn(x, w, 1) <= 1)) total += 12;
    else {
      // the whole query may be a typo of the label ("evcof" for EV / CFO)
      return qc.length >= 4 && approxIn(label, qc, allowed(qc.length)) <= allowed(qc.length) ? 200 - approxIn(label, qc, 2) * 20 : 0;
    }
  }
  return total;
}

export function searchMetrics<T extends Searchable>(list: T[], query: string): T[] {
  if (!compact(query)) return list;
  return list.map((m) => ({ m, s: scoreMetric(m, query) })).filter((x) => x.s > 0).sort((a, b) => b.s - a.s).map((x) => x.m);
}
