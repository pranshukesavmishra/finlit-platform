import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DASH_KEY, DashToggle, readDashOpen, writeDashOpen } from "./DashToggle";
import { PartTile, zoneBg } from "../components/prism/shared/PartTile";
import { PrismGlyph } from "../components/prism/shared/PrismGlyph";

// "Show full breakdown": collapsed by default, a real button with aria-expanded and aria-controls, and a choice that is remembered in
// this browser only, through storage that may be missing or may throw.
const store = (impl: Partial<Storage>) => vi.stubGlobal("localStorage", impl);
afterEach(() => { vi.unstubAllGlobals(); });

describe("Show full breakdown toggle", () => {
  it("is a button that says what it does and is collapsed by default", () => {
    const closed = renderToStaticMarkup(<DashToggle open={false} onToggle={() => undefined} controls="dk-full" />);
    expect(closed).toContain("<button");
    expect(closed).toContain('type="button"');
    expect(closed).toContain('aria-expanded="false"');
    expect(closed).toContain('aria-controls="dk-full"');
    expect(closed).toContain("Show full breakdown");
    const open = renderToStaticMarkup(<DashToggle open onToggle={() => undefined} controls="dk-full" />);
    expect(open).toContain('aria-expanded="true"');
    expect(open).toContain("Hide full breakdown");
  });

  it("starts collapsed when nothing is stored, and remembers the choice", () => {
    const mem = new Map<string, string>();
    store({ getItem: (k) => mem.get(k) ?? null, setItem: (k, v) => void mem.set(k, v) });
    expect(readDashOpen()).toBe(false);
    writeDashOpen(true);
    expect(mem.get(DASH_KEY)).toBe("1");
    expect(readDashOpen()).toBe(true);
    writeDashOpen(false);
    expect(readDashOpen()).toBe(false);
  });

  it("still works when storage throws (private window, blocked site data) or does not exist", () => {
    store({ getItem: () => { throw new Error("denied"); }, setItem: () => { throw new Error("denied"); } });
    expect(readDashOpen()).toBe(false);
    expect(() => writeDashOpen(true)).not.toThrow();
    vi.unstubAllGlobals();
    vi.stubGlobal("localStorage", undefined);
    expect(readDashOpen()).toBe(false);
    expect(() => writeDashOpen(true)).not.toThrow();
  });
});

describe("shared dashboard pieces", () => {
  it("a tile names its part, value, status word and weight, and says no data when it has none", () => {
    const html = renderToStaticMarkup(<PartTile name="Valuation" value={16.4} word="Poor" tone="weak" color="--p-quality" weight={30} />);
    expect(html).toContain('aria-label="Valuation: 16 out of 100, poor. 30% of the score"');
    expect(html).toContain("Poor");
    expect(html).toContain(">30%<");
    for (const t of [35, 50, 65, 80]) expect(html).toContain(`left:${t}%`);   // tick marks at the label thresholds
    expect(renderToStaticMarkup(<PartTile name="Risk" value={null} word="No data" tone="na" color="--p-balance" />)).toContain('aria-label="Risk: no data"');
  });

  it("a pressable tile is a button with aria-expanded", () => {
    const html = renderToStaticMarkup(<PartTile name="Quality" value={56} word="Mixed" tone="mixed" color="--p-quality" onPress={() => undefined} pressed />);
    expect(html).toContain("<button");
    expect(html).toContain('aria-expanded="true"');
  });

  it("the bar tints one zone per label band and cuts them at the thresholds", () => {
    expect(zoneBg([35, 50, 65, 80])).toMatch(/35%.*50%.*65%.*80%/);
    expect(zoneBg([45, 62, 78])).toMatch(/45%.*62%.*78%/);
  });

  it("the glyph draws one filled arc per part with a score, sized by weight, and says Not rated without a score", () => {
    const parts = [{ key: "a", name: "A", weight: 40, value: 70, color: "--p-growth" }, { key: "b", name: "B", weight: 60, value: null, color: "--p-quality" }];
    const html = renderToStaticMarkup(<PrismGlyph parts={parts} score={58.44} ariaLabel="Rating" />);
    expect(html).toContain("58.4");
    expect(html).toContain('stroke-dasharray="70 100"');
    expect(html.match(/class="dk-gl-track"/g)).toHaveLength(2);
    expect(html.match(/class="dk-gl-fill"/g)).toHaveLength(1);   // the part without data has a track only
    expect(html).toContain('aria-label="Rating"');
    const none = renderToStaticMarkup(<PrismGlyph parts={parts} score={null} />);
    expect(none).toContain("Not rated");
    expect(none).not.toContain("OUT OF 100");
    expect(none).toContain('aria-hidden="true"');
  });
});
