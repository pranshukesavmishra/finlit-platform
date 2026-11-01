export type Theme = "dark" | "light";

export const THEME_STORAGE_KEY = "finlit-theme";

export function readStoredTheme(): Theme | null {
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY);
    return value === "dark" || value === "light" ? value : null;
  } catch { return null; }
}

export function getSystemTheme(): Theme {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function getInitialTheme(root: HTMLElement = document.documentElement): Theme {
  return readStoredTheme() || (root.dataset.theme === "dark" || root.dataset.theme === "light" ? root.dataset.theme : getSystemTheme());
}
