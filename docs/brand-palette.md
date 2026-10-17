# FinLit colour system

One restrained palette, defined once as CSS variables in `frontend/src/styles/finlit.css`. Everything else (charts, cards, gradients) uses these tokens, so changing a colour there changes the whole site.

| Role | Dark theme | Light theme | Used for |
|---|---|---|---|
| Background | `#060C1A` navy | `#F1F4FB` | Page |
| Brand gold | `#EBC46A` (deep `#C9952F`, pale `#F7E4B0`) | `#9A6A0E` | Logo accents, buttons, key numbers, score arc |
| Steel blue | `#86A5DC` (ice `#C9DAF5`) | `#3B5FA0` | Secondary series, info, "Basic" tier |
| Slate | `#9AA9C8` | `#6B7A99` | Muted series |
| Gain / loss | `#34D399` / `#FB7185` | `#047857` / `#BE123C` | Only for up/down and good/bad meaning |

Categorical data (five score pillars, ownership holders, revenue segments) uses the gold / steel family in different lightness, never extra hues. The bronze tier is the only warm accent beyond gold.
