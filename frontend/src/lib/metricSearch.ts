// Tolerant metric search: "EV / CFO", "ev/cfo", "EV-CFO", "ev cfo" all find EV/CFO. Pure, so it is tested without the page.
const ALIASES: Record<string, string[]> = {
  pe: ["pe", "p/e", "price earnings", "price to earnings"], pb: ["pb", "p/b", "price to book"], ps: ["ps", "price to sales"],
  roe: ["roe", "return on equity"], roce: ["roce", "return on capital employed"], roa: ["roa"], eps: ["eps"], opm: ["opm"], npm: ["npm"],
  operating_margin: ["opm"], net_margin: ["npm"], market_cap: ["mcap", "market size", "market capitalisation"], price: ["cmp", "ltp", "current price"],
  debt_to_equity: ["de", "d/e", "gearing"], interest_coverage: ["icr", "icr"], net_profit: ["pat"], dividend_yield: ["dy", "div yield"],
  op_profit: ["ebitda", "operating profit annual"], ev_ebitda: ["ev ebitda"], ev_cfo: ["ev cfo"],
};
export const tokens = (s: string): string[] => s.toLowerCase().normalize("NFKD").replace(/[̀-ͯ]/g, "").split(/[^a-z0-9]+/).filter(Boolean);
const compact = (s: string) => tokens(s).join("");

/** Edit distance (insert, delete, replace, swap of neighbours). */
export function distance(a: string, b: string): number {
  const d: number[][] = Array.from({ length: a.length + 1 }, (_, i) => [i, ...Array(b.length).fill(0)]);
  for (let j = 0; j <= b.length; j++) d[0][j] = j;
  for (let i = 1; i <= a.length; i++) for (let j = 1; j <= b.length; j++) {
    d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
  }
  return d[a.length][b.length];
}
const allow = (n: number) => (n <= 3 ? 0 : n <= 5 ? 1 : 2);

/** 0 = no match; higher is better. */
export function score(query: string, label: string, aliases: string[] = []): number {
  const qt = tokens(query), qc = qt.join("");
  if (!qc) return 0;
  let best = 0;
  for (const target of [label, ...aliases]) {
    const tt = tokens(target), tc = tt.join("");
    if (!tc) continue;
    if (qc === tc) best = Math.max(best, 100);
    else if (tc.startsWith(qc)) best = Math.max(best, 90);
    else if (qt.every((q) => tt.some((t) => t.startsWith(q)))) best = Math.max(best, 80);
    else if (qc.length >= 4 && tc.includes(qc)) best = Math.max(best, 60);
    else {
      const near = qt.every((q) => tt.some((t) => distance(q, t) <= allow(q.length) || (q.length >= 4 && distance(q, t.slice(0, q.length)) <= allow(q.length))));
      const whole = qc.length >= 4 && distance(qc, tc.slice(0, qc.length)) <= allow(qc.length);
      if (near || whole) best = Math.max(best, 40);
    }
  }
  return best;
}

export function rankMetrics<T extends { key: string; label: string }>(items: T[], query: string): T[] {
  if (!tokens(query).length) return items;
  return items.map((m, i) => ({ m, i, s: score(query, m.label, ALIASES[m.key] || []) })).filter((x) => x.s > 0).sort((a, b) => b.s - a.s || a.i - b.i).map((x) => x.m);
}
export const matchesMetric = (query: string, m: { key: string; label: string }) => score(query, m.label, ALIASES[m.key] || []) > 0;
