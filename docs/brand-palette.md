# FinLit colour system

Follows the brand direction in the FinLit Technical Improvement & Modernization Plan (Phase 4.4): **ivory, black and muted gold**, with clear contrast. One palette, defined once as CSS variables in `frontend/src/styles/finlit.css`; every chart, card and gradient uses these tokens. Ivory is the default theme; a warm-black dark theme is available from the toggle.

| Role | Ivory (default) | Warm black (dark) | Used for |
|---|---|---|---|
| Page / surfaces | `#F6F1E7` / `#FFFDF8` | `#0F0E0B` / `#17150F` | Backgrounds |
| Text | `#16140E` | `#F4EFE3` | Body and headings |
| Muted gold | `#8A6A25` (light `#C9A24E`) | `#D4B26A` (deep `#A8843A`) | Brand accents, buttons, key numbers, score arc |
| Charcoal / stone | `#2E2A20` / `#8A8472` | `#EDE6D3` / `#A39B88` | Secondary chart series, info |
| Gain / loss | `#2F7A58` / `#A8392F` | `#5FB88E` / `#E0707A` | Only for up/down and good/bad meaning |

Categorical data (five score pillars, ownership holders, revenue segments) uses gold, charcoal and stone in different lightness, never extra hues. No blue, violet, pink or cyan anywhere. The Silver plan tier is a cool grey accent beside gold.
