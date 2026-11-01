import { beforeEach, describe, expect, it, vi } from "vitest";
import { getInitialTheme, getSystemTheme, readStoredTheme } from "./theme";

describe("theme foundation", () => {
  beforeEach(() => {
    let value: string | null = null;
    vi.stubGlobal("localStorage", {
      getItem: () => value,
      setItem: (_key: string, next: string) => { value = next; },
      clear: () => { value = null; },
    });
  });

  it("uses a valid saved preference before system or pre-paint state", () => {
    localStorage.setItem("finlit-theme", "dark");
    const root = { dataset: { theme: "light" } } as unknown as HTMLElement;
    expect(getInitialTheme(root)).toBe("dark");
    expect(readStoredTheme()).toBe("dark");
  });

  it("falls back to the pre-paint theme, then the system theme", () => {
    const root = { dataset: { theme: "light" } } as unknown as HTMLElement;
    expect(getInitialTheme(root)).toBe("light");
    delete root.dataset.theme;
    expect(["light", "dark"]).toContain(getSystemTheme());
  });

  it("ignores invalid stored values", () => {
    localStorage.setItem("finlit-theme", "sepia");
    expect(readStoredTheme()).toBeNull();
  });
});
