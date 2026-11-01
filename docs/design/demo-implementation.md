# Review implementation and demo checks

Updated 1 November 2026. User-approved implementation of the website review and landing-page proposal, using the supplied Design System v1.3 reference. This is a local preview; no production deployment was performed.

## Latest demo update

The later [minimalism and motion direction](minimalism-and-motion.md) adds the opening introduction, product-and-services homepage, simpler Services page and product directory. Its demo walkthrough replaces the earlier homepage sequence below.

## Delivered

| Area | Change |
|---|---|
| Landing page | Empty company search with keyboard navigation, a live and explicitly labelled Reliance sample, three research tasks, concise methodology, real founder introduction and compact plan summaries. |
| Content depth | Full feature catalogue moved to `/platform`; detailed features and quotas stay on `/plans`. Removed homepage 3D decorations, ticker, repeated account prompts and notification signup. |
| Navigation | Research, Markets, Funds and Plans form the public navigation; less-used destinations are grouped under More. Phone navigation uses expandable groups. The complete product rail remains available inside tools. |
| Visual system | Navy, ivory and restrained gold; Inter for product headings and figures, Source Serif 4 for editorial headings. Plain report surfaces and clear focus outlines replace ornamental treatments. Removed old rules forcing light-theme reports/plans into dark surfaces. |
| Help | Header/menu/footer entry replaces the floating launcher. Auth pages have no assistant overlay. Guided help now starts with research, screener, Prism and access questions; services remain reachable. |
| Company report | One plain FinLit score and simpler pillar values, labelled phone actions, compact plan introduction and one destination for the complete strengths/concerns list. Trading eligibility is expandable; exchange-surveillance warnings remain visible. |
| Prism report | One headline financial score; separate technical views; completeness and validation shown independently. Component strengths/concerns precede factor details. Calculation arithmetic is expandable, while factor inputs, sources, histories and warnings remain available. No contribution weights in the summary or factor headings. |
| Calculation state | Real elapsed time and a status message; removed elapsed-time-derived percentage progress. Polling/retry behavior is unchanged. |
| Screener | Filters and results take priority; coverage charts and the optional 3D view are expandable. The 3D scene mounts only when requested. |
| Chart builder | One empty chart initially; choosing a company starts its price chart. Explicit company links and saved/shared configurations still work. No implicit Reliance selection. |
| Dashboard | Onboarding is ahead of the optional market overview. Market charts mount when opened. Appearance preferences remain in Customise. |

Financial model formulas, scoring ranges, factors, data-source hierarchy, backend APIs, access checks and PDF generation were not changed by this UI pass. Calculation details remain available for audit; simplification is presentation-only.

## Verification

- Full frontend suite: **133 files, 1,798 tests passed**.
- Subsequent targeted regression checks cover the updated search, Prism summary, graph state, stylesheet ownership and opaque overlays.
- Production build passes (`npm run build`, including TypeScript). Existing bundle-size warnings remain; they do not block the build.
- `git diff --check` passes.
- In-app browser: real Reliance sample loads; empty search finds TCS and Enter opens its company report.
- TCS report: plain overall score and five pillar values render; the main report has no horizontal page overflow at the desktop width checked.
- Reliance Prism: completeness of 100% and “Review required” are distinct. The summary link reaches data checks, with warning notes open. Quality-component navigation focuses the factor section; the calculation disclosure opens.
- Screener: real local results render; coverage disclosure starts closed, with no 3D canvas mounted. The isolated local database has three ingested company reports, not the full production screener universe.
- Chart builder: starts at 1×1 with no company; selecting TCS produces one share-price chart.
- Plans: request-access wording renders and light-theme cards use white surfaces.
- Mobile: landing page checked at 390 px (dark) and 320 px (light); search is in the first viewport, the menu is usable and the final 320 px layout has no page overflow. Help opens from the menu. Prism reflow was also inspected at 320 px without page overflow.

The local preview uses the existing development APIs and an isolated local database populated through the existing provider integration. No fabricated company figures were added to the application. Browser-test screenshots/logs are kept outside Git.

## Demo walkthrough

1. Open the homepage; explain the company search and labelled sample.
2. Search TCS, then open its company report and strengths/concerns.
3. Open Reliance in FinLit Prism; distinguish financial score, separate technical views, completeness and validation.
4. Open a component's factors and data checks; demonstrate that the evidence remains available.
5. Show the screener and the one-chart starting point in Chart builder.
6. Finish with the team and Plans. Silver/Gold activation is by request; pricing is unannounced.

## Follow-up review

- Validate wording and the research-first emphasis with the team and representative users.
- Complete a dedicated assistive-technology, actual 200% browser-zoom and cross-browser pass; the viewport checks above are not a claim of that full accessibility audit.
- The original design reference still marks some chart, spacing, grid, navigation and motion choices as candidates or “TO DESIGN”. This pass does not change those source-document approval labels.
- Confirm deployment and the public-domain cutover separately. Local preview availability does not mean the AWS site or old public-domain site has been updated.
