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

---

# Layout and overlay guards

## Overlay guard (dialogs, menus, drawers, popovers, tips, toasts, trays)

Every floating surface must be **opaque**, sit **above** what it covers and stay **on screen**. Page text must never show through a dialog or tip.

### The rules (one place: `frontend/src/styles/overlay.css`, imported last in `main.tsx`)

- Surfaces paint `--ov-surface` (an opaque colour). Glass/blur is allowed only on top of that colour.
- `--ov-*` tokens are resolved on `:root`. A hero, `.band`, `.report` or `.plan` remaps `--s1/--s2/--s3` to translucent white for its own children; an overlay rendered inside one used to inherit that. This was the see-through "Create new alert" dialog: `.alx-modal { background: var(--s2) }` inside `.band.hero` got `--s2: rgba(255,255,255,.075)` (`finlit.css` `.band`).
- Z-index scale: `--z-header 40 < --z-tray 50 < --z-dropdown 200 < --z-tip 260 < --z-backdrop 300 < --z-modal 310 < --z-drawer 320 < --z-popover 400 < --z-toast 500`. Do not use bare numbers for overlays.
- Dialogs are portalled to `<body>` (`createPortal`). Tips use `lib/floating.ts` (`placeFloating`): below, above, right or left of the anchor, kept inside the viewport, preferring a side that does not cover another button or link.
- `@supports not (backdrop-filter)` and `prefers-reduced-transparency: reduce` fall back to solid colours (machines without GPU acceleration, remote desktops, Windows "transparency effects" off).
- New overlay class: add it to the surface list in `overlay.css`. The unit test fails if a floating rule with a see-through background is not covered.

### Running it

```
cd frontend
VITE_DEMO=1 npm run dev -- --port 5301          # demo mode: no backend, signed in as Gold
npm run overlay-guard -- http://127.0.0.1:5301  # dark + light at 1280, 947, 390
FULL=1 npm run overlay-guard -- http://127.0.0.1:5301   # also 1229/1093/1055/945 px, GPU off, Windows scaling 125% and 150%
```

Environment: `CHROME=/path/to/chrome`, `SHOTS=/dir` (screenshot of every overlay), `ONLY=alert,leadtip`, `THEMES=dark`, `SIZES=1280x800`, `NOGPU=1`.

Per overlay it checks: background alpha is 1 (or an opaque layer under it), the topmost element on a 5x5 grid of the surface belongs to the surface (nothing painted above or visible through it), inside the viewport, a full-viewport backdrop with alpha >= .5 under the surface and above the header (modals, drawers), Esc closes, page scroll is locked and focus is inside (modals), and a tip does not sit on top of another control. Exit code 1 on any failure.

Unit test (no browser): `npx vitest run src/styles/overlay.test.ts`.
