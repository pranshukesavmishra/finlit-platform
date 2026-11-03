export type Theme = "dark" | "light";

export const THEME_STORAGE_KEY = "finlit-theme";

export function readStoredTheme(): Theme | null {
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY);
    return value === "dark" || value === "light" ? value : null;
  } catch { return null; }
}

/** A first visit opens in the light theme whatever the device prefers; the visitor's own choice (the sun / moon button) is kept after that. */
export const DEFAULT_THEME: Theme = "light";

export function getInitialTheme(root: HTMLElement = document.documentElement): Theme {
  return readStoredTheme() || (root.dataset.theme === "dark" || root.dataset.theme === "light" ? root.dataset.theme : DEFAULT_THEME);
}
