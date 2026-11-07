# FinLit type scale and dashboard refresh: handover

Font sizes, card rules and the dashboard changes, for the whole site. Measured on finlitventures.com on 4 Nov 2026 (50 pages, desktop 1222 px and phone 375 px). The visual reference is the canvas **"FinLit dashboard refresh"** (desktop dashboard, phone dashboard, and the type rules), shared separately.

| File | What it is |
|---|---|
| `tokens.css` | The scale as CSS variables (`--fs-11` … `--fs-40`, with line heights and role names), plus three site-wide basics |
| `fontscale.js` | Stopgap: snaps every font size in the site's CSS to the scale when a page loads. One script tag, every page and tab |
| `fontsize_codemod.py` | The real fix: rewrites font sizes in the source (CSS, JSX, SVG, Tailwind) and lists the ones a person must check |
| `test_typescale.py` | Tests for both (`python test_typescale.py`; the browser test needs Playwright) |

## 1. The scale

Eleven sizes replace the 70+ font-size values in the live CSS (37 style files).

| Token | Size / line | Font | Use it for |
|---|---|---|---|
| `--fs-11` | 11 / 16 | Inter 600, uppercase, 0.08em tracking | Eyebrows, chart axis ticks, legend keys. Labels only, never sentences |
| `--fs-12` | 12 / 16 | Inter | Captions, timestamps, table headers, chips, footnotes |
| `--fs-13` | 13 / 18 | Inter | Secondary text, labels, dense table cells |
| `--fs-14` | 14 / 20 | Inter | Default: card and table text, menus, buttons |
| `--fs-16` | 16 / 24 | Inter | Reading text, key values, **every form input** (phones zoom in below 16px) |
| `--fs-18` | 18 / 24 | Source Serif 4 600 | Card titles |
| `--fs-20` | 20 / 28 | Source Serif 4 600 | Section titles |
| `--fs-24` | 24 / 32 | Inter 600 | Big numbers: KPIs, index level |
| `--fs-28` | 28 / 36 | Source Serif 4 600 | Page title on phones, report section titles |
| `--fs-32` | 32 / 40 | Source Serif 4 600 | Page title on desktop (today 36px on app pages) |
| `--fs-40` | 40 / 48 | Inter 600 | Hero numbers (score dial) |

Marketing display headings (44px and up, and the `clamp()` heroes) stay as they are. Numbers use tabular figures.

**Old size → new size** in the live CSS (about 960 rules change; another 954 are already on the scale):

| Old | New | Rules | | Old | New | Rules |
|---|---|---|---|---|---|---|
| 12.5px | 13 | 338 | | 9.5px | 11 | 12 |
| 13.5px | 14 | 230 | | 15.5px | 16 | 12 |
| 11.5px | 12 | 83 | | 19px | 18 | 10 |
| 15px | 16 | 72 | | 9px | 11 | 9 |
| 14.5px | 14 | 57 | | 21px | 20 | 9 |
| 10.5px | 11 | 31 | | 26px | 24 | 7 |
| 17px | 16 | 28 | | 30px, 34px, 36px | 32 | 8 |
| 10px | 11 | 27 | | 23px, 25px | 24 | 3 |
| 22px | 20 | 15 | | 8px, 8.5px | 11 | 2 |

The cut points: up to 11 → 11; 11.5–12 → 12; 12.5–13 → 13; 13.5–14.5 → 14; 15–17 → 16; 17.5–19 → 18; 19.5–22 → 20; 22.5–26 → 24; 26.5–29 → 28; 29.5–37 → 32; 37.5–43.5 → 40. Left alone: 0px (text hidden on purpose) and 44px and up.

## 2. How to apply it

**Step 1, today: `fontscale.js`.** Add `<script src="/fontscale.js"></script>` to `<head>` in `index.html`. It changes each rule's font size in place in the browser, so selectors, cascade order and `!important` are untouched. Route styles that load later are caught as they arrive, and chart labels drawn with `font-size="10"` are raised by a small rule sheet. Removing the tag undoes it.

Measured on the Asian Paints company report with it switched on: 960 rules changed, text on the scale went to 87%, and text under 11px fell from 15.7% to 4.2%. Layout held on the pages checked. What it cannot reach (and step 2 handles):
- sizes written as `calc()` or `var()` (29 rules) or `em` (5 rules);
- sizes set by JavaScript at run time (the heatmap tiles shrink labels to fit, down to 8.5px);
- the FAQ title (26px) and a few other sizes that come from those rules.

**Step 2, this sprint: `fontsize_codemod.py` on the source.**
```
python fontsize_codemod.py src                  # dry run: every change, file and line, nothing written
python fontsize_codemod.py src --write --tokens # rewrite; CSS gets var(--fs-13), JSX/SVG get the px value
```
Load `tokens.css` before the app's CSS, then remove `fontscale.js`. The run ends with a list of relative and computed sizes (`0.92em`, `calc(1em - 1.5px)`, `fontSize: w / 9`). Fix each so the result is 11px or more. For the heatmap: hide a tile's label when it would need less than 11px, and show it on hover.

**Step 3: check the busy pages.** These have the most text that grows: company report, IPO calendar, option chain, glossary, latest results, mutual funds, and the dashboard heatmap. Look for labels that no longer fit their box, table columns that wrap, and chips that wrap to two lines. Check each at 1280px and at 375px.

## 3. Cards, controls and spacing

| Thing | Rule |
|---|---|
| Card | Radius 16px, 1px border `#DDD3BD`, background `#FDFBF6`, padding 20px 24px (16px on phones). Today there are two styles: 20px radius with a light border and cream background on top blocks, and 16px radius with a 1.5px darker border and white background on widgets |
| Gaps | 16px between cards; 8 / 12 / 16 / 24 inside |
| Titles | Card title Source Serif 4 18px 600; section title 20px; subtitle 13px muted. Today: 15, 16, 18, 20 and 22px, in three weights |
| Buttons | 40px tall on desktop, 44px on phones, 14px 600 |
| Chips and tabs | 36px on desktop, 44px on phones, 13px |
| Help "?" icons | 20px glyph area in a 32px button (today 22px boxes with 10px glyphs) |
| Tables | Header 12px 600 muted, cells 14px, numbers right-aligned, tabular |
| Coloured tiles | White text only on colours that reach 4.5:1. Today's map greens give 3.1–4.4:1. Use the scale `#8E2620 #A12E26 #B5473D #6B6455 #2E7D57 #1F6B49 #17583B` (all pass with white) |
| Loading | Grey placeholder blocks while data loads; "empty" text only when the data comes back empty |

## 4. The company report

Asian Paints, checked on 4 Nov 2026. The fonts are the right ones: Inter for text and charts, and Source Serif 4 for the 19 section titles at 32px. The sizes are the problem:
- 3,938 pieces of text in **42 different sizes**, from 7.2px to 60px;
- **31% of the text is smaller than 12px**;
- the page is 38,785px tall, about 45 screens.

| Section | Text under 12px |
|---|---|
| Price history, statements and filings | 74% |
| How sales, profit and cash have moved | 73% |
| Sep 2026 quarter against a year ago | 59% |
| How it compares with its peers | 49% |
| Triggers to watch | 44% |
| Cash returned to shareholders | 37% |
| Top of the report (header, score, price) | 29% |

| Tiny element | Today | New |
|---|---|---|
| Chart axis numbers and years (about 250, SVG `font-size` attributes) | 9.5–10.5px | 11px |
| Info "i" icons (72) | 10px | 12px |
| Sort arrows ▲▼ (47) | 9px | 11px |
| "Score" labels (32) | 9.5px | 12px |
| Trend chips such as "Weakening" (26) | 10px | 12px |
| Plan badges "Basic" / "Gold" (21) | 10.5px | 11px uppercase |
| Insight tags such as "Strength" (11) | 9.5px | 12px |
| Dates such as "As of 03 Nov 2026" | 9.5px | 12px |
| "/ 100" in the compact score ring | 7.4px | 12px |
| "In simple words" explainers | 10.5px | 13px |

Beyond sizes: the report would read better with a sticky in-page contents bar (19 sections), with each section collapsed to its summary after the first three.

## 5. Every page, today

Font sizes used in each page's main area (default view), the share of text under 12px, and the smallest size.

| Page | Path | Sizes | Under 12px | Smallest |
|---|---|---|---|---|
| Company report | /stocks/ASIANPAINT | 42 | 31% | 7.2 |
| Dashboard | /dashboard | 33 | 15% | 8.5 |
| Compare companies | /compare | 20 | 23% | 9 |
| FII / DII | /fii-dii | 20 | 11% | 10.5 |
| Macro insights | /macro | 20 | 16% | 9.2 |
| Latest results | /results/quarter | 19 | 37% | 10 |
| Query builder | /query-builder | 18 | 13% | 10.1 |
| Equity mutual funds | /funds | 18 | 27% | 9 |
| Fair value (DCF) | /dcf | 17 | 16% | 10 |
| SIP calculator | /sip-calculator | 17 | 23% | 11 |
| Commodity prices | /commodities | 17 | 7% | 10 |
| Watchlist | /watchlist | 16 | 15% | 10 |
| Alerts | /alerts | 16 | 12% | 9.5 |
| EPS calculator | /eps-calculator | 16 | 17% | 10 |
| IPO calendar | /ipo | 16 | 40% | 10 |
| Option chain | /premium/options | 16 | 38% | 9.5 |
| Basic score screener | /score-screener | 15 | 4% | 10.5 |
| Advanced score screener | /advanced-score-screener | 15 | 8% | 10.5 |
| Correlation charts | /graphs/advanced | 15 | 14% | 10.5 |
| Plans | /plans | 15 | 8% | 10.5 |
| Stock screener | /screener | 14 | 1% | 10.5 |
| ETFs | /etfs | 14 | 8% | 10 |
| Company financials, income tab | /premium/fundamentals?c=… | 14 | 3% | 9.5 |
| Results calendar | /results | 13 | 22% | 10.5 |
| News and filings | /news | 13 | 0% | 11 |
| Mutual fund screener | /funds/screener | 13 | 11% | 10 |
| Services | /services | 13 | 6% | 11 |
| Equity portfolio | /holdings | 12 | 2% | 11 |
| Company search | /research | 12 | 2% | 11 |
| Prism | /prism | 12 | 6% | 11 |
| Outlook | /outlook | 12 | 6% | 11 |
| Chart builder | /graphs | 12 | 11% | 11 |
| Market events & index | /premium/markets | 12 | 4% | 10 |
| Glossary | /glossary | 12 | 38% | 10 |
| My baskets | /baskets | 12 | 3% | 11 |
| MF portfolio | /mf-portfolio | 11 | 5% | 11 |
| Premium reports | /premium/report | 11 | 5% | 11 |
| Company financials | /premium/fundamentals | 11 | 5% | 11 |
| How to read sector signals | /learn/sector-signals | 11 | 3% | 11 |
| Account: plan | /account/plan | 11 | 3% | 10.5 |
| About | /about | 11 | 11% | 11 |
| Account: appearance | /account/appearance | 10 | 2% | 10.5 |
| Why we exist | /why-we-exist | 10 | 8% | 11 |
| Sector Pulse | /sectors | 9 | 4% | 11 |
| Connect AI assistants | /mcp | 9 | 1% | 11 |
| Your account | /account | 9 | 4% | 10.5 |
| Documents | /documents | 8 | 16% | 11 |
| Contact | /contact | 8 | 7% | 11 |
| Forum | /forum | 7 | 4% | 11 |
| Blog | /blog | 7 | 0% | 12 |

"Under 12px" counts 11px labels too, which the scale allows. After the change, the goal for every page is: only the eleven sizes, and nothing under 11px. Headings today: app pages use H1 36px (account and forum pages 30–32px), the shared "Questions about this page" title is 26px, and card titles range from 15px to 22px. The header and side menu use 12–14px plus a 10.5px badge, which becomes 11px.

## 6. Dashboard changes (see the canvas)

Same page, same widgets, reordered and tidied:
1. **Order:** greeting with a slim "Setup 2 of 5" bar (replaces the mid-page checklist) → **Your stocks today** (price, today's move, FinLit score, latest quarter's revenue and profit growth, alert) → Market today with a **prices and rates strip** (Brent, USD/INR, repo, CPI, WPI, 10-year G-sec) → Market snapshot and **Sectors today as a ranked bar list** → FII/DII and **Stress Lab today** → index heatmap → results and filings → IPOs, alerts and saved screens, term of the day → FAQ, collapsed.
2. **Merge** "Heatmap" and "Sectoral activity" into one block with a Map / List switch.
3. **Gainers and decliners** default to Nifty 50 (switch: Nifty 500, All stocks), so upper-circuit small caps no longer fill the list.
4. **Results** shows results only, one line per company; **filings** are de-duplicated, tagged (Results, Board, Corporate, Capital) and cut to one line.
5. **Index cards:** same capitalisation for every name, one row of seven, P/E on every card (Sensex needs it added).
6. **Ask FinLit AI** moves into the header instead of a floating button that covers content.
7. **Gold & silver card removed:** it shows MCX prices that come through Dhan, which Dhan's terms do not allow on the site. Brent in the prices strip comes from the US EIA.
8. **Customise** lets users move and hide every block, the market blocks included (today only the lower 11 widgets).
9. **Phone:** three tabs (My stocks · Market · News) instead of 17 screens of scrolling; 44px tap targets; no "Dashboard" button in the header on the dashboard itself.
10. Capitalise the user's name in the greeting; drop the second GOLD badge.
