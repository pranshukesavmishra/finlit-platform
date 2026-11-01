# Workspace UI pass — 1 November 2026

## Direction and scope

Extend the approved navy, ivory, gold, silver and green visual system into the signed-in workspace. Give each page a clear title, one useful starting action, readable controls and financial tables. Use semantic surfaces and text colours so the same hierarchy works in light and dark themes. Keep calculations, source data, plan gates and account content intact.

## Delivered changes

| Area | Change |
| --- | --- |
| Shared page headers | Compact tier badge, readable title and description, visible related-page buttons; display header statistics only where they add information. |
| Sidebar | Personal workspace immediately below Overview; clearer active destination; active link revealed in its scroll area; phone drawer focuses search, contains keyboard focus and restores body scrolling on close. |
| Dashboard | Navy welcome panel with research shortcut; actual followed-company, alert and saved-screen counts; collapsed optional setup checklist; consistent widget surfaces and empty states. |
| Watchlists | Clear active list, readable search/filter controls, five compact desktop metrics and two columns on phones; remove duplicate header counts. |
| My portfolio | Separate Add a share, Paste a list and Import a file modes; expandable model explanation; existing import and PDF review retained. |
| MF portfolio | Shared surfaces, controls, metric cards and table treatment. |
| Alerts | Clear preset cards and controls; four desktop metrics and two phone columns; remove duplicate header counts. |
| My baskets | Shorter explanation, one creation action and one usage count; remove redundant header statistics and empty-state CTA. |
| Help and account | Integrated FAQ surfaces; account cards and tabs use the shared hierarchy; dashboard FAQ matches the current layout. |
| Stock fundamentals | Repair table layout collision; larger viewport, aligned columns, wrapping row labels, sticky header and first column, numeric alignment, alternating surfaces and selected-row accent. |

## Financial table defect and fix

The `pm-pick` class was shared by statement tables and the market index search picker. Its picker rule set `display:flex`, `max-height:140px` and vertical overflow on the table itself. This separated the header/body sizing and reduced the usable table to a couple of rows.

Statement tables now use `pm-statement` and, when chart selection is enabled, `pm-selectable`. The index search picker uses `pm-index-picker`. Financial table wrappers use `pm-table-scroll` and retain native table layout, with a maximum height of 640px. Short tables grow only to their content height; longer tables keep every row available by scrolling. Depending on label wrapping, approximately 9–11 complete rows fit in the cash-flow viewport. Labels are proper row headers and remain pinned during horizontal scrolling. Long labels wrap within their column rather than overlapping values. A narrow-phone action-row fix also prevents the company report links from widening the page.

No statement periods, reported values, growth formulas or model calculations were changed by this UI pass.

## Verification

- Production frontend build passed.
- Full frontend suite: 135 files, 1,810 tests passed, using two workers and a 15-second test timeout. Initial runs under load timed out; the outdated dashboard FAQ text expectation was updated and all failed files were rerun successfully before the final full pass.
- Desktop personal-workspace routes checked in light and dark: dashboard, watchlists, holdings, MF portfolio, alerts and baskets. No page-width overflow was found; five watchlist and four alert KPI columns were confirmed at 1280px.
- Shared header/surface and page-width checks in both themes: company report, stock screener, query builder, chart builder, Prism, DCF, commodities, macro, results, IPOs, mutual funds and account appearance. These are presentation checks, not end-to-end validation of every financial workflow.
- TCS income statement (37 rows), balance sheet (70 rows) and cash flow (119 rows): native table display and matching header/body column positions confirmed. Ratios and both shareholder tables also align.
- Cash-flow table verified in desktop light/dark and a 390px phone layout. At 320px the page also fits after wrapping the company actions. Row selection still changes the chart. Sticky headers and labels were verified; all rows remain available.
- Portfolio entry mode switches were exercised without adding holdings. Phone product drawer focuses its search input and closes with Escape.
- Empty local portfolio/market states remain honest; no holdings or figures were fabricated.

Screenshots are in the local review folder `design-review/demo-preview/workspace/`, including `fundamentals-light.png`, `fundamentals-dark.png` and the mobile variants. Changes are local; this pass did not deploy to AWS.

## Maintenance

`styles/page-header.css` owns header-specific styles. `styles/workspace.css` is imported after the shared theme and page layers and owns the workspace presentation overrides. Keep selectors scoped to workspace or financial-table components. Do not reuse table class names for pickers. Replace older styles deliberately as later pages receive more specific redesign work, instead of adding unscoped global table layout rules.

## Footer and sidebar follow-up

Page questions now render inside `AppShell` after the route content and expand to the full content-column width. The public `Layout` owns one full-width footer after the workspace, below both columns. Desktop navigation is sticky while reading the page and questions, then stops above the footer; it does not extend into or sit alongside the footer. The page uses normal browser scrolling so existing anchor links, pagination and scroll-to-top actions continue to work. On phones the navigation remains a drawer and content scrolls naturally. Workspace routes use `Layout workspace` to avoid rendering a second FAQ section. `SiteFooter` is a shared component, and a shell regression check verifies FAQ placement and footer separation.

## Global market strip follow-up

The market strip renders through the shared site layout on public, workspace and sign-in routes. It uses the same `/api/indices` query everywhere, independent of the company being viewed, and polls every minute. Two matching visual groups provide a seamless scroll; the second is hidden from assistive technology. Readers can pause it, hover/focus to read, or scroll manually. Reduced-motion preferences keep the strip static and manually scrollable. Earlier blanket animation blockers no longer target the ticker.

The strip labels closing data as `Last close`. The research API fetches FinEdge's index daily feed and overlays validated Dhan index quotes during market hours when configured. Closing values are not tick-by-tick live prices; polling is one minute. On 1 November 2026 the local endpoint returned `marketOpen: false`, `live: false`, FinEdge rows dated 30 October 2026. This verifies the current close-price response, not a successful open-market Dhan session. Missing percentage moves remain missing rather than appearing as zero. Each quote exposes its provider and timestamp in its tooltip.
