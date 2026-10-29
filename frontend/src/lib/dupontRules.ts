/** Rule configuration for the "Decoding ROE" block. Product can tune every threshold, condition and sentence here without touching the component or the maths.
 *  Nothing in this file gives advice: every sentence describes what the company's own numbers show.
 *
 *  A rule fires when ALL of its `when` clauses are true. A clause compares one named measure (see `Measure`) with a number, or with the rule's own `threshold`.
 *  A clause whose measure is unavailable (for example a margin spread that cannot be worked out) is false, so the rule stays silent instead of guessing. */

export type Measure =
  | "roeChange"          // ROE last comparable year minus first, in percentage points
  | "emShare" | "marginShare" | "turnoverShare"   // share of the ROE move (log method), in per cent; positive = moved the same way as ROE
  | "emLatest" | "emDelta"                        // equity multiplier in the latest year, and its change from the year before
  | "marginCv" | "marginMean" | "marginStd"       // net margin spread over the last years: coefficient of variation = std / mean
  | "turnoverChange" | "marginChange"             // relative change first to last comparable year, per cent
  | "endpointOneOffPct"                           // largest one-off share of pre-tax profit among the first and last comparable year, per cent
  | "roeFirst" | "roeLast" | "emFirst" | "emLast" | "marginFirst" | "marginLast" | "turnoverFirst" | "turnoverLast";
export type Clause = { measure: Measure; op: ">" | "<" | ">=" | "<="; value: number | "threshold" };
export type InsightRule = {
  id: string;
  /** Higher shows first. */
  importance: number;
  /** The number the sentence quotes (per cent, or times for the multiplier); referenced as {threshold} and by clauses with value "threshold". */
  threshold: number;
  when: Clause[];
  /** The sentence. Tokens in braces are replaced by the numbers; no other text is generated. */
  template: string;
  /** The numbers behind the sentence, shown under it. Tokens as above. */
  evidence: string[];
  /** Equity multipliers of banks and lenders are structurally high, so rules about a high multiplier skip them. */
  notForLenders?: boolean;
};

/** How each token is printed. */
export const MEASURE_FORMAT: Record<Measure | "threshold", "pct0" | "pct1" | "x2" | "pp1" | "ratio2"> = {
  threshold: "pct0", roeChange: "pp1", emShare: "pct0", marginShare: "pct0", turnoverShare: "pct0", emLatest: "x2", emDelta: "x2", marginCv: "ratio2", marginMean: "pct1", marginStd: "pct1",
  turnoverChange: "pct1", marginChange: "pct1", endpointOneOffPct: "pct0", roeFirst: "pct1", roeLast: "pct1", emFirst: "x2", emLast: "x2", marginFirst: "pct1", marginLast: "pct1", turnoverFirst: "x2", turnoverLast: "x2",
};

export const INSIGHT_RULES: InsightRule[] = [
  { id: "one-off-endpoint", importance: 90, threshold: 50, when: [{ measure: "endpointOneOffPct", op: ">", value: "threshold" }],
    template: "A year at one end of this comparison has one-off items above {threshold}% of its pre-tax profit, so part of the ROE change reflects those one-offs.",
    evidence: ["Largest one-off share at either end: {endpointOneOffPct}% of pre-tax profit"] },
  { id: "leverage-fell", importance: 80, threshold: 40, when: [{ measure: "roeChange", op: "<", value: 0 }, { measure: "emShare", op: ">", value: "threshold" }],
    template: "Over {threshold}% of the ROE decline is due to lower leverage, not worse operations.",
    evidence: ["Equity multiplier {emFirst}× to {emLast}×: {emShare}% of the ROE move", "ROE {roeFirst}% to {roeLast}%"] },
  { id: "leverage-rose", importance: 80, threshold: 40, when: [{ measure: "roeChange", op: ">", value: 0 }, { measure: "emShare", op: ">", value: "threshold" }],
    template: "Over {threshold}% of the ROE rise comes from a higher equity multiplier rather than from margin or turnover.",
    evidence: ["Equity multiplier {emFirst}× to {emLast}×: {emShare}% of the ROE move", "ROE {roeFirst}% to {roeLast}%"] },
  { id: "leverage-driven", importance: 75, threshold: 3, when: [{ measure: "emLatest", op: ">", value: "threshold" }, { measure: "emDelta", op: ">", value: 0 }], notForLenders: true,
    template: "ROE is increasingly leverage-driven. Check debt servicing.",
    evidence: ["Equity multiplier now {emLatest}×, {emDelta}× on the year before (rule applies above {threshold}×)"] },
  { id: "earnings-volatile", importance: 70, threshold: 0.5, when: [{ measure: "marginCv", op: ">", value: "threshold" }],
    template: "Earnings are volatile, so ROE is unreliable as a trend.",
    evidence: ["Net margin averaged {marginMean}% with a standard deviation of {marginStd}%: coefficient of variation {marginCv} (rule applies above {threshold})"] },
  { id: "margin-driven", importance: 60, threshold: 40, when: [{ measure: "marginShare", op: ">", value: "threshold" }, { measure: "turnoverShare", op: "<=", value: "threshold" }],
    template: "Profitability, not efficiency, drove the change.",
    evidence: ["Net margin {marginFirst}% to {marginLast}%: {marginShare}% of the ROE move", "Asset turnover {turnoverFirst}× to {turnoverLast}×: {turnoverShare}% of the ROE move"] },
  { id: "turnover-driven", importance: 55, threshold: 40, when: [{ measure: "turnoverShare", op: ">", value: "threshold" }, { measure: "marginShare", op: "<=", value: "threshold" }],
    template: "Efficiency, not profitability, drove the change.",
    evidence: ["Asset turnover {turnoverFirst}× to {turnoverLast}×: {turnoverShare}% of the ROE move", "Net margin {marginFirst}% to {marginLast}%: {marginShare}% of the ROE move"] },
  { id: "growth-pressure", importance: 50, threshold: 3, when: [{ measure: "turnoverChange", op: ">", value: "threshold" }, { measure: "marginChange", op: "<", value: -3 }],
    template: "Growth is coming with price or margin pressure.",
    evidence: ["Asset turnover {turnoverChange}% and net margin {marginChange}% from the first to the last year (a move of more than {threshold}% counts)"] },
  { id: "margin-up-turnover-down", importance: 45, threshold: 3, when: [{ measure: "marginChange", op: ">", value: "threshold" }, { measure: "turnoverChange", op: "<", value: -3 }],
    template: "Each rupee of sales earns more, but the assets produce fewer rupees of sales.",
    evidence: ["Net margin {marginChange}% and asset turnover {turnoverChange}% from the first to the last year (a move of more than {threshold}% counts)"] },
  { id: "leverage-easing", importance: 40, threshold: 3, when: [{ measure: "emLatest", op: ">", value: "threshold" }, { measure: "emDelta", op: "<", value: 0 }], notForLenders: true,
    template: "The equity multiplier is above {threshold}× but fell on the year, so ROE leans less on leverage than a year earlier.",
    evidence: ["Equity multiplier now {emLatest}×, {emDelta}× on the year before"] },
  { id: "earnings-steady", importance: 30, threshold: 0.15, when: [{ measure: "marginCv", op: "<", value: "threshold" }],
    template: "Net margin stayed in a narrow band, so the ROE trend is not a product of earnings swings.",
    evidence: ["Net margin averaged {marginMean}% with a standard deviation of {marginStd}%: coefficient of variation {marginCv} (rule applies below {threshold})"] },
];

/** Everything else product may want to tune. */
export const DUPONT_LIMITS = {
  /** One-off items above this share of pre-tax profit: the year is "low-quality earnings" and left out of averages. */
  lowQualityShare: 0.5,
  /** One-off items above this multiple of pre-tax profit are shown as an implausible ratio (tiny denominator or data issue). */
  implausibleOneOffShare: 5,
  /** Net margin above this per cent is shown as likely tiny revenue or a data issue. */
  implausibleMarginPct: 70,
  /** Year-on-year relative change in the equity multiplier or net margin above this is a step change. */
  stepChange: 0.5,
  /** Equity below this share of total assets (equity multiplier above 50) makes ROE not meaningful. */
  nearZeroEquityShare: 0.02,
  /** Tax rate used for one-offs only when tax and pre-tax profit do not give one. Stated in the note whenever it is used. */
  fallbackTaxRate: 0.25,
  taxRateMax: 0.4,
  /** Years used for the margin coefficient of variation, and the fewest years that make it worth computing. */
  cvYears: 5,
  cvMinYears: 3,
  /** At most this many insight cards are shown. */
  maxCards: 4,
  /** Windows for the average ROE tiles. */
  averageWindows: [3, 5],
  /** Share of a ROE change from one factor above which the badge names it, in per cent. */
  flatChangePct: 3,
  /** Prompt for a step change in the equity multiplier or net margin. */
  stepPrompt: "Possible equity raise, merger or restructuring: check the cash flow and equity statements.",
} as const;

/** The ROE quality score: 100 points from three parts, each worked out from the company's own statements over the last few years.
 *  It is a description of how clean and steady the ROE is, not a rating of the company. */
export const QUALITY_SCORE = {
  parts: [
    { key: "oneOffs", label: "Clean earnings", max: 40, how: "Full points when one-off items are 0% of pre-tax profit, none when they average 50% or more (the low-quality-earnings line)." },
    { key: "stability", label: "Margin stability", max: 35, how: "Full points when the net margin's coefficient of variation is 0, none at 0.5 or more (the volatile-earnings line)." },
    { key: "leverage", label: "Leverage level", max: 25, how: "Full points when the equity multiplier is 2× or lower, none at 6× or higher, in a straight line between. Not scored for banks and lenders, whose balance sheets are built on leverage." },
  ],
  leverageFull: 2, leverageNone: 6, oneOffNone: 0.5, cvNone: 0.5,
} as const;

/** The names of the three drivers in the "ROE driven by" badge. */
export const DRIVER_NAME = { netMargin: "Operations (margin)", turnover: "Efficiency (turnover)", multiplier: "Leverage (multiplier)" } as const;
