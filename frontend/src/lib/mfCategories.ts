// AMFI fund categories for the /funds dashboard: which tab (Equity, Hybrid, Debt, Solution Oriented, Others) and which sub-category each AMFI category
// name belongs to, the friendly names, and the six quick cards. AMFI uses two generations of names side by side ("Equity Scheme - Large Cap Fund" and
// "Equity Schemes - Large Cap Fund", "Debt Scheme - Low Duration Fund" and "Income/Debt Oriented Schemes - Ultra Short to Short Term Fund") plus old
// category lines without a group ("ELSS", "Income"), so one sub-category can cover several AMFI names.
// The server has the same table (backend/finlit/mf.py `classify`, used for its `group=` filter and the checklist's peer groups): keep the two in step.

export type TabKey = "equity" | "hybrid" | "debt" | "solution" | "other";
export const TABS: { key: TabKey; label: string }[] = [
  { key: "equity", label: "Equity" }, { key: "hybrid", label: "Hybrid" }, { key: "debt", label: "Debt" }, { key: "solution", label: "Solution Oriented" }, { key: "other", label: "Others" },
];
export const TAB_KEYS = TABS.map((t) => t.key);
export const tabLabel = (k: TabKey | "all") => (k === "all" ? "All" : TABS.find((t) => t.key === k)!.label);

export type Classified = { tab: TabKey; key: string; label: string };

/** Lower case, accents and apostrophes gone, "&" as "and", anything else not a letter or digit as one space. */
export function cnorm(s: string): string {
  const t = (s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[’'`*]/g, "").replace(/&/g, " and ");
  return t.replace(/[^a-z0-9]+/g, " ").replace(/\s+/g, " ").trim();
}

const GROUP_TABS: [RegExp, TabKey][] = [
  [/^equity schemes?\b/, "equity"], [/^hybrid schemes?\b/, "hybrid"], [/^(debt schemes?|income debt oriented schemes?)\b/, "debt"],
  [/^(solution oriented schemes?|childrens? funds?|life cycle funds?)\b/, "solution"],
  [/^(other schemes?|index funds?|exchange traded funds?|fund of funds|overseas fund of funds)\b/, "other"],
];
const LEGACY: Record<string, Classified> = {
  elss: { tab: "equity", key: "elss", label: "ELSS (Tax Savings)" }, growth: { tab: "equity", key: "equity-other", label: "Equity - Other" },
  income: { tab: "debt", key: "fixed-term", label: "Fixed Term & Interval" }, gilt: { tab: "debt", key: "gilt", label: "Gilt" }, liquid: { tab: "debt", key: "liquid", label: "Liquid" },
  "money market": { tab: "debt", key: "money-market", label: "Money Market" }, balanced: { tab: "hybrid", key: "hybrid-other", label: "Hybrid - Other" },
};
const SUBS: Record<TabKey, [RegExp, string, string][]> = {
  equity: [
    [/\bcontra\b/, "contra", "Contra"], [/\bdividend yield\b/, "dividend-yield", "Dividend Yield"], [/\belss\b|\btax saver\b/, "elss", "ELSS (Tax Savings)"],
    [/\bflexi ?cap\b/, "flexi-cap", "Flexi Cap"], [/\bfocused\b/, "focused", "Focused"], [/\blarge and mid ?cap\b/, "large-mid-cap", "Large & Mid Cap"],
    [/\blarge ?cap\b/, "large-cap", "Large Cap"], [/\bmid ?cap\b/, "mid-cap", "Mid Cap"], [/\bmulti ?cap\b/, "multi-cap", "Multi Cap"],
    [/\bsmall ?cap\b/, "small-cap", "Small Cap"], [/\bsectoral\b|\bthematic\b/, "sectoral-thematic", "Sectoral / Thematic"], [/\bvalue\b/, "value", "Value"],
    [/(?:)/, "equity-other", "Equity - Other"],
  ],
  debt: [
    [/\bovernight\b/, "overnight", "Overnight"], [/\bliquid\b/, "liquid", "Liquid"], [/\bultra short to short\b|\blow duration\b/, "low-duration", "Low Duration"],
    [/\bultra short\b/, "ultra-short", "Ultra Short Duration"], [/\bmoney market\b/, "money-market", "Money Market"],
    [/\bmedium to long\b/, "medium-long-duration", "Medium to Long Duration"], [/\bmedium (duration|term)\b/, "medium-duration", "Medium Duration"],
    [/\bshort (duration|term)\b/, "short-duration", "Short Duration"], [/\blong (duration|term)\b/, "long-duration", "Long Duration"],
    [/\bdynamic (bond|term)\b/, "dynamic-bond", "Dynamic Bond"], [/\bcorporate bond\b/, "corporate-bond", "Corporate Bond"],
    [/\bcredit risk\b/, "credit-risk", "Credit Risk"], [/\bbanking and psu\b/, "banking-psu", "Banking & PSU"],
    [/\b10 ?year\b|\bconstant (duration|maturity)\b/, "gilt-10y", "Gilt, 10-year Constant Duration"], [/\bgilt\b/, "gilt", "Gilt"],
    [/\bfloat(er|ing)\b/, "floater", "Floater"], [/\bfixed term\b|\binterval\b/, "fixed-term", "Fixed Term & Interval"], [/(?:)/, "debt-other", "Debt - Other"],
  ],
  hybrid: [
    [/\bconservative\b/, "conservative-hybrid", "Conservative Hybrid"], [/\bbalanced hybrid\b/, "balanced-hybrid", "Balanced Hybrid"],
    [/\bbalanced advantage\b|\bdynamic asset allocation\b/, "balanced-advantage", "Balanced Advantage / Dynamic Asset Allocation"],
    [/\baggressive\b/, "aggressive-hybrid", "Aggressive Hybrid"], [/\bmulti asset\b/, "multi-asset", "Multi Asset Allocation"],
    [/\barbitrage\b/, "arbitrage", "Arbitrage"], [/\bequity savings\b/, "equity-savings", "Equity Savings"], [/(?:)/, "hybrid-other", "Hybrid - Other"],
  ],
  solution: [
    [/\bretirement\b/, "retirement", "Retirement"], [/\bchild/, "childrens", "Children's"], [/\blife cycle\b/, "life-cycle", "Life Cycle"],
    [/(?:)/, "solution-other", "Solution Oriented - Other"],
  ],
  other: [   // matched against the whole name: the group says as much as the rest here
    [/\bgold\b/, "gold-etf", "Gold ETFs"], [/\bsilver\b/, "silver-etf", "Silver ETFs"],
    [/^index funds? debt\b/, "index-debt", "Index Funds (Debt)"], [/\bindex funds?\b/, "index-funds", "Index Funds"],
    [/\bdebt etf\b/, "etf-debt", "ETFs (Debt)"], [/\betfs?\b|\bexchange traded\b/, "etf", "ETFs (Other)"],
    [/\boverseas\b/, "fof-overseas", "FoF Overseas"], [/\bfof\b|\bfund of funds\b/, "fof-domestic", "FoF Domestic"], [/(?:)/, "other", "Other"],
  ],
};

const cache = new Map<string, Classified>();
/** AMFI category name -> its tab, sub-category key and friendly name. Every name gets one; anything unrecognised lands in Others. */
export function classify(category: string): Classified {
  const hit = cache.get(category);
  if (hit) return hit;
  const i = category.indexOf(" - ");
  const n = cnorm(category), head = i >= 0 ? cnorm(category.slice(0, i)) : "";
  let out: Classified | undefined = !head ? LEGACY[n] : undefined;
  if (!out) {
    const tab = GROUP_TABS.find(([rx]) => rx.test(head || n))?.[1] ?? "other";
    const sub = tab === "other" ? n : i >= 0 ? cnorm(category.slice(i + 3)) : n;
    const m = SUBS[tab].find(([rx]) => rx.test(sub))!;
    out = { tab, key: m[1], label: m[2] };
  }
  cache.set(category, out);
  return out;
}

/** The friendly name of a sub-category key ("large-mid-cap" -> "Large & Mid Cap"); the key itself when unknown. */
export function keyLabel(key: string): string {
  for (const rows of Object.values(SUBS)) for (const [, k, label] of rows) if (k === key) return label;
  return Object.values(LEGACY).find((c) => c.key === key)?.label ?? key;
}

/** The six quick cards above the tabs. Clicking one shows just that sub-category. */
export type Card = { key: string; tab: TabKey; title: string; lines: [string, string]; icon: string; note?: string };
export const CARDS: Card[] = [
  { key: "elss", tab: "equity", title: "ELSS (Tax Savings)", lines: ["Lock-in for three years", "Tax savings of up to Rs. 46,800 under 80C"], icon: "percent",
    note: "Under the old tax regime: 30% tax plus 4% cess on the ₹1.5 lakh Section 80C limit is ₹46,800. The new tax regime has no 80C deduction." },
  { key: "large-cap", tab: "equity", title: "Large-Cap Funds", lines: ["Established companies", "Lower risk with consistent returns"], icon: "building" },
  { key: "flexi-cap", tab: "equity", title: "Flexi Cap Funds", lines: ["Moderate risk", "Long-term (> 5 years) investments"], icon: "layers" },
  { key: "small-cap", tab: "equity", title: "Small-Cap Funds", lines: ["High growth potential", "Higher volatility & risk"], icon: "sprout" },
  { key: "money-market", tab: "debt", title: "Money Market Funds", lines: ["Low risk", "Higher liquidity"], icon: "coins" },
  { key: "corporate-bond", tab: "debt", title: "Corporate Bonds", lines: ["Higher risk & return than FD", "Medium-term (1–5 years) investments"], icon: "wallet" },
];

/** "Large Cap & Mid Cap" (up to three names), "Large Cap, Mid Cap & 4 more"; the tab's own name when all or none are chosen. */
export function selectionTitle(tab: TabKey | "all", labels: string[], all: boolean): string {
  if (tab === "all") return "All";
  if (all || !labels.length) return tabLabel(tab);
  if (labels.length <= 3) return labels.join(" & ");
  return `${labels.slice(0, 2).join(", ")} & ${labels.length - 2} more ${tabLabel(tab).toLowerCase()}`;
}
