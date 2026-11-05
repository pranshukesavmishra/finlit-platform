import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import fs from "node:fs";
import { FeatureBucket } from "./FeatureBucket";
import { GROUPS, TOOL_COPY } from "../lib/featureBucket";
import { TOOL_ICONS, TOOL_IDS } from "../lib/toolIcons";
import { ToolIcon } from "./ToolIcon";

const app = fs.readFileSync(new URL("../App.tsx", import.meta.url), "utf8");
const routes = [...app.matchAll(/path="([^"]+)"/g)].map((m) => m[1]);
const exists = (p: string) => routes.some((r) => r === p.slice(1) || (r.endsWith("/*") && p.slice(1).startsWith(r.slice(0, -2))));
const html = renderToStaticMarkup(<MemoryRouter><FeatureBucket /></MemoryRouter>);

describe("tool registry", () => {
  it("has 22 tools, each with icon, tagline, tier and an existing route", () => {
    expect(TOOL_IDS).toHaveLength(22);
    for (const id of TOOL_IDS) {
      const m = TOOL_ICONS[id];
      expect(m.tagline.length).toBeGreaterThan(5);
      expect(["free", "silver", "gold"]).toContain(m.tier);
      expect(exists(m.route), `${id} -> ${m.route}`).toBe(true);
      expect(renderToStaticMarkup(<ToolIcon id={id} />)).toContain("<svg");
      expect(TOOL_COPY[id].features).toHaveLength(3);
    }
  });
});

describe("Tools & Research Hub", () => {
  it("renders 5 groups (h3) and 22 cards (h4) with a plan chip and a link each", () => {
    expect((html.match(/<h3/g) ?? []).length).toBe(GROUPS.length);
    expect((html.match(/<h4/g) ?? []).length).toBe(22);
    expect((html.match(/class="fb-chip/g) ?? []).length).toBe(22);
    for (const id of TOOL_IDS) expect(html).toContain(`href="${TOOL_ICONS[id].route}"`);
    expect(html).toContain("never investment advice");
    expect(html).toMatch(/Free<span class="sr-only"> plan/);
  });
  it("has filter pills for All and each group", () => {
    expect((html.match(/class="fb-pill"/g) ?? []).length).toBe(6);
  });
  it("uses no advice words", () => {
    const text = html.replace(/<[^>]+>/g, " ");
    expect(text).not.toMatch(/\b(best|buy|sell|multibagger|top pick|accumulate)\b/i);
  });
});
