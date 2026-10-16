// Indian number formatting used across the site (₹, lakh/crore grouping, true minus sign).
export const MINUS = "−";

export const nf = (n: number, d = 2) =>
  Math.abs(n).toLocaleString("en-IN", { minimumFractionDigits: d, maximumFractionDigits: d });

export const num = (n: number | null | undefined, d = 2) => (n == null ? "—" : (n < 0 ? MINUS : "") + nf(n, d));

export const signed = (n: number | null | undefined, d = 2, unit = "%") =>
  n == null ? "—" : (n > 0 ? "▲ +" : n < 0 ? "▼ " + MINUS : "") + nf(n, d) + unit;

/** Crore amount, switching to lakh crore (L) above ₹1,00,000 Cr. */
export const cr = (n: number | null | undefined) =>
  n == null ? "—" : Math.abs(n) >= 100000 ? (n < 0 ? MINUS : "") + nf(n / 100000, 2) + " L" : num(n, 0);

export const pct = (n: number | null | undefined, d = 2) => (n == null ? "—" : num(n, d) + "%");

export function fmtUnit(v: number | null | undefined, unit?: string | null): string {
  if (v == null) return "—";
  if (unit === "%") return num(v) + "%";
  if (unit === "x") return num(v) + "×";
  if (unit === "Cr") return "₹" + cr(v) + " Cr";
  if (unit === "days") return num(v, 0) + " days";
  return num(v);
}

export const dateIN = (iso: string, opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short", year: "numeric" }) => {
  const d = new Date(iso.length === 10 ? iso + "T00:00:00" : iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-IN", opts);
};

export const initials = (text: string) =>
  text.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase() || text.slice(0, 2).toUpperCase();

export const capSize = (crore: number | null | undefined) =>
  crore == null ? null : crore >= 100000 ? "Large cap" : crore >= 30000 ? "Mid cap" : crore >= 5000 ? "Small cap" : "Micro cap";
