// Company size by market value, in rupees crore. The edges are the site's own buckets (not an official classification:
// SEBI ranks the top 100 / next 150 / the rest by rank, these are plain money bands so a portfolio can be read at a glance).
export type CapBucket = { id: "mega" | "large" | "mid" | "small" | "micro" | "nano"; label: string; range: string; min: number };
export const CAP_BUCKETS: CapBucket[] = [
  { id: "mega", label: "Mega-cap", range: "Above ₹2,00,000 Cr", min: 200000 },
  { id: "large", label: "Large-cap", range: "₹50,000–2,00,000 Cr", min: 50000 },
  { id: "mid", label: "Mid-cap", range: "₹10,000–50,000 Cr", min: 10000 },
  { id: "small", label: "Small-cap", range: "₹2,000–10,000 Cr", min: 2000 },
  { id: "micro", label: "Micro-cap", range: "₹500–2,000 Cr", min: 500 },
  { id: "nano", label: "Nano-cap", range: "Below ₹500 Cr", min: 0 },
];

/** The bucket a market value (₹ crore) falls in; null when the value is not known. The ranges read "above 2,00,000", "50,000 to 2,00,000", ...:
 *  a value exactly on an edge belongs to the bucket whose range ends there (2,00,000 is Large-cap, 500 is Nano-cap, 50,000 is Mid-cap). */
export function capBucket(crore: number | null | undefined): CapBucket | null {
  if (crore == null || !Number.isFinite(crore) || crore < 0) return null;
  if (crore > 200000) return CAP_BUCKETS[0];
  if (crore > 50000) return CAP_BUCKETS[1];
  if (crore > 10000) return CAP_BUCKETS[2];
  if (crore > 2000) return CAP_BUCKETS[3];
  if (crore > 500) return CAP_BUCKETS[4];
  return CAP_BUCKETS[5];
}
