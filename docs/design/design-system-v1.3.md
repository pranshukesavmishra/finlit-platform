# FinLit Design System v1.3 source snapshot

Source: [Finlit Yusra Google design document](https://docs.google.com/document/d/1Rz1CdPwluvpsZkYp_60xEtR4PgymB0ukOj_zI6MQwkw/edit?tab=t.ltp1jxuuxcp6).
Specification version: 1.3, dated 27 October 2026. Exported and read on 1 November 2026.

This is the retained Markdown export of the supplied design-system content. The Google document remains the maintained source; this file is not automatically synchronised. Source labels such as FINAL, PROPOSED, CANDIDATE and TO DESIGN are preserved. This snapshot is documentation and does not change application styles.

See the [design index](README.md) for implementation status and the separate proposed landing-page review.

---

**FINLIT VENTURES**

**Design System**

Color, Typography & Theme Specification

| \#0B192C | \#C6A76A | \#F5F3ED |
| :---- | :---- | :---- |
| **Midnight Navy** | **Champagne Gold** | **Warm Ivory** |

 

| Document | Details |
| :---- | :---- |
| Version | 1.3  ·  27 October 2026 |
| Audience | UI/UX designers (primary); frontend developers (secondary) |
| Covers | Brand colors, light and dark theme colors, financial and status colors, chart colors, fonts, text styles, number formatting, component rules, accessibility |
| Does not cover yet | Spacing, grid, icons, shadows, animation (see section 13\) |
| Status | Brand colors and fonts are final. Some values are proposed and need checking on real screens. |

 

**Contents**

1\. How to use this document

2\. Design principles

**COLOR**

3\. Brand colors

4\. Theme colors

5\. Financial and status colors

6\. Chart colors

7\. Approved color pairings

**TYPOGRAPHY**

8\. Fonts

9\. Text styles

10\. Numbers and financial data

**APPLYING THE SYSTEM**

11\. Components

12\. Accessibility requirements

13\. Still to define

14\. Design deliverables and sign-off checklist

15\. Decision register

**APPENDICES**

Appendix A. Notes for developers

Appendix B. CSS tokens

Appendix C. References

# 

# 

# 

# **1\. How to use this document**

This is the single source of truth for color and typography on FinLit. Every color and every piece of text in a FinLit design must use a named color or text style from this document. If you need something that is not here, ask for it to be added instead of picking a new hex value or font size.

## **1.1 Status labels**

Each color, style and decision carries one of these labels:

| Label | Meaning | What you should do |
| :---- | :---- | :---- |
| **FINAL** | Approved and contrast-checked | Use as specified |
| **PROPOSED** | Contrast-checked, not yet reviewed on real screens | Use it, and flag anything that looks wrong in context |
| **CANDIDATE** | Starting value that still needs testing | Test in realistic layouts before relying on it |
| **TO DESIGN** | Not defined yet | Owned by the design team; see section 13 |

## **1.2 Naming**

Color names follow the pattern \--category-role-state, for example \--action-primary-hover. Developers call these "tokens"; in Figma they are color variables. Create them in two modes (Light and Dark) with the same names, without the leading dashes. Designs should use the variables, never raw hex values, so switching modes updates every screen.

Text styles have short names such as body-01 or table-value. Create a Figma text style with exactly that name for each one in section 9\.

## **1.3 Themes**

•     Light mode is the default.

•     Dark mode is fully supported and must be designed for every screen, not generated afterward.

•     The app follows the system setting until the user picks a theme; their choice is then remembered.

# **2\. Design principles**

| Principle | What it means in practice |
| :---- | :---- |
| **Clarity before decoration** | Figures, ratios, reports and labels come first. Ornament never competes with data. |
| **Progressive depth** | A beginner gets a clear first view; an expert can reach full tables and analysis without detours. |
| **Color has a job** | Every color has one defined role. Brand, financial meaning, status, validation and chart series never share colors. |
| **Never color alone** | Every color signal is paired with a sign, arrow, icon, label or underline. |
| **Numbers must be right** | A figure must show the correct unit, sign and decimals. Number formatting is a correctness rule, not a style choice. |
| **Premium but restrained** | The serif font and gold add a premium feel on brand and editorial pages. Data screens stay plain and functional. |
| **One system everywhere** | Research pages, screeners, calculators, pricing and auth all use the same tokens and components. |
| **Validate on real screens** | Swatches and contrast numbers are a starting point. Final approval happens on real, populated screens. |

# **3\. Brand colors**

These five colors define FinLit's identity. Everything else in this document exists to support usability and financial meaning.

|   | Name | HEX | RGB | Role |
| :---- | :---- | :---- | :---- | :---- |
|   | **Midnight Navy** | \#0B192C | 11, 25, 44 | Primary identity, headings, light-mode primary button |
|   | **Deep Navy** | \#172E48 | 23, 46, 72 | Secondary identity, dark-mode surfaces |
|   | **Champagne Gold** | \#C6A76A | 198, 167, 106 | Premium accent, dark-mode primary button |
|   | **Warm Ivory** | \#F5F3ED | 245, 243, 237 | Light-mode page background |
|   | **Pure White** | \#FFFFFF | 255, 255, 255 | Cards, tables, form surfaces |

 

## **3.1 Gold usage rules**

| Do | Don't |
| :---- | :---- |
| Use gold for the logo, thin accent rules and premium details on light backgrounds | Use gold for text, icons or indicators on white or ivory (2.3:1, fails) |
| Use gold as the primary button in dark mode (7.7:1 with navy text) | Use gold to mean profit, a good investment, or a recommendation |
| Use one gold element per view as a focal point | Make every button or highlight gold; the primary action must stand out |
| Use the darker gold \#7F6326 if gold-tinted text is ever required in light mode | Use gold as a chart series color |

# **4\. Theme colors**

Each row shows the color name, its light and dark values, and where to use it. Every text color below is readable on every background in its theme, and every border and focus color is clearly visible (see section 7 for the numbers).

## **4.1 Surfaces**

| Token |   | Light |   | Dark | Use it for | Status |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| \--bg-page |   | \#F5F3ED |   | \#0B192C | Page canvas behind everything | **FINAL** |
| \--bg-surface |   | \#FFFFFF |   | \#172E48 | Cards, tables, dashboards, forms | **FINAL** |
| \--bg-subtle |   | \#ECEFF3 |   | \#203A56 | Sidebars, grouped panels, table header rows | **FINAL** |
| \--bg-elevated |   | \#FFFFFF |   | \#29445F | Mega-menu, dropdowns, popovers, tooltips, modals | **FINAL** |
| \--bg-selected |   | \#E3ECFB |   | \#1E3D66 | Selected table row, active search result | **PROPOSED** |
| \--overlay |   | navy 48% |   | black 60% | Dark see-through backdrop behind pop-up windows and the search overlay | **PROPOSED** |

 

| Surface layering.  Light mode: ivory page → white cards → white popovers with a shadow. Dark mode gets lighter as it rises: page → surface → subtle → elevated. Never place a surface on the same color as its parent without a border. |
| :---- |

## **4.2 Text**

| Token |   | Light |   | Dark | Use it for | Status |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| \--text-primary |   | \#0B192C |   | \#F8F6F1 | Headings, key figures, prices | **FINAL** |
| \--text-body |   | \#334155 |   | \#D5DEE8 | Paragraphs, navigation labels | **FINAL** |
| \--text-secondary |   | \#475569 |   | \#B5BFCC | Labels, captions, column headers | **FINAL** |
| \--text-muted |   | \#5B6779 |   | \#A5B1C2 | Timestamps, placeholders, helper text | **PROPOSED** |
| \--text-disabled |   | \#8A94A3 |   | \#6B7F98 | Disabled controls only (exempt from contrast) | **PROPOSED** |
| \--text-link |   | \#1D4ED8 |   | \#93C5FD | Inline links (always underlined in body copy) | **PROPOSED** |

## **4.3 Borders and focus**

| Token |   | Light |   | Dark | Use it for | Status |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| \--border-subtle |   | \#D6DCE4 |   | \#526780 | Card edges, dividers, table row lines (decorative) | **FINAL** |
| \--border-control |   | \#737F8E |   | \#8196AC | Inputs, selects, checkboxes, radio buttons, outlined buttons | **FINAL** |
| \--focus-ring |   | \#6D28D9 |   | \#A78BFA | Keyboard focus outline on every interactive element | **FINAL** |

 

| Important.  Use \--border-subtle only for decoration. Any boundary the user needs to see to use a control (input, checkbox, outlined button) must use \--border-control. |
| :---- |

## **4.4 Actions and brand**

| Token |   | Light |   | Dark | Use it for | Status |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| \--action-primary |   | \#0B192C |   | \#C6A76A | Primary button fill | **FINAL** |
| \--action-primary-hover |   | \#1E3350 |   | \#D4B97F | Primary button on hover | **PROPOSED** |
| \--action-primary-pressed |   | \#050E1A |   | \#B39257 | Primary button while pressed | **PROPOSED** |
| \--action-on-primary |   | \#FFFFFF |   | \#0B192C | Text and icons on the primary button | **FINAL** |
| \--action-disabled-bg |   | \#E2E6EB |   | \#1E3550 | Disabled button fill | **PROPOSED** |
| \--brand-accent |   | \#C6A76A |   | \#C6A76A | Logo, thin rules, premium details (decorative only) | **FINAL** |

# **5\. Financial and status colors**

These colors carry meaning about money and system state. They are deliberately separate from brand colors, chart colors and each other.

## **5.1 Foreground colors**

| Token |   | Light |   | Dark | Use it for | Status |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| \--financial-positive |   | \#166534 |   | \#4ADE80 | Favorable movement, always with \+ sign or up arrow | **FINAL** |
| \--financial-negative |   | \#B91C1C |   | \#FCA5A5 | Unfavorable movement, always with − sign or down arrow | **FINAL** |
| \--financial-neutral |   | \#5B6779 |   | \#A5B1C2 | Unchanged (0.00%) and "Not available" values | **PROPOSED** |
| \--status-warning |   | \#9A3412 |   | \#FDBA74 | Caution notices, stale data, risk flags | **FINAL** |
| \--status-info |   | \#1D4ED8 |   | \#93C5FD | Neutral notices and tips | **FINAL** |
| \--form-error |   | \#BE123C |   | \#FDA4AF | Form validation errors only | **FINAL** |

## **5.2 Background tints (badges, banners, alerts)**

Put the matching foreground color from 5.1 on these tints. All pairs pass 5.2:1 or better in both themes.

| Token |   | Light |   | Dark | Use it for | Status |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| \--financial-positive-bg |   | \#DCFCE7 |   | \#0F3A2A | Gain badge / success banner fill | **PROPOSED** |
| \--financial-negative-bg |   | \#FEE2E2 |   | \#4A1D24 | Loss badge fill | **PROPOSED** |
| \--status-warning-bg |   | \#FFEDD5 |   | \#4A2A12 | Warning banner fill | **PROPOSED** |
| \--status-info-bg |   | \#DBEAFE |   | \#172F55 | Info banner fill | **PROPOSED** |
| \--form-error-bg |   | \#FFE4E6 |   | \#4C1426 | Error summary box fill | **PROPOSED** |

## **5.3 Rules for financial meaning**

•     **Direction is not judgement.** A share price going up is a direction, not a recommendation. Debt going up can be unfavorable; revenue going up can be favorable. Color by what is favorable for that metric, and label it.

•     **Always add a non-color cue.** Show \+/− signs and ▲/▼ arrows on every colored change. About 1 in 12 men cannot reliably tell this red from this green.

•     **Missing is not zero.** In tables show "—"; everywhere else show "Not available". Both use \--financial-neutral. Never show 0 for missing data (see section 10.7).

•     **Errors are not losses.** Form errors use rose (--form-error), never the loss red, so "you made a mistake" never looks like "you lost money".

•     **Warnings are not brand.** Warning is burnt orange, kept clearly apart from champagne gold.

 

## **5.4 Example treatments**

| Case | Display | Color token |
| :---- | :---- | :---- |
| Stock up today | ▲ \+2.41% | \--financial-positive |
| Stock down today | ▼ −1.08% | \--financial-negative |
| No change | 0.00% | \--financial-neutral |
| Data missing (card) | Not available | \--financial-neutral |
| Data missing (table cell) | — | \--financial-neutral |
| Debt rose (unfavorable) | ▲ \+18% debt | \--financial-negative |
| Data delayed | ⚠ Prices delayed 15 min | \--status-warning on \--status-warning-bg |
| Invalid PAN in form | ⊘ Enter a valid 10-character PAN | \--form-error |

# **6\. Chart colors**

Charts use their own set of colors. Brand gold and the status colors (green, red, orange) are never used for chart lines or bars.

## **6.1 Colors for chart lines and bars**

When a chart shows several lines or bars, give them these colors in this fixed order. A line keeps its color when others are hidden. If a chart needs more than six, group the rest into "Other" or split it into several small charts.

| \# | Name |   | Light |   | Dark | Status |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| 1 | Blue |   | \#2563EB |   | \#60A5FA | **CANDIDATE** |
| 2 | Teal |   | \#0D9488 |   | \#2DD4BF | **CANDIDATE** |
| 3 | Plum |   | \#9F5A8A |   | \#D58BC0 | **CANDIDATE** |
| 4 | Amber |   | \#B45309 |   | \#FBBF24 | **CANDIDATE** |
| 5 | Magenta |   | \#BE185D |   | \#F472B6 | **CANDIDATE** |
| 6 | Slate |   | \#64748B |   | \#CBD5E1 | **CANDIDATE** |

 

## **6.2 Chart rules by type**

| Chart | Color rule |
| :---- | :---- |
| Price history (one line) | Use color 1 (blue). Green/red only for the change figure, not the line. |
| Revenue, margin, debt | Color shows which line is which; whether a rise is good depends on the metric. |
| P\&L comparison, several lines | Colors in order, each line labeled directly or in a legend, with different markers or dash styles. |
| Portfolio allocation | Colors in order; label every segment with its name and percentage. |
| Market heatmap | Red for falls, grey for no change, green for rises, with the middle point labeled. The middle is always grey. |
| Research score | Shades of one color from light (low) to dark (high), with labeled score bands. |
| Scenarios | Base, optimistic and pessimistic as clearly labeled lines; do not use red/green for them. |
| Missing data | Grey or striped area plus a text label. Never draw it as zero. |

 

| Testing still needed.  Every chart color stands out clearly from its background, but two neighbouring lines can still be hard to tell apart, especially for color-blind users. Check real charts with a color-blindness simulator (for example the one built into Figma plugins or Chrome DevTools) before marking final. |
| :---- |

# **7\. Approved color pairings**

Contrast is how strongly a color stands out from its background, as a ratio. The accessibility standard requires at least 4.5:1 for text and 3:1 for borders, focus rings and chart lines. Each number below is the worst case: the lowest contrast that color reaches on any background in its theme.

| Token |   | Light | Min |   | Dark | Min |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| \--text-primary |   | \#0B192C | 15.3 |   | \#F8F6F1 | 9.3 |
| \--text-body |   | \#334155 | 9.0 |   | \#D5DEE8 | 7.4 |
| \--text-secondary |   | \#475569 | 6.6 |   | \#B5BFCC | 5.4 |
| \--text-muted |   | \#5B6779 | 5.0 |   | \#A5B1C2 | 4.6 |
| \--text-link |   | \#1D4ED8 | 5.8 |   | \#93C5FD | 5.6 |
| \--financial-positive |   | \#166534 | 6.2 |   | \#4ADE80 | 5.8 |
| \--financial-negative |   | \#B91C1C | 5.6 |   | \#FCA5A5 | 5.3 |
| \--status-warning |   | \#9A3412 | 6.3 |   | \#FDBA74 | 6.0 |
| \--status-info |   | \#1D4ED8 | 5.8 |   | \#93C5FD | 5.6 |
| \--form-error |   | \#BE123C | 5.5 |   | \#FDA4AF | 5.3 |
| \--border-control |   | \#737F8E | 3.5 |   | \#8196AC | 3.3 |
| \--focus-ring |   | \#6D28D9 | 6.2 |   | \#A78BFA | 3.7 |

 

| Specific pair | Light | Dark |
| :---- | :---- | :---- |
| Primary button text on primary button | 17.7:1 | 7.7:1 |
| … on hover state | 12.8:1 | 9.3:1 |
| … on pressed state | 19.4:1 | 6.0:1 |
| Primary text on selected row | 14.8:1 | 10.2:1 |
| Status color on its own tint (worst case) | 5.2:1 | 7.3:1 |
| Gold on white or ivory | 2.3:1  ✗ decorative only | n/a |

 

| Scope.  These checks cover solid colors on the backgrounds listed here. They do not cover text on photos, see-through layers, or new combinations. Check any new combination with a contrast checker before using it. |
| :---- |

# **8\. Fonts**

FinLit uses two fonts. Inter is the working font for the whole product. Source Serif 4 adds a premium, editorial feel, and is only used for large headings on brand and article pages.

## **8.1 The fonts**

| Font | Role | Used for | Status |
| :---- | :---- | :---- | :---- |
| **Inter** | Main font | Everything in the product: navigation, buttons, forms, tables, charts, dashboards, research screens, article body text | **FINAL** |
| **Source Serif 4** | Editorial headings | Large headings on the homepage, marketing and service pages, and article/report templates | **FINAL** |
| **Inter (numbers)** | Financial figures | Prices, returns, ratios and statements, with fixed-width numbers switched on (see 10.1) | **FINAL** |
| **Inter (IDs)** | Reference codes | PAN, ISIN, order and transaction IDs, with look-alike characters made distinct (see 10.8) | **PROPOSED** |
| **Noto Sans Devanagari** | Future Hindi support | Hindi text, if and when the product is translated. Not needed yet. | **CANDIDATE** |

 

| Both fonts are free.  Inter and Source Serif 4 are open-source and available from Google Fonts. Install the variable versions, which contain every weight in one file. |
| :---- |

## **8.2 Where the serif font may be used**

The test is simple: the serif may only appear on pages whose main content is written text. It never appears on anything that shows live or financial data.

| Serif allowed | Serif never used |
| :---- | :---- |
| Homepage hero headline | Navigation and mega-menu |
| Marketing and service page headings | Stock research screens |
| Article page headings (H1, H2) | Financial statements and tables |
| Report headings, when the report is mainly written text | Charts and Graph Studio |
|   | Screeners and calculators |
|   | Forms, field labels and buttons |
|   | Any heading containing a number, KPI cards, live prices |

 

•     Article body text is Inter, even when the article headings are serif. This is deliberate: it keeps long reading consistent with the rest of the product.

•     Financial figures are never in the serif font.

## **8.3 Light and dark mode**

•     Use the same text styles in both themes. Font, size and weight do not change when the theme changes.

•     Light text on dark navy can look slightly bolder. Only adjust weights if testing on real screens shows a problem, and record any change here.

•     Avoid serif weights thinner than Regular (400) on dark backgrounds; thin strokes break up.

## **8.4 Setting up the fonts in Figma**

•     Use the variable versions of both fonts so Figma and the website draw letters the same way.

•     Both fonts adjust their letter shapes slightly at very large and very small sizes to stay readable. Browsers do this automatically. In Figma, make sure the font's "Optical size" setting follows the font size, so mockups match the live site.

•     Compare a few headings in Figma and in a browser at the same size before finalising letter spacing.

# **9\. Text styles**

Every piece of text uses one of these named styles. Create a Figma text style for each, with exactly this name. Sizes are shown as font size / line height in pixels.

## **9.1 Style list**

| Style name | Font | Size / line | Weight | Fixed-width numbers | Use for |
| :---- | :---- | :---- | :---- | :---- | :---- |
| display-01 | Source Serif 4 | 56 / 64 | Regular 400 | — | Homepage hero headline |
| editorial-h1 | Source Serif 4 | 40 / 48 | Regular 400 | — | Article and marketing page title |
| editorial-h2 | Source Serif 4 | 32 / 40 | Regular 400 | — | Article and marketing section heading |
| heading-01 | Inter | 40 / 48 | Medium 500 | — | Product page title |
| heading-02 | Inter | 32 / 40 | Semibold 600 | — | Product section heading |
| heading-03 | Inter | 24 / 32 | Semibold 600 | — | Sub-section heading |
| heading-04 | Inter | 20 / 28 | Semibold 600 | — | Card and panel heading |
| editorial-body | Inter | 18 / 28 | Regular 400 | — | Article body text |
| body-01 | Inter | 16 / 24 | Regular 400 | — | Standard paragraphs; text typed into form fields |
| body-compact | Inter | 14 / 20 | Regular 400 | — | Dense screens, descriptions in tools |
| nav-label | Inter | 14 / 20 | Medium 500 | — | Header and menu links |
| field-label | Inter | 14 / 20 | Medium 500 | — | Labels above form fields (proposed) |
| button-label | Inter | 14 / 20 | Semibold 600 | — | All button text |
| table-header | Inter | 14 / 20 | Semibold 600 | Yes | Table column headings |
| table-value | Inter | 14 / 20 | Regular 400 | Yes | Numbers and text in table cells |
| stat-value-lg | Inter | 32 / 40 | Semibold 600 | If it updates live | Main figure, e.g. portfolio value |
| stat-value-md | Inter | 24 / 32 | Semibold 600 | If it updates live | KPI and summary cards |
| chart-label | Inter | 12 / 16 | Regular 400 | Yes | Chart axis labels and legends |
| caption | Inter | 12 / 16 | Regular 400 | — | Timestamps, footnotes, sources |
| helper-text | Inter | 14 / 20 | Regular 400 | — | Hints and error messages under form fields |
| identifier | Inter | 14 / 20 | Medium 500 | Yes | PAN, ISIN, order and transaction IDs |

 

## **9.2 Rules for the styles**

•     **Letter spacing is 0 for every style.** The fonts already tighten themselves at large sizes. Only change spacing for headings and large figures after comparing Figma with the browser; until then those values are provisional.

•     **Large headings are deliberately lighter.** heading-01 is Medium while heading-02 to 04 are Semibold. Big text already has visual weight, so it does not need to be as heavy. This is intentional; do not "fix" it.

•     **caption and chart-label look identical** but are kept as separate styles, because they may need to change independently later.

•     **Form fields use 16px for typed text.** Smaller text makes phones zoom in when the user taps the field.

•     **No new sizes.** If a screen seems to need a size or weight not listed here, propose a new style for the system rather than adding a one-off.

## **9.3 Mobile sizes**

On small screens, large headings shrink. Everything from body text down stays the same size; never shrink body text, table values or chart labels to fit more in.

| Style | Desktop | Mobile |
| :---- | :---- | :---- |
| display-01 | 56 / 64 | 36 / 44 |
| editorial-h1 | 40 / 48 | 30 / 38 |
| editorial-h2 | 32 / 40 | 26 / 34 |
| heading-01 | 40 / 48 | 30 / 38 |
| heading-02 | 32 / 40 | 26 / 34 |
| heading-04 | 20 / 28 | 18 / 26 |
| stat-value-lg | 32 / 40 | 28 / 36 |
| Body, navigation, tables, charts, captions | unchanged | unchanged |

 

•     Design and check layouts at 320, 360, 390, 768 and 1280 px wide, plus a large desktop.

•     Nothing should make the page scroll sideways on a phone. Wide financial tables scroll inside their own box, or are rearranged, instead of shrinking the numbers.

•     Mobile sizes are starting values; confirm them on real components.

# **10\. Numbers and financial data**

How numbers look is a correctness issue on FinLit. A wrong sign, unit or number of decimals can mislead an investor. These rules apply to every screen.

## **10.1 Lining numbers up**

In normal text, digits have different widths (a 1 is narrower than an 8). For tables and live prices we switch on Inter's fixed-width numbers, where every digit takes the same space. Columns then line up and prices don't jiggle as they update. In Figma this setting is called "Tabular figures" (Type settings → Numbers).

| Where | Fixed-width numbers |
| :---- | :---- |
| Table values and table headings with numbers | Always |
| Live prices and the market ticker | Always |
| KPI cards whose values update | Always |
| Chart axis values | Yes, where they need to line up |
| Numbers in marketing headlines or article text | Not needed |

 

•     Number columns are right-aligned; row labels and descriptions are left-aligned.

•     Values in the same column use the same number of decimals.

## **10.2 How to show each kind of number**

| Data | Show it as | Notes |
| :---- | :---- | :---- |
| Stock price | ₹1,202.00 | Two decimals (unless the instrument trades in smaller steps) |
| Price change | \+₹12.50  /  −₹12.50 | Always show the sign |
| Percentage change | \+12.45%  /  −12.45% | Always show the sign |
| Full rupee amount | ₹1,25,000.00 | Transactions and statements where exact value matters |
| Large company figure | ₹3,11,850 Cr | Default for revenue, market cap, etc. |
| Table of statement figures | 3,11,850 | Unit goes in the column heading, e.g. "Revenue (₹ Cr)" |
| Ratio or multiple | 24.65× | Use the × sign, not the letter x |
| Accounting-style negative | (1,250) | Only in statements that explicitly use accounting style |
| Share quantity | 1,250 | Whole numbers unless fractions are allowed |
| Missing (table cell) | — | Screen readers announce "Not available" |
| Missing (card, form, summary) | Not available | Written out in full |

## **10.3 Indian comma grouping**

All numbers use Indian grouping: the first comma after three digits, then every two digits.

| Number | Shown as |
| :---- | :---- |
| 125000 | 1,25,000 |
| 311850 | 3,11,850 |
| 12500000 | 1,25,00,000 |

## **10.4 Short forms (Cr, L Cr)**

•     Default to crores: ₹3,11,850 Cr. Most users read this easily.

•     Use lakh crore (₹3.12 L Cr) only where space is genuinely tight, such as a small card on mobile. Beginners may not read it correctly.

•     Whenever a short form is used, the full value must be available in a tooltip, label or detail view.

•     In tables, state the unit once in the column heading instead of repeating it in every cell.

## **10.5 Decimal places**

| Data | Decimals |
| :---- | :---- |
| Stock prices | 2 (more only if the instrument needs it) |
| Percentages | 2 (more where a tiny change would otherwise show as 0.00%) |
| Ratios | 2, unless the metric needs otherwise |
| Share quantities | 0, unless fractional shares are allowed |
| Statement figures | The same throughout each table |

 

Rounding is only for display. The underlying data is never rounded.

## **10.6 Signs, zero and tiny values**

| Case | Show | Not |
| :---- | :---- | :---- |
| A rise | \+12.45% | 12.45% |
| A fall | −12.45%  (true minus sign) | \-12.45%  (hyphen) |
| Exactly no change | 0.00%  (no sign, neutral color) | \+0.00% or −0.00% |
| A tiny fall that rounds to zero | ▼ \<0.01% | −0.00%  or  0.00% |
| A tiny rise that rounds to zero | ▲ \<0.01% | \+0.00%  or  0.00% |

 

The true minus sign (−) is the same width as the plus sign, so columns stay aligned. A hyphen (-) is narrower and looks wrong in figures. Gains and losses also follow the color rules in section 5: never color alone, always a sign or arrow.

## **10.7 Zero, missing and not applicable**

These are different things and must never look the same:

| Situation | In a table | Elsewhere |
| :---- | :---- | :---- |
| Actual value is zero | 0 or 0.00 | 0 or 0.00 |
| Value exists but we don't have it | — (read aloud as "Not available") | Not available |
| Value does not apply (e.g. P/E for a loss-making company) | — (read aloud as "Not applicable") | Not applicable |

 

Tables that use "—" should include a short note explaining what it means.

## **10.8 Reference codes (PAN, ISIN, order IDs)**

Codes that mix letters and digits are easy to misread: 0 and O, 1 and I and l. Use the identifier style, which turns on Inter's alternate letter shapes that make these characters distinct. In Figma, enable Inter's "Disambiguation" option in the type settings for this style.

•     Users must be able to select and copy codes.

•     Spacing codes into groups for readability must not change the code itself when copied.

•     Stock ticker symbols (e.g. RELIANCE) use normal text styles, not the identifier style.

# **11\. Components**

## **11.1 Buttons**

| Variant | State | Fill | Text / icon | Border |
| :---- | :---- | :---- | :---- | :---- |
| **Primary** | Default | \--action-primary | \--action-on-primary | none |
|   | Hover | \--action-primary-hover | \--action-on-primary | none |
|   | Pressed | \--action-primary-pressed | \--action-on-primary | none |
|   | Focus | as current state | as current state | 2px \--focus-ring, 2px offset |
|   | Disabled | \--action-disabled-bg | \--text-disabled | none |
| **Secondary** | Default | transparent | \--text-primary | 1px \--border-control |
|   | Hover | \--bg-subtle | \--text-primary | 1px \--border-control |
|   | Disabled | transparent | \--text-disabled | 1px \--border-subtle |
| **Text button** | Default | transparent | \--text-link | none; underline on hover |

 

•     All button text uses button-label.

•     Only one primary button per view. The guest header has a single primary action: Sign in.

•     Minimum tap area: 44 × 44 px on touch screens. On desktop, buttons can look 32 px tall as long as the clickable area is 44 px.

## **11.2 Form fields**

| State | Fill | Border | Text | Extra cue |
| :---- | :---- | :---- | :---- | :---- |
| Default | \--bg-surface | 1px \--border-control | \--text-primary; placeholder \--text-muted | — |
| Hover | \--bg-surface | 1px \--text-secondary | — | — |
| Focus | \--bg-surface | 2px \--focus-ring | — | — |
| Error | \--bg-surface | 2px \--form-error | message in \--form-error | Error icon \+ text message below field |
| Disabled | \--action-disabled-bg | 1px \--border-subtle | \--text-disabled | — |

 

•     Every field has a visible label above it (field-label); placeholder text is never the only label.

•     Typed text uses body-01 (16px). Hints and error messages under the field use helper-text.

•     Errors always have an icon and a written message, never just a red border.

•     If the form is submitted with errors, show a summary box (--form-error-bg) at the top listing each problem.

## **11.3 Other components**

| Component | Background | Text styles | Notes |
| :---- | :---- | :---- | :---- |
| **Header** | \--bg-page | nav-label, button-label | Logo left; navigation; search; theme switch; one Sign in button. Account menu after login. |
| **Market ticker** | \--bg-subtle | table-value | Separate strip above the header; changes use financial colors with ▲/▼. |
| **Mega-menu** | \--bg-elevated \+ shadow | nav-label, body-compact | Clear groups; works with keyboard and touch; visible focus. |
| **Search overlay** | \--bg-elevated on \--overlay | body-01, caption | Categories, recent searches, previews; highlighted result uses \--bg-selected. |
| **Cards** | \--bg-surface \+ \--border-subtle | heading-04, stat-value-md, caption | Separate with spacing and edges; shadows only for floating elements. |
| **Tables** | \--bg-surface; header row \--bg-subtle | table-header, table-value | Numbers right-aligned; units and dates stated; selected row \--bg-selected. |
| **Sidebar** | \--bg-subtle | body-compact, table-value | All financial colors checked on this background. |
| **Active nav item** | \--text-primary \+ 2px underline | nav-label | Underline required as well as color. |
| **Tooltip** | Light: navy with white text. Dark: \--bg-elevated | body-compact | Never hide essential data only in a tooltip. |
| **Badges / alerts** | tint \+ matching text color | body-compact | Always include an icon and a text label. |
| **Charts** | \--bg-surface | chart-label, caption | See section 6 for colors. |
| **Pricing plans** | \--bg-surface cards | heading-03, body-01 | Gold may mark a premium plan as decoration; never use status colors for tiers. |

## **11.4 Focus indicator**

When someone moves through the page with the keyboard, the element they are on gets a 2px \--focus-ring outline with a 2px gap around it. The gap keeps the ring visible next to the navy or gold primary button. Never remove focus outlines.

# **12\. Accessibility requirements**

Target: WCAG 2.2 Level AA (the international accessibility standard) across the whole product. The last column gives the rule number for reference.

| Requirement | What it means | WCAG |
| :---- | :---- | :---- |
| Normal text contrast | ≥ 4.5:1 | 1.4.3 |
| Large text (≥ 24px, or ≥ 18.66px bold) | ≥ 3:1 | 1.4.3 |
| Control borders, icons, focus rings, chart marks | ≥ 3:1 | 1.4.11 |
| Meaning never by color alone | Add sign, arrow, icon, label or underline | 1.4.1 |
| Visible keyboard focus | On every interactive element | 2.4.7 |
| Focus not hidden | Sticky header/ticker must not cover focused items | 2.4.11 |
| Target size | ≥ 24 × 24 px minimum; 44 × 44 px preferred | 2.5.8 |
| Zoom and reflow | Usable at 200% zoom and at 320 px width | 1.4.4, 1.4.10 |
| Text resizing | Text can be enlarged to 200% without anything being cut off | 1.4.4 |
| Text spacing | Layouts survive users increasing line, letter and paragraph spacing | 1.4.12 |
| Headings in order | Headings follow the page structure (H1, then H2…), not just look bigger | 1.3.1 |
| Numbers read aloud correctly | Screen readers announce values, signs and "Not available" clearly | 1.1.1 |

# **13\. Still to define**

These are not part of this version. The design team owns them; nothing above should block this work.

| Area | What is needed | Status |
| :---- | :---- | :---- |
| Letter spacing | Final values for headings and large figures, after comparing Figma and browser | **CANDIDATE** |
| Mobile text sizes | Confirm the starting sizes in 9.3 on real components | **CANDIDATE** |
| Spacing and grid | Spacing scale (suggest a 4 px base), page grid, compact layouts for data-heavy views | **TO DESIGN** |
| Shadows | Shadow levels for cards, menus and pop-ups in both themes | **TO DESIGN** |
| Icons | Icon set, sizes, line weight, financial icons (▲▼, warning, info, error) | **TO DESIGN** |
| Animation | Durations, easing, behaviour when users turn off motion | **TO DESIGN** |
| Chart scales | Final light-to-dark and red-grey-green scales, checked with a color-blindness simulator | **CANDIDATE** |
| Membership badges | Gold/Silver tier marks that don't clash with status colors | **TO DESIGN** |
| Mega-menu content | Labels and grouping (information architecture review) | **TO DESIGN** |

# **14\. Design deliverables and sign-off checklist**

## **14.1 First deliverables**

•     Figma color variables for every color in sections 4–6, in Light and Dark modes.

•     Figma text styles for every style in section 9, with desktop and mobile versions of the headings.

•     Component sheet: buttons, inputs, badges, alerts, table rows and nav items in every state, both themes.

•     The six test screens below, in both themes.

## **14.2 Test screens**

The system is only approved once it works on these real FinLit screens:

| Screen | What to check |
| :---- | :---- |
| Homepage | Serif headlines, brand feel, headings on mobile |
| Profit & loss statement | Numbers line up, decimals, units, dense tables |
| Graph Studio | Axis labels, legends, controls, several lines readable |
| Company research on mobile | Heading sizes, long company names, KPI cards |
| Header and mega-menu | Navigation fits at laptop widths, 14px labels readable, keyboard use |
| Sign in and forms | Labels, hints, errors, reference codes |

## **14.3 Sign-off checklist**

☐    Every color comes from a variable; no loose hex values

☐    Every piece of text uses a named text style; no one-off sizes or weights

☐    Serif appears only where section 8.2 allows

☐    Number columns line up and use the same decimals

☐    Signs, units, Indian commas and "Not available" follow section 10

☐    Header, mega-menu and search designed in both themes

☐    Research page and P\&L table designed in both themes

☐    Multi-series chart is labeled and distinguishable in color-blind simulation

☐    Form error, warning and financial loss look clearly different side by side

☐    Every gain and loss has a sign or arrow, not just color

☐    "Not available" and zero values are visually distinct

☐    Focus ring visible on every interactive element, including on the primary button

☐    All screens usable at mobile width and at 200% zoom, with no sideways scrolling

☐    Figma and browser rendering match closely in both themes

☐    Any new color combination has been contrast-checked and added to section 7

# **15\. Decision register**

| Decision | Status | Next step |
| :---- | :---- | :---- |
| Navy / gold / ivory brand direction | **FINAL** | Build Figma variables and core components |
| Light mode default, full dark mode | **FINAL** | Design every screen in both themes |
| Theme, text and financial color tokens | **FINAL** | Use as specified |
| State, tint and overlay tokens | **PROPOSED** | Review on real component screens |
| Violet focus indicator | **FINAL** | Apply to all interactive elements |
| Single "Sign in" header action | **FINAL** | Produce responsive header variants |
| Inter \+ Source Serif 4, serif limited to editorial pages | **FINAL** | Set up Figma text styles |
| Text style list and sizes | **FINAL** | Use as specified |
| Number formatting rules | **FINAL** | Developers build shared formatting functions (Appendix A) |
| Letter spacing and mobile sizes | **CANDIDATE** | Confirm on the test screens |
| Chart color set | **CANDIDATE** | Test with real charts and a color-blindness simulator |
| Spacing, icons, shadows, animation | **TO DESIGN** | Separate design-system chapters |

## **Changes in version 1.3**

•     Added typography: fonts and where each may be used (8), the full text style list with mobile sizes (9), and rules for numbers and financial data (10).

•     Added text styles to the components table, and typography items to the accessibility, checklist and decision sections.

•     Aligned the missing-data rule across color and typography: "—" in tables, "Not available" elsewhere.

•     Rewrote technical terms in plain language and moved developer-only detail to Appendix A.

## **Changes in version 1.2**

•     Restructured for designers: swatches, light/dark side by side, component state tables, status labels.

•     Defined the missing colors from v1.1 (link, hover, disabled, selected row, backdrop, neutral, tints) and gave colors consistent names.

# **Appendix A. Notes for developers**

Designers can skip this appendix. It covers how the rules above are built in code.

## **A.1 Using the styles**

•     Colors and text styles are defined once as CSS variables (Appendix B). Components use the variables; no hard-coded hex values, font sizes or font families.

•     Font sizes are written in rem so they grow when users enlarge text. Divide the pixel value by 16: 14px \= 0.875rem, 20px \= 1.25rem.

•     Fixed-width numbers: font-variant-numeric: tabular-nums on table, ticker, live KPI and chart-label styles.

•     Focus outlines use :focus-visible, so the ring shows for keyboard users but not on mouse clicks.

•     Theme is set with data-theme on the root element. Follow the system setting by default, remember the user's choice, and avoid a flash of the wrong theme on load.

## **A.2 Loading the fonts**

•     Self-host the variable font files. Keep the full Inter build so the alternate shapes for reference codes (10.8) are not stripped out; some packaged web versions remove them.

•     Load only the Latin and Latin Extended character sets on English pages. Load the Devanagari font only on pages that contain Hindi.

•     Preload only the font files needed for the first screen.

•     Use a fallback system font sized to match Inter, so text doesn't jump when the real font arrives. Test font-display options and measure layout shift rather than assuming one setting.

## **A.3 Number formatting**

One general-purpose number function is not enough. Build separate, tested functions for each kind of data, all using the en-IN locale:

•     Prices · rupee amounts · percentages · signed changes · ratios · quantities · statement figures with units · crore and lakh-crore short forms · missing values (table vs elsewhere).

Two things the browser's built-in formatter (Intl.NumberFormat) gets wrong for our rules, which the functions must handle:

•     It outputs a hyphen (-) for negatives; replace it with the true minus sign (U+2212).

•     Its short notation produces "31LCr" for lakh crore; write a custom function for "₹3.12 L Cr".

Each function must pass these checks:

| Function | Input | Expected output |
| :---- | :---- | :---- |
| price | 1202 | ₹1,202.00 |
| price | 1202.5 | ₹1,202.50 |
| signed change (₹) | −12.5 | −₹12.50 |
| percentage change | 0.1245 | \+12.45% |
| percentage change | 0 | 0.00% |
| percentage change | −0.00004 | ▼ \<0.01% |
| percentage change | −0 (negative zero) | 0.00% |
| crore amount | 311850 (in Cr) | ₹3,11,850 Cr |
| lakh-crore short form | 311850 (in Cr) | ₹3.12 L Cr |
| statement figure | 12500000 | 1,25,00,000 |
| ratio | 24.654 | 24.65× |
| missing value, table | null | — (with "Not available" for screen readers) |
| missing value, card | null | Not available |

 

•     Keep full precision in calculations; round only when displaying.

•     Never format numbers by hand inside individual components.

# **Appendix B. CSS tokens**

For developers. Designers mirror these names as Figma color variables and text styles.

:root {  
  color-scheme: light;  
   
  /\* Brand primitives \*/  
  \--brand-navy: \#0B192C;  
  \--brand-navy-deep: \#172E48;  
  \--brand-gold: \#C6A76A;  
  \--brand-ivory: \#F5F3ED;  
   
  /\* Surfaces \*/  
  \--bg-page: \#F5F3ED;  
  \--bg-surface: \#FFFFFF;  
  \--bg-subtle: \#ECEFF3;  
  \--bg-elevated: \#FFFFFF;  
  \--bg-selected: \#E3ECFB;  
  \--overlay: rgba(11, 25, 44, 0.48);  
   
  /\* Text \*/  
  \--text-primary: \#0B192C;  
  \--text-body: \#334155;  
  \--text-secondary: \#475569;  
  \--text-muted: \#5B6779;  
  \--text-disabled: \#8A94A3;  
  \--text-link: \#1D4ED8;  
   
  /\* Borders and focus \*/  
  \--border-subtle: \#D6DCE4;  
  \--border-control: \#737F8E;  
  \--focus-ring: \#6D28D9;  
   
  /\* Actions \*/  
  \--action-primary: \#0B192C;  
  \--action-primary-hover: \#1E3350;  
  \--action-primary-pressed: \#050E1A;  
  \--action-on-primary: \#FFFFFF;  
  \--action-disabled-bg: \#E2E6EB;  
  \--brand-accent: \#C6A76A;  
   
  /\* Financial and status \*/  
  \--financial-positive: \#166534;  
  \--financial-negative: \#B91C1C;  
  \--financial-neutral: \#5B6779;  
  \--status-warning: \#9A3412;  
  \--status-info: \#1D4ED8;  
  \--form-error: \#BE123C;  
   
  /\* Tints \*/  
  \--financial-positive-bg: \#DCFCE7;  
  \--financial-negative-bg: \#FEE2E2;  
  \--status-warning-bg: \#FFEDD5;  
  \--status-info-bg: \#DBEAFE;  
  \--form-error-bg: \#FFE4E6;  
   
  /\* Chart series (candidate) \*/  
  \--chart-1: \#2563EB;  
  \--chart-2: \#0D9488;  
  \--chart-3: \#9F5A8A;  
  \--chart-4: \#B45309;  
  \--chart-5: \#BE185D;  
  \--chart-6: \#64748B;  
}  
   
\[data-theme="dark"\] {  
  color-scheme: dark;  
   
  /\* Surfaces \*/  
  \--bg-page: \#0B192C;  
  \--bg-surface: \#172E48;  
  \--bg-subtle: \#203A56;  
  \--bg-elevated: \#29445F;  
  \--bg-selected: \#1E3D66;  
  \--overlay: rgba(0, 0, 0, 0.60);  
   
  /\* Text \*/  
  \--text-primary: \#F8F6F1;  
  \--text-body: \#D5DEE8;  
  \--text-secondary: \#B5BFCC;  
  \--text-muted: \#A5B1C2;  
  \--text-disabled: \#6B7F98;  
  \--text-link: \#93C5FD;  
   
  /\* Borders and focus \*/  
  \--border-subtle: \#526780;  
  \--border-control: \#8196AC;  
  \--focus-ring: \#A78BFA;  
   
  /\* Actions \*/  
  \--action-primary: \#C6A76A;  
  \--action-primary-hover: \#D4B97F;  
  \--action-primary-pressed: \#B39257;  
  \--action-on-primary: \#0B192C;  
  \--action-disabled-bg: \#1E3550;  
  \--brand-accent: \#C6A76A;  
   
  /\* Financial and status \*/  
  \--financial-positive: \#4ADE80;  
  \--financial-negative: \#FCA5A5;  
  \--financial-neutral: \#A5B1C2;  
  \--status-warning: \#FDBA74;  
  \--status-info: \#93C5FD;  
  \--form-error: \#FDA4AF;  
   
  /\* Tints \*/  
  \--financial-positive-bg: \#0F3A2A;  
  \--financial-negative-bg: \#4A1D24;  
  \--status-warning-bg: \#4A2A12;  
  \--status-info-bg: \#172F55;  
  \--form-error-bg: \#4C1426;  
   
  /\* Chart series (candidate) \*/  
  \--chart-1: \#60A5FA;  
  \--chart-2: \#2DD4BF;  
  \--chart-3: \#D58BC0;  
  \--chart-4: \#FBBF24;  
  \--chart-5: \#F472B6;  
  \--chart-6: \#CBD5E1;  
}  
   
/\* \---------- Typography (same in both themes) \---------- \*/  
:root {  
  /\* Font families \*/  
  \--font-sans: "Inter", system-ui, \-apple-system, "Segoe UI", Roboto, sans-serif;  
  \--font-serif: "Source Serif 4", Georgia, "Times New Roman", serif;  
   
  /\* Text styles: weight size/line-height family \*/  
  \--type-display-01: 	400 3.5rem/4rem   	var(--font-serif);  
  \--type-editorial-h1:   400 2.5rem/3rem   	var(--font-serif);  
  \--type-editorial-h2:   400 2rem/2.5rem   	var(--font-serif);  
  \--type-heading-01: 	500 2.5rem/3rem   	var(--font-sans);  
  \--type-heading-02: 	600 2rem/2.5rem   	var(--font-sans);  
  \--type-heading-03: 	600 1.5rem/2rem   	var(--font-sans);  
  \--type-heading-04: 	600 1.25rem/1.75rem   var(--font-sans);  
  \--type-editorial-body: 400 1.125rem/1.75rem  var(--font-sans);  
  \--type-body-01:    	400 1rem/1.5rem   	var(--font-sans);  
  \--type-body-compact:   400 0.875rem/1.25rem  var(--font-sans);  
  \--type-nav-label:  	500 0.875rem/1.25rem  var(--font-sans);  
  \--type-field-label:	500 0.875rem/1.25rem  var(--font-sans);  
  \--type-button-label:   600 0.875rem/1.25rem  var(--font-sans);  
  \--type-table-header:   600 0.875rem/1.25rem  var(--font-sans);  
  \--type-table-value:	400 0.875rem/1.25rem  var(--font-sans);  
  \--type-stat-value-lg:  600 2rem/2.5rem   	var(--font-sans);  
  \--type-stat-value-md:  600 1.5rem/2rem   	var(--font-sans);  
  \--type-chart-label:	400 0.75rem/1rem  	var(--font-sans);  
  \--type-caption:    	400 0.75rem/1rem  	var(--font-sans);  
  \--type-helper-text:	400 0.875rem/1.25rem  var(--font-sans);  
  \--type-identifier: 	500 0.875rem/1.25rem  var(--font-sans);  
   
  /\* Letter spacing: 0 everywhere until checked in browser \*/  
  \--tracking-default: 0;  
}  
   
/\* Mobile heading sizes \*/  
@media (max-width: 767px) {  
  :root {  
    \--type-display-01: 	400 2.25rem/2.75rem   var(--font-serif);  
    \--type-editorial-h1:   400 1.875rem/2.375rem var(--font-serif);  
    \--type-editorial-h2:   400 1.625rem/2.125rem var(--font-serif);  
    \--type-heading-01: 	500 1.875rem/2.375rem var(--font-sans);  
    \--type-heading-02: 	600 1.625rem/2.125rem var(--font-sans);  
    \--type-heading-04: 	600 1.125rem/1.625rem var(--font-sans);  
    \--type-stat-value-lg:  600 1.75rem/2.25rem   var(--font-sans);  
  }  
}  
   
/\* Fixed-width numbers for tables, tickers, live KPIs, chart labels \*/  
.num, .table-value, .table-header, .chart-label, .identifier {  
  font-variant-numeric: tabular-nums;  
}  
 

# **Appendix C. References**

•     W3C Web Content Accessibility Guidelines 2.2: https\://www\.w3.org/TR/WCAG22/

•     IBM Carbon Design System (themes, type scale, data visualization): https\://carbondesignsystem.com/

•     Inter typeface: https\://rsms.me/inter/

•     Source Serif 4: https\://fonts.google.com/specimen/Source+Serif+4

•     MDN, Intl.NumberFormat: https\://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global\_Objects/Intl/NumberFormat

Contrast ratios use the WCAG 2.x relative-luminance formula and can be reproduced with any standard contrast checker