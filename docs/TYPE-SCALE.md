# One type scale for the whole site

Every font size on the site is one of eleven sizes (the team's type-scale handover, `docs/typescale-src/`). The rule sheet is
`docs/typescale-src/rules.pdf`; the handover is `docs/typescale-src/finlit_typescale/README.md`.

| Token | Size / line | Use |
|---|---|---|
| `--fs-11` | 11 / 16 | Eyebrows, chart axis ticks, legend keys. Uppercase labels only, never sentences |
| `--fs-12` | 12 / 16 | Captions, timestamps, chips, footnotes |
| `--fs-13` | 13 / 18 | Secondary text, labels, dense table cells |
| `--fs-14` | 14 / 20 | Default: card and table text, menus, buttons |
| `--fs-16` | 16 / 24 | Reading text, key values, every form field |
| `--fs-18` | 18 / 24 | Card titles (Source Serif 4, 600) |
| `--fs-20` | 20 / 28 | Section titles |
| `--fs-24` | 24 / 32 | Big numbers (KPIs) |
| `--fs-28` | 28 / 36 | Page title on phones, report section titles |
| `--fs-32` | 32 / 40 | Page title on desktop |
| `--fs-40` | 40 / 48 | Hero numbers, company name on wide screens |

Role names for new code: `--fs-label --fs-caption --fs-small --fs-body --fs-reading --fs-card-title --fs-section-title --fs-kpi --fs-page-title`
(`--fs-page-title` is 32px, 28px on phones). Tokens live in `frontend/src/styles/typescale.css`, loaded first in `main.tsx`.
The team's `--type-*` tokens in `design-system.css` are in rem on the same sizes (0.875rem = 14px and so on) and are untouched.

## What was done

1. **Source rewritten with the codemod** (`docs/typescale-src/finlit_typescale/fontsize_codemod.py src --write --tokens`):
   1,563 font sizes in 97 files. CSS got `var(--fs-N)`, JSX/SVG/inline styles got the px value. 12.5 to 13 (436), 13.5 to 14 (278),
   11.5 to 12 (154), 15 to 16 (145), 10.5 to 11 (102), 10 to 11 (82), 14.5 to 14 (73), 22 to 20 (53), 17 to 16 (44), 19 to 18 (34),
   26 to 24 (29), 9.5 to 11 (23), 21 to 20 (21), 30 to 32 (19), and the rest in smaller groups (including every 6 to 9px size to 11).
   Not touched: `src/content/*.json`, `node_modules`, 0px (text hidden on purpose), 44px and up, `pt` sizes inside `@media print`.
2. **The codemod's by-hand list (relative and computed sizes), each fixed**
   - `charts/MiniBars.tsx` axis labels (9.5 or 11): 11 in both modes; label spacing assumes 6.8px per character in both.
   - `components/markets/MarketsBlock.tsx` + `lib/markets.ts` heat-map tiles: `labelFont()` no longer shrinks to 8.5px. It steps down
     14, 13, 12, 11 and returns 0 when 11px does not fit, and the tile then shows no label (name and move stay in the hover card and `aria-label`).
     Tile colours are now the sheet's scale `#2E7D57 to #17583B` (greens), `#B5473D to #8E2620` (reds), `#6B6455` (flat); white text passes 4.5:1 on every stop (tested).
   - `components/search/parts.tsx` initials in logo placeholders (`size * 0.34`, down to 8px): 11, 12, 14 or 16 by logo size.
   - `stock/Sections3.tsx` peer-orbit labels (9.5 or 11): 11, with the symbol cut to 5 letters in small bubbles.
   - `styles/finlit.css` `.rs` (rupee sign, `.6em`) 24px next to the 44/32px price; `.unit` (`.66em`) 13px; `styles/mf.css` `sup` 11px;
     `styles/site.css` marquee star 16px; `qbuilder.css` and `qresults.css` code and tag chips (`.92em`, `.45em`) 13px or 12px.
   - Other `em`/`%`/`calc` sizes: none left (the test fails on any).
3. **Fluid `clamp()` sizes.** `clamp()` with a largest value under 28px was replaced by the scale size. Page titles (`.ph-title`, dashboard H1, ETF H1,
   preparing page) use `--fs-page-title`. Big figures (`.bs-v`, `.qt-v`, `.tr-v`, `.dcf-k b`, `.cm-big`, `.fl-fig .big`, `.sip-big b`) are 24 or 28.
   The company name is 28 / 32 / 40 by width. **Kept fluid on purpose** (largest value 28px or more: marketing and editorial headings):
   home and Plans headings, blog headings, the quote and tagline blocks, platform grid, Legal and Pricing heads. The allow-list is in the test.
4. **Report tokens** `--fs-h4 15 to 16`, `--fs-small 12.5 to 13`, `--fs-chip 10.5 to 11`, phone `--fs-h3 17 to 18` in `report-polish.css`
   (they share names with the role tokens and now agree with them).
5. **Form fields are 16px at every width** (`typescale.css`, `!important`: the field styles were spread over 40 files at 13 and 14px; phones already had it).
6. **`<small>`, `<sup>`, `<sub>` default to 12px** (the browser default is "smaller", about 10px). Class rules still win.
7. **Chart text at the size the reader sees** (`lib/svgText.ts`, started in `main.tsx`). SVG text is sized in the chart's own units; a 720-unit chart
   drawn 332px wide on a phone shrank an 11-unit label to 5px, and a stretched chart grew it to 18px. Each `<text>` is set to the nearest scale size
   (never under 11px) divided by the chart's scale; it follows resize and re-render. This is not the `fontscale.js` stopgap (that snapped CSS rules in
   the browser; it is not shipped).
8. **Cards and controls** (low-risk swaps only): card titles 18px, Source Serif 4, 600 (also on phones); help "?" icons 20px with a 32px tap area and a 12px glyph.
   The card radius is already 16px (`calm.css --r-card`).

## Checks

- `frontend/src/styles/typescale.test.ts` scans every `.css`, `.ts`, `.tsx` in `src/` (not `content/`) and fails with `file:line` for any font size under
  11px, off the scale, relative or computed, unknown `--fs-N`, or a `clamp()` whose largest value is under 28px. Allowed: 44px and up, 0, `inherit`, `clamp()` 28px and up.
- `src/lib/svgText.test.ts` (chart text), `src/lib/markets.test.ts` (heat-map label steps and tile contrast).
- Real-browser measurement: see the delivery notes (computed sizes per page, before and after).

## Not done (and why)

- The dashboard changes (handover section 6) and the company-report restructuring (sticky contents bar): not asked for in this task.
- Table header 12px / cells 14px everywhere, shared card padding 20/24 and 16px gaps, 40/44px control heights, grey loading placeholders: each is spread
  over many page-specific rules, so a global swap would change layouts; the codemod already put every table, card and control text on the scale.
  The design system already forces 44px minimum heights on buttons and inputs; nothing was shrunk.
- `pt` sizes in the print stylesheet (`@media print`, `.pp`) and the 40px canvas texture in `three/Plot3D.tsx` (a 3D label sprite, scaled by the scene) are not screen text.
- Dashboard heat-map tiles too narrow for 11px show no label (by design); the tile still shows the move and a hover card.
