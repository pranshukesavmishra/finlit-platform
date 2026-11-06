// The fixed words of the My portfolio page. Every sentence about the user's list comes from the server's readings (never from here); this file holds only labels,
// method notes and the FAQ. One test (portfolio/wording.test.tsx) scans these and every sentence on the rendered page for advice wording.
import type { Mode } from "./types";

export const DISCLAIMER = "Information only, not investment advice.";
export const HEAD_DESC = "Add the shares you own and see how strong they are, and how spread out they are. Only names are needed; nothing is sent to a broker.";
export const ADD_NOTE = "Excel, CSV or PDF statements work. Only the share names are taken; quantities, prices and dates are ignored.";
export const MODE_LABEL: Record<Mode, string> = { eq: "Equal amounts", mc: "Sized by company value" };
export const MODE_SHORT: Record<Mode, string> = { eq: "Equal amounts", mc: "By company value" };
export const MODE_NOTE: Record<Mode, string> = { eq: "If equal amounts were held", mc: "If amounts were sized by company value" };
export const READINGS_FOOT = "Written from your list's figures by fixed rules. They describe the list and are not advice. Change \"Count as\" to see them for amounts sized by company value.";
export const NAV = [["where", "Where your list sits"], ["together", "What moves together"], ["risk", "Share of risk"], ["style", "Style"], ["shares", "Your shares"]] as const;
export const SECTION_TAG: Record<string, { label: string; to: string }> = {
  where: { label: "Where it sits", to: "where" }, together: { label: "Moves together", to: "together" }, risk: { label: "Risk", to: "risk" },
  market: { label: "NIFTY 50", to: "risk" }, data: { label: "Data", to: "shares" },
};
export const SCALE_NOTE = "How spread the list is, not how safe it is";
export const SCORE_PARTS = { comove: "Co-movement · 60% of the score", sector: "Sector spread · 40% of the score" };
export const FULL_AT = { stocks: "15 or more scores in full.", sectors: "8 or more scores in full." };
export const SIZES_NOTE = "Sectors are NSE's. Sizes are AMFI's: large cap = the 100 biggest companies, mid cap = the next 150, small cap = the rest. The same sector and size are used everywhere on this page.";
export const GROUP_NOTE = "A group is shares whose average correlation with each other is 0.5 or more. Letters match the dark bars beside the grid.";
export const GROUP_NOTE_LONG = "Found from each pair of shares, not from sector labels. A group is shares whose average correlation with each other is 0.5 or more; letters match the dark bars beside the grid.";
export const NIFTY_NOTE = "Beta 1.00 means the list moved in line with the index. Bad weeks are the NIFTY 50's 10 worst weeks in the period shown.";
export const TILT_FOOT_EXTRA = "Valuation: higher means cheaper. Risk: higher means lower risk.";
export const TABLE_FOOT = "Green from 70, orange 50 to 69, red under 50, for the score and each part. \"Moves with rest\" is a share's average correlation with the other shares in the list. " + DISCLAIMER;
export const LEGEND = ["0, unrelated", "0.05–0.2", "0.2–0.35", "0.35–0.5", "0.5–0.65", "0.65+, move almost as one"];
