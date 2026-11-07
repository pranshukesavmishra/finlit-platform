# FinLit on phones (mobile rules)

The phone layer is `frontend/src/styles/mobile.css`, loaded after every page stylesheet (just before `overlay.css`, which stays last).
Every rule sits inside a phone (`max-width: 760px`), narrow (`380px`) or touch (`pointer: coarse`) query, so desktop never changes.

## Breakpoints for new code
| Token | Width | Means |
|---|---|---|
| `--bp-phone` | 480px | small phones (360-480) |
| `--bp-mobile` | 760px | every phone, landscape too (bottom tab bar shows) |
| `--bp-tablet` | 1024px | tablets; desktop starts above |

Old queries (1180 ... 420) stay; replace one only when you are already fixing that rule.

## What each shared piece does on a phone
- **Header:** logo, assistant, theme, alerts, account. Search and menu live in the bottom tab bar; a signed-in header drops the duplicate "Dashboard" button.
- **Bottom tab bar:** Dashboard/Home, Research, Search, Screener, Menu. It hides while a filter sheet is open.
- **Menus and drawers** (`lib/useSheet.ts`): the page behind is locked, Escape, the backdrop and the phone's Back button close them, focus goes in and comes back. The site menu and the product drawer stop above the bottom bar.
- **Tables:** scroll sideways inside their own box (never the page); the first column stays frozen; a soft fade at the edge shows more columns (`lib/scrollHints.ts` sets `data-edge`). Screener name columns take at most about 40% of the screen.
- **Screener filters** (stock, score and advanced screeners): a bottom sheet (max 88% of the screen) with a drag handle and a sticky "Show N companies" footer.
- **Dialogs:** the alert dialog rises from the bottom; close buttons are 44px.
- **Stock page header:** the letter badge sits beside the name; the details card uses the full width.
- **Charts:** a vertical swipe scrolls the page (`touch-action: pan-y`).
- **Forms:** inputs are 16px on touch screens (no iOS zoom); number boxes open the number pad (`inputmode` added automatically).
- **Text:** nothing under 12px, except bottom-bar labels on phones under 380px (11px).
- **Back to top:** a small button after two screens of scrolling, hidden at the page end and while a sheet is open.

## Checks
- `node e2e/mobile.mjs <url>`: no sideways scroll on every page at 360, 390 and 430px.
- `node e2e/mobile_audit.mjs <url> [outDir]`: 6 devices x light/dark. Reports sideways scroll, cut-off text, controls under bars, tap targets, small text, inputs that zoom, nested scroll boxes. `AUDIT_DEVICES=390 AUDIT_ONLY=screener AUDIT_SHOTS=1` narrow it.
