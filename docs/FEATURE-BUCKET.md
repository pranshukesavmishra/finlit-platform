# Tools & Research Hub (Home page feature bucket)

Section `#tools`, component `components/FeatureBucket.tsx`, placed on the Home page after the "Method" block and before the plans band. Nothing else on the Home page was changed.

- Copy: team's approved text (`docs/feature-bucket-source.html`) in `lib/featureBucket.ts`; old playful names are not shown. Where the founder's icon pictures give newer names and taglines, those are used (`lib/toolIcons.ts`, the single registry: id, name, tagline, tier, route).
- Wording changes: the site forbids the word "Fundamental" in visible text (`noFundamentalWord.test.ts`), so "fundamentals" became "financials" in three lines.
- Design: five group bands (h3) with a small colour accent that has a darker light-theme value; cards (h4) in a grid of 4 / 3 / 2 / 1 columns (no horizontal scroll at 390). Colours come from design-system tokens. Plan chip has text ("Free", "Silver", "Gold") plus a shape, not colour alone. Cards for higher plans stay clickable.
- Filter pills (All + 5 groups) only hide groups visually; all 22 cards stay in the DOM.
- Icons: `components/ToolIcon.tsx` (sizes sm 28 / md 44 / lg 64, tier ring: gold with glow, blue Free, silver Silver; ivory disc in light theme).
- Pictures: `frontend/public/feature-bucket/<tool>-light.webp` and `-dark.webp` (640x400, under 56 KB), real pages from the demo build. Two `<img>` per card, swapped by `data-theme`; only the visible one loads (lazy).
- Regenerate: `cd frontend && VITE_DEMO=1 npx vite build --minify false --outDir /tmp/fb-demo && npx vite preview --outDir /tmp/fb-demo --port 4423 --host 127.0.0.1 &` then `node ../scripts/make-feature-shots.mjs http://127.0.0.1:4423 [slug...]` (needs Playwright; set `PLAYWRIGHT_PATH` if not at `/opt/node-tools/node_modules/playwright`).
