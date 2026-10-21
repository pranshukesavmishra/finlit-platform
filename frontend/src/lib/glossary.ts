// Glossary data (generated from backend/finlit/normalize/glossary_data.json by backend/scripts/sync_glossary.py) and search.
import data from "../content/glossary.json";

export type Term = { id: string; term: string; letter: string; topic: string; meaning: string; why: string; how: string; formula: string; finlit: string; aliases: string[] };
export const TERMS = data.terms as Term[];
export const TOPICS = data.topics as string[];
export const LETTERS = ["0–9", ..."ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("")];

/** Lower-case letters and digits only, so "EV / CFO", "ev-cfo" and "EVCFO" are the same. */
export const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "");

function within1(a: string, b: string): boolean {
  if (Math.abs(a.length - b.length) > 1) return false;
  let i = 0, j = 0, edits = 0;
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) { i++; j++; continue; }
    if (++edits > 1) return false;
    if (a.length > b.length) i++; else if (a.length < b.length) j++; else { i++; j++; }
  }
  return edits + (a.length - i) + (b.length - j) <= 1;
}

/** Score 0 = no match. Names and aliases first, then the text; one typo is tolerated in words of 4+ letters. */
export function score(t: Term, q: string): number {
  const nq = norm(q);
  if (!nq) return 1;
  const names = [t.term, ...t.aliases].map(norm);
  if (names.some((n) => n === nq)) return 100;
  if (names.some((n) => n.startsWith(nq))) return 80;
  if (names.some((n) => n.includes(nq))) return 60;
  const body = norm(`${t.meaning} ${t.why} ${t.how} ${t.formula}`);
  if (body.includes(nq)) return 30;
  if (nq.length >= 4) {
    const words = [t.term, ...t.aliases].join(" ").toLowerCase().split(/[^a-z0-9]+/).filter((w) => w.length >= 4);
    if (words.some((w) => within1(w, nq)) || names.some((n) => n.length >= 4 && n.length <= nq.length + 1 && within1(n, nq))) return 20;
  }
  return 0;
}

export function search(q: string, pool: Term[] = TERMS): Term[] {
  return pool.map((t) => [t, score(t, q)] as const).filter(([, s]) => s > 0).sort((a, b) => b[1] - a[1] || a[0].term.localeCompare(b[0].term)).map(([t]) => t);
}

export const termOfTheDay = (): Term => TERMS[Math.floor(Date.now() / 86_400_000) % TERMS.length];
