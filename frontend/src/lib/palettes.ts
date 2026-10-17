// Colour palettes a member can choose. The default is the brand palette (ivory, black and muted gold); the others
// recolour the accent and, for some, the page surfaces. Gains and losses keep their green/red meaning in every palette.
export type PaletteId = "gold" | "champagne" | "bronze" | "graphite" | "midnight" | "emerald";
type Mode = "dark" | "light";
type Accent = [main: string, light: string, deep: string];
type Surface = { bg: string; s1: string; s2: string; s3: string; border: string; strong: string; text: string; muted: string; faint: string; header: string };
type Spec = { label: string; blurb: string; swatch: [string, string, string]; accent: Record<Mode, Accent>; surface?: Partial<Record<Mode, Surface>>; bands?: { a: string; b: string; rep: [string, string]; foot: [string, string] } };

export const PALETTES: Record<PaletteId, Spec> = {
  gold: { label: "Ivory & Gold", blurb: "The FinLit signature: ivory, black and muted gold.", swatch: ["#F6F1E7", "#16140E", "#B8933F"],
    accent: { dark: ["#D4B26A", "#E8D29B", "#A8843A"], light: ["#8A6A25", "#C9A24E", "#8A6A25"] } },
  champagne: { label: "Champagne", blurb: "Softer, paler gold on warm ivory.", swatch: ["#FAF6EC", "#2A2519", "#CDB985"],
    accent: { dark: ["#E3D2A8", "#F1E6C8", "#B9A573"], light: ["#7D6B3E", "#B3A06D", "#7D6B3E"] } },
  bronze: { label: "Copper", blurb: "Warm copper accents, the Bronze plan's own colour.", swatch: ["#F3EAE0", "#2B1D14", "#B8703F"],
    accent: { dark: ["#D08A5B", "#E6B089", "#A5663A"], light: ["#9A5A2E", "#C98A5A", "#9A5A2E"] } },
  graphite: { label: "Graphite", blurb: "Calm, neutral greys with a silver accent.", swatch: ["#F3F4F6", "#14161A", "#8B93A1"],
    accent: { dark: ["#C5C9D0", "#E3E6EA", "#8C919A"], light: ["#4B5360", "#7B8492", "#4B5360"] },
    surface: {
      dark: { bg: "#0E0F11", s1: "#16181B", s2: "#1D2024", s3: "#272B30", border: "rgba(220,225,235,.12)", strong: "rgba(220,225,235,.26)", text: "#F2F3F5", muted: "#B5B9C0", faint: "#868B93", header: "rgba(14,15,17,.97)" },
      light: { bg: "#F3F4F6", s1: "#FFFFFF", s2: "#F6F7F9", s3: "#E7E9ED", border: "#DDE0E5", strong: "#C3C8D0", text: "#14161A", muted: "#444A54", faint: "#666C77", header: "rgba(243,244,246,.97)" },
    }, bands: { a: "#1C1E22", b: "#0E0F11", rep: ["#23262B", "#191B1F"], foot: ["#1C1E22", "#121316"] } },
  midnight: { label: "Midnight", blurb: "Deep navy with the gold accent.", swatch: ["#EEF1F8", "#101528", "#C9A24E"],
    accent: { dark: ["#D4B26A", "#E8D29B", "#A8843A"], light: ["#8A6A25", "#C9A24E", "#8A6A25"] },
    surface: {
      dark: { bg: "#0A1020", s1: "#101830", s2: "#16203D", s3: "#212C4F", border: "rgba(190,205,240,.13)", strong: "rgba(190,205,240,.28)", text: "#F1F4FB", muted: "#B3BCD3", faint: "#7F89A6", header: "rgba(10,16,32,.97)" },
      light: { bg: "#EEF1F8", s1: "#FFFFFF", s2: "#F4F6FB", s3: "#E3E8F3", border: "#D5DCEC", strong: "#BAC4DD", text: "#101528", muted: "#3F4963", faint: "#5F6985", header: "rgba(238,241,248,.97)" },
    }, bands: { a: "#16203D", b: "#0A1020", rep: ["#1B2748", "#111A33"], foot: ["#16203D", "#0B1226"] } },
  emerald: { label: "Emerald", blurb: "Deep green with a soft sage accent.", swatch: ["#F0F4EF", "#121A14", "#4C8B69"],
    accent: { dark: ["#8FC9A4", "#BFE3CC", "#5E9A76"], light: ["#2F6B4C", "#5E9A76", "#2F6B4C"] },
    surface: {
      dark: { bg: "#0A130F", s1: "#101C16", s2: "#16251D", s3: "#213329", border: "rgba(190,230,205,.13)", strong: "rgba(190,230,205,.28)", text: "#F0F6F2", muted: "#B2C4B8", faint: "#7E9488", header: "rgba(10,19,15,.97)" },
      light: { bg: "#F0F4EF", s1: "#FFFFFF", s2: "#F5F8F3", s3: "#E1EADF", border: "#D3DFD0", strong: "#B6C8B3", text: "#121A14", muted: "#3F4C43", faint: "#62706A", header: "rgba(240,244,239,.97)" },
    }, bands: { a: "#16251D", b: "#0A130F", rep: ["#1B2E24", "#111E17"], foot: ["#16251D", "#0B1611"] } },
};
export const PALETTE_IDS = Object.keys(PALETTES) as PaletteId[];
export const isPalette = (v: unknown): v is PaletteId => typeof v === "string" && v in PALETTES;

const soft = (hex: string, a: number) => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`;
};

/** Every CSS variable a palette sets for the given theme. Empty for the default palette (the stylesheet already is it). */
export function paletteVars(id: PaletteId, theme: Mode): Record<string, string> {
  if (id === "gold") return {};
  const p = PALETTES[id];
  const [a, b, c] = p.accent[theme];
  const [da, db, dc] = p.accent.dark;
  const [la, lb, lc] = p.accent.light;
  const v: Record<string, string> = {
    "--gold": a, "--gold-2": b, "--gold-deep": c, "--gold-soft": soft(a, theme === "dark" ? 0.14 : 0.13),
    "--t-gold": a, // chart colours are a separate fixed categorical set (--k1..--k8) and do not follow the palette
    // the always-dark bands and the always-light hero read these
    "--dk-gold": da, "--dk-gold-2": db, "--dk-gold-deep": dc, "--dk-gold-soft": soft(da, 0.14),
    "--lt-gold": la, "--lt-gold-2": lb, "--lt-gold-deep": lc, "--lt-gold-soft": soft(la, 0.13),
  };
  const s = p.surface?.[theme];
  if (s) Object.assign(v, { "--bg": s.bg, "--s1": s.s1, "--s2": s.s2, "--s3": s.s3, "--border": s.border, "--border-strong": s.strong, "--text": s.text, "--muted": s.muted, "--faint": s.faint, "--header": s.header });
  if (p.bands) Object.assign(v, { "--band-a": p.bands.a, "--band-b": p.bands.b, "--rep-a": p.bands.rep[0], "--rep-b": p.bands.rep[1], "--foot-a": p.bands.foot[0], "--foot-b": p.bands.foot[1] });
  return v;
}

const ALL_VARS = new Set<string>();
for (const id of PALETTE_IDS) for (const t of ["dark", "light"] as const) for (const k of Object.keys(paletteVars(id, t))) ALL_VARS.add(k);

/** Paint a palette onto the page. Inline custom properties on <html> beat the stylesheet, so this needs no extra CSS. */
export function applyPalette(id: PaletteId, theme: Mode, root: HTMLElement = document.documentElement) {
  for (const k of ALL_VARS) root.style.removeProperty(k);
  for (const [k, val] of Object.entries(paletteVars(id, theme))) root.style.setProperty(k, val);
  root.dataset.palette = id;
  try { localStorage.setItem("finlit-palette-vars", JSON.stringify({ id, theme, vars: paletteVars(id, theme) })); } catch { /* private mode */ } // read by theme-init.js before first paint
}
