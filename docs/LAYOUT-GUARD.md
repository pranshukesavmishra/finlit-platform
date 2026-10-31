# Layout guard

`frontend/e2e/layout_guard.mjs` is a Playwright script that opens the main pages at many widths and fails when a page collapses,
goes blank, scrolls sideways, clips text or throws. It exists because the stock screener once collapsed to a ~40-160 px results
column (black screen) when the saved filter-panel width, the app sidebar and the window width met in the wrong combination.

## Run it

```
cd frontend
npx playwright install chromium        # once
npm run layout-guard                   # builds the demo site, serves it, runs every case; exit 1 on any failure
npm run layout-guard:api               # normal build with /api mocked: the server-side screener (ScreenerPro) and friends
node e2e/layout_guard.mjs http://127.0.0.1:5199 ./out   # against a server you already run
```

Env: `CHROME=/path/to/chrome`, `GUARD_FULL=1` (every width x theme for every storage state), `GUARD_ONLY=screener`
(page-name substring), `GUARD_SHOTS=1` (screenshot every case; failures are always saved as `FAIL-*.png`),
`GUARD_LEGACY=1` (write the pre-versioning bare storage values, to test an older build).

## What it checks

Pages: home, screener, score screener, advanced score screener, fund screener, query builder, stock, prism, compare, portfolio,
holdings, funds, fundamentals, plans, FAQ. Widths 1440 / 1055 / 768 / 390 / 360 in both themes, plus 865, 900, 945, 1000, 1093,
1229, 1366 (Windows display scaling: 1366 at 125% = 1093 CSS px) at device pixel ratio 1 / 1.25 / 1.5.

Per case it fails on: blank page (< 200 px / no text) or the error card showing; horizontal page scroll; a main container
(results card, table box, query results) narrower than 320 px at widths >= 768; text squeezed to one word per line; text sticking
out of its card; a screener without a results table; uncaught page errors or console errors.

Storage states (screener pages): sidebar folded, saved panel width 620 / 0 / absurd, **stale values from an older release**,
**corrupt JSON**, wrong types and a future version. Saved UI state is versioned (`{"v":2,"d":...}`, `src/lib/persist.ts`);
anything else is discarded and the default used.

## When it fails

Open the `FAIL-*.png` named in the output. Typical causes: a fixed-width panel in a flex/grid row without `min-width: 0`, a
grid track in px that does not leave the content a minimum, an item that moves to the wrong track when its sibling is `display:none`.
See the comment above `.scr` in `src/styles/tools.css` for the rules the screener layout follows.
