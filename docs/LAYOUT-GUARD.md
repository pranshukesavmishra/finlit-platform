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
