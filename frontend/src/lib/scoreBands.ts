// The one colour rule for every FinLit score on the site, as the founder set it: green from 70, orange from 50 to under 70, red under 50,
// grey when there is no score. Colour only decorates; the model's own word (Strong / Healthy / Mixed / Weak) and the number carry the meaning,
// and the model's thresholds and labels are not changed here. Also: the market-cap line, and which score badge a plan may see.
import { capSize, nf } from "./format";
import { scoreTone } from "./prism";
import { fmtScore, ratingWord, type TrendTone } from "./prismTechnical";

export type ScoreBand = "hi" | "mid" | "lo" | "na";
export const BAND_GREEN = 70, BAND_ORANGE = 50;
export const scoreBand = (v: number | null | undefined): ScoreBand => (v == null || !Number.isFinite(v) ? "na" : v >= BAND_GREEN ? "hi" : v >= BAND_ORANGE ? "mid" : "lo");
export const BAND_NAME: Record<ScoreBand, string> = { hi: "green", mid: "orange", lo: "red", na: "grey" };
/** The CSS variable holding a band's colour (defined in styles/dash-shared.css). */
export const bandVar = (b: ScoreBand) => (b === "na" ? "var(--faint)" : `var(--band-${b})`);
/** The same colour for TEXT (a word or number on the card), tuned per theme for contrast. */
export const bandInk = (b: ScoreBand) => (b === "na" ? "var(--faint)" : `var(--band-${b}-ink)`);
export const LEGEND: { band: ScoreBand; rule: string }[] = [
  { band: "hi", rule: "70 or more" }, { band: "mid", rule: "50 to 69" }, { band: "lo", rule: "under 50" }, { band: "na", rule: "not enough data" },
];

/** Text for a dot's title and aria-label, e.g. "Quality 76: green, healthy". `word` is the model's own word for the score. */
export function dotLabel(name: string, v: number | null | undefined, word?: string): string {
  const b = scoreBand(v);
  return b === "na" ? `${name}: grey, not enough data` : `${name} ${Math.round(v as number)}: ${BAND_NAME[b]}${word ? ", " + word.toLowerCase() : ""}`;
}

export type Plan = "basic" | "silver" | "gold";
export type BadgeKind = "none" | "basic" | "prism";
/** Which score badge a plan sees at the top of a stock page: Silver the basic FinLit score only, Gold the advanced Prism rating only, Basic none. */
export const badgeFor = (plan: Plan, admin = false): BadgeKind => (plan === "gold" || admin ? "prism" : plan === "silver" ? "basic" : "none");

/** "₹1,23,456 Cr" in Indian grouping; null when the market value is not known. */
export const marketCapText = (cr: number | null | undefined) => (cr == null || !Number.isFinite(cr) || cr <= 0 ? null : `₹${nf(cr, 0)} Cr`);
/** "Market cap ₹4,063 Cr · Small cap" (the size word is the site's own capSize rule). */
export function marketCapLine(cr: number | null | undefined): string | null {
  const t = marketCapText(cr), size = capSize(cr);
  return t ? `Market cap ${t}${size ? " · " + size : ""}` : null;
}
/** Industry for the header: the sub-industry when it adds to the industry, else the industry, else the sector. */
export function industryText(p: { industry?: string | null; subIndustry?: string | null; sector?: string | null }): string | null {
  const i = p.industry?.trim() || null, s = p.subIndustry?.trim() || null;
  if (i && s && s.toLowerCase() !== i.toLowerCase()) return `${i} · ${s}`;
  return i || s || p.sector?.trim() || null;
}

/** The technical scores of a stored Prism report, as the dots need them: the model's rating word (never shown) and the -100..+100 score of each horizon. */
export type TechIn = { score: number | null; rating: string | null };
export type PrismInput = { kind: "loading" | "none" | "hidden" | "locked" }
  | { kind: "report"; final: number | null; word: string; status: string; parts?: Partial<Record<string, number | null>>; short?: TechIn | null; long?: TechIn | null; reason?: string | null; techAsOf?: string | null };
export type BadgeView =
  | { kind: "none" }
  | { kind: "basic"; score: number | null; word: string | null; band: ScoreBand }
  | { kind: "prism"; score: number; word: string; band: ScoreBand; provisional: boolean }
  | { kind: "prism-none" };
/** What the badge at the top of the stock page shows. Silver: the basic FinLit score and nothing of Prism. Gold: the Prism rating and nothing of the basic score.
 *  Basic: no badge (the header is as it was). Gold with no stored (or no usable) rating: "not rated yet" with a link. While the rating loads, or when the server hides it, nothing. */
export function badgeView(plan: Plan, admin: boolean, basic: { overall: number | null; word: string | null }, prism: PrismInput): BadgeView {
  const kind = badgeFor(plan, admin);
  if (kind === "none") return { kind };
  if (kind === "basic") return { kind, score: basic.overall, word: basic.overall == null ? null : basic.word, band: scoreBand(basic.overall) };
  if (prism.kind === "none") return { kind: "prism-none" };
  if (prism.kind !== "report") return { kind: "none" };
  if (prism.final == null || prism.status === "NOT RATED") return { kind: "prism-none" };
  return { kind: "prism", score: prism.final, word: prism.word, band: scoreBand(prism.final), provisional: prism.status === "PROVISIONAL" };
}

/** The reading direction of a Prism fundamental part: every one of the four is "higher is better". Risk is the one people misread: a HIGH Risk score means LOW risk. */
export function partHint(key: string): { short: string; long: string } | null {
  if (key === "risk") return { short: "Higher is better", long: "Higher is better: a higher Risk score means lower risk." };
  return ["fundamental", "valuation", "quality"].includes(key) ? { short: "Higher is better", long: "Higher is better: a higher score is a stronger result." } : null;
}

/** The five word bands of a Prism score, written once so every tooltip quotes the same cut-offs as `partWord` / `scoreTone`. */
export const BAND_RULE = "Strong 80 and above, Healthy 65 to 79, Average 50 to 64, Weak 35 to 49, Poor below 35.";

/* ---- Gold header dots: the six FinLit Prism parameters (4 fundamental, 2 technical) ---- */
export type GoldDot = { key: string; name: string; letter: string; group: "fund" | "tech"; value: number | null; band: ScoreBand; label: string };
/** Fundamental parts in the Prism order, then the two technical horizons. Letter F V Q R S L. */
export const GOLD_DOTS: { key: string; name: string; letter: string; group: "fund" | "tech"; what: string }[] = [
  { key: "fundamental", name: "Fundamentals", letter: "F", group: "fund", what: "how steadily sales and profit grow" },
  { key: "valuation", name: "Valuation", letter: "V", group: "fund", what: "the share price against earnings, book value and its own history" },
  { key: "quality", name: "Quality", letter: "Q", group: "fund", what: "financial strength: borrowing, interest cover, returns, cash backing" },
  { key: "risk", name: "Risk", letter: "R", group: "fund", what: "price swings, largest fall, trading activity, pledged shares" },
  { key: "shortTerm", name: "Short-term technical", letter: "S", group: "tech", what: "recent price trend over weeks" },
  { key: "longTerm", name: "Long-term technical", letter: "L", group: "tech", what: "price trend over months" },
];
/** Trend tone to the shared dot colour: positive green, neutral orange, negative red, grey when absent (the colours the Prism card's technical bars use). */
export const trendBand = (t: TrendTone): ScoreBand => (t === "strongpos" || t === "pos" ? "hi" : t === "neutral" ? "mid" : t === "strongneg" || t === "neg" ? "lo" : "na");
/** "23 Oct 2026" from an ISO date (no time zone shift: the date is read as written). */
export const asOfText = (iso: string): string => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso); return m ? `${Number(m[3])} ${["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][Number(m[2]) - 1]} ${m[1]}` : iso; };
/** The six dots for Gold, or null while the report loads or when the server hides it (nothing is drawn: no flicker). A company with no stored or no usable rating
 *  gets six grey dots whose tooltip says why. */
export function goldDots(prism: PrismInput): GoldDot[] | null {
  if (prism.kind === "loading" || prism.kind === "hidden" || prism.kind === "locked") return null;
  const grey = (reason: string): GoldDot[] => GOLD_DOTS.map((d) => ({ key: d.key, name: d.name, letter: d.letter, group: d.group, value: null, band: "na", label: `${d.name}: grey, ${reason}` }));
  if (prism.kind !== "report") return grey("not rated yet");
  if (prism.status === "NOT RATED") return grey(prism.reason ? `not rated: ${prism.reason.replace(/[.\s]+$/, "")}` : "not rated");
  return GOLD_DOTS.map((d) => {
    const base = { key: d.key, name: d.name, letter: d.letter, group: d.group };
    if (d.group === "fund") {
      const v = prism.parts?.[d.key] ?? null;
      if (v == null || !Number.isFinite(v)) return { ...base, value: null, band: "na" as ScoreBand, label: `${d.name}: grey, not available` };
      const word = scoreTone(v);
      return { ...base, value: v, band: scoreBand(v), label: `${d.name} ${Math.round(v)}: ${BAND_NAME[scoreBand(v)]}, ${word}` };
    }
    const t = d.key === "shortTerm" ? prism.short : prism.long, v = t?.score ?? null;
    if (v == null || !Number.isFinite(v)) return { ...base, value: null, band: "na" as ScoreBand, label: `${d.name}: grey, not available` };
    const w = ratingWord(t?.rating, v), band = trendBand(w.tone);
    return { ...base, value: v, band, label: `${d.name} ${fmtScore(v)}: ${BAND_NAME[band]}, ${w.word.toLowerCase()}${prism.techAsOf ? `, as of ${asOfText(prism.techAsOf)}` : ""}` };
  });
}
