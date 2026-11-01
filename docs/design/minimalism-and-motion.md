# Minimalism and motion direction

Updated 1 November 2026 after reviewing [Mehman](https://mehman.ai/) in the in-app browser. The goal is to highlight FinLit's products and services through a restrained interface with purposeful motion. This updates the earlier search-first homepage emphasis; company search remains available in the product section.

## What the reference does well

These are observations from the rendered site, not claims about its internal implementation:

- A full-colour opening brand moment introduces the site before the main page.
- A small header, short headline and prominent action establish a clear starting point.
- One animated product demonstration does most of the explaining, with generous surrounding space.
- Scroll reveals lead into the product story and a small set of capability groups.
- Repeated colours, type, spacing and simple lines make the page feel connected.

The interpretation for FinLit is to give each section one job and let the product provide the proof. Keep the approved [Design System v1.3](design-system-v1.3.md): navy, ivory, restrained gold, Inter for product content and Source Serif 4 for permitted editorial headings. Do not copy Mehman's assets, travel motifs, typeface, palette, copy or waitlist mechanics.

## Direction across the interface

| Surface | Treatment | Demo status |
|---|---|---|
| Public navigation | Products, Services, Plans and More; retain the full tool navigation inside the workspace. | Implemented |
| Homepage | Products and services share the main promise. One real Reliance preview, three product introductions, company search, five concise service rows and the actual team. | Implemented |
| Product directory | Simple numbered rows and a plan filter. Preserve the existing thirteen tools; explicitly add Company research and FinLit Prism. Remove decorative sample dashboards and repeated plan banners from this page. | Implemented |
| Services | Five expandable conversations, using existing service names and descriptions. One enquiry route and clear educational scope. Remove the empty price-card catalogue and unrelated DCF sales pitch. | Implemented |
| Reports and dashboards | Calm shared surfaces and typography. Findings before details. Preserve meaningful factors, sources, warnings, missing values and access controls. | Existing first pass retained; shared finishing styles updated |
| Screeners and charts | Controls and results stay stable. Optional visualisation remains optional. Never animate a number through invented intermediate values. | Existing first pass retained |
| Forms and feedback | Clear labels, visible focus, opaque dialogs, explicit success/error responses and restrained transitions. | Existing flows retained; further flow-by-flow review planned |
| Account and auth | Immediate access, one clear action, no branded intro blocking sign-in or recovery. | Intro bypass implemented |

## Membership colour update — 1 November 2026

The user's subsequent direction adds colour to membership identity: **Basic uses green, Silver uses silver, and Gold uses gold**. This supersedes the v1.3 restriction on green tier accents; the original source specification remains preserved as history.

Use these colours for labelled membership badges, thin top rules, lightly tinted plan cards and product filters. Keep the navy/ivory foundation, readable body text and restrained motion. Labels remain visible so colour is never the only indication of plan access. Membership tokens are separate from financial gain/loss tokens and do not change when a member chooses an accent palette.

| Plan | Decorative accent, light / dark | Text, light / dark |
|---|---|---|
| Basic | `#438D68` / `#68B78D` | `#276749` / `#8BCBA8` |
| Silver | `#9DAABD` / `#AAB8CB` | `#526174` / `#CBD5E1` |
| Gold | `#C6A76A` / `#C6A76A` | `#7F6326` / `#DEC18A` |

Applied to homepage product badges, the product directory's badges and plan filters, the Plans page and the shared tier tokens. Prices, permissions and feature limits are unchanged.

## Homepage content discipline

Each section must help a visitor understand a product, choose a service or take a useful next step. Do not add a section merely to display the colour palette. Keep plan comparison and detailed entitlements on the Plans page.

The cleanup removes the separate Basic/Silver/Gold membership strip and its unused styles. Product badges retain the tier colours. It also removes a duplicate link inside the sample report, a generic hero caption, repeated plan/methodology promotion below the product search and the duplicate disclaimer above the footer. The product footer keeps All products and tools and Compare plans; the footer retains the full disclosure. The sample keeps its report date and one clear link to the full report.

## Opening experience

This is a short brand introduction, not a report-generation progress indicator.

- Show a navy field with the existing FinLit logo, a subtle gold line and the words “Company research & financial planning”.
- Fade the lockup in, then open the cover in two panels to reveal the site.
- Main hold is 1,250 ms, followed by a 380 ms exit. Release the cover by 3 seconds even if app startup is slow.
- Show once per browser-tab session on a home-page document entry. Internal navigation, company links, report links and auth routes open directly.
- Provide a visible Skip introduction button and Escape support. Release the background and return keyboard focus to the main content.
- Bypass for reduced-motion preferences; use session storage only as an optional convenience. A storage failure cannot block entry.
- The footer's Replay introduction button supports the demo. `/?intro=1` forces a home-page replay; `/?intro=0` bypasses it. Reduced motion takes precedence over replay.
- No fabricated percentage, simulated server work, compulsory wait, repeated route loader or sound.

The static cover and controller live in `frontend/public/opening.css`, `frontend/public/opening-init.js` and `frontend/index.html`, so the brand can appear before the application bundle. The cover is hidden by default when scripting is disabled, and has its own release deadline.

## Motion language

| Interaction | Intended behaviour |
|---|---|
| Intro | One brief brand event with a soft split exit. |
| Public section reveals | One 12 px upward reveal with opacity over 480 ms; small 70 ms stagger for the three product introductions. Content is visible by default and becomes visible if the observer fails. |
| Public hero | One subtle 10 px arrival over 600–650 ms. |
| Tool header | A quiet 220 ms opacity arrival; no cascading table animation. |
| Links and actions | Border/colour response over 160–200 ms; directional arrows may move 4 px. |
| Expandable services | Plus rotates into a close mark over 220 ms; content opens with native disclosure behaviour. |
| Financial figures | Stay still. Values, signs, units and missing-data markers remain accurate and selectable. |
| Reduced motion and print | Motion is removed; the intro is skipped and all required content remains available. |

## Demo walkthrough

1. Start at `/?intro=1` and let the introduction finish. Replay once and demonstrate Skip or Escape.
2. Show the Products and Services promise, then the real, dated sample report.
3. Explore the three main products; use the empty company search to find TCS.
4. Open Services, expand a conversation and open its enquiry form without submitting it.
5. Open the product directory and filter by plan.
6. Open a company report and Prism to show that detail and validation warnings remain available inside a quieter visual system.

## Release and further review

### Local verification — 1 November 2026

- Frontend suite: 134 test files and 1,805 tests passed, including seven opening-experience tests.
- TypeScript and production build passed. Existing bundle-size warnings remain.
- In-app browser: verified automatic intro exit, replay, Skip, Escape, returning visits, direct-link bypass and reduced-motion bypass.
- Verified product navigation, company search for TCS, service disclosure, correctly preselected enquiry form and Gold product filtering. No enquiry was submitted.
- Checked the homepage at 390 px and 320 px widths: no horizontal overflow; the primary action is 48 px high.

The changes are local until committed, pushed and deployed through the AWS workflow. Do not mistake the local preview for an updated public site.

Complete actual 200% browser zoom, assistive-technology and cross-browser checks, plus a measured animation-performance pass on a low-end phone. Review About, Contact, plan activation and remaining tool-specific layouts in the next sweep. Avoid a blanket reduction in financial information just to make screens look sparse. The existing design document's CANDIDATE and TO DESIGN labels remain authoritative.

## Product-led revision — 1 November 2026

Feedback on the first minimalist pass: the page felt too plain, and product browsing and plan comparison were visually lost. This revision adds hierarchy and character without reinstating the redundant membership strip.

- Use a bold sans-serif headline with a gold serif emphasis, paired with a navy product stage. The opening brand introduction remains intact.
- Place Explore products and Compare plans as full-size, contrasting actions in the hero and alongside the product collection heading. They lead directly to the directory and Plans page. Keep a single Products disclosure in the marketing header; avoid competing search/help icons there. The duplicate header Explore products action was removed in the navigation correction below.
- Let visitors switch the real Reliance sample between Company snapshot and Five pillars. Use the existing summary endpoint, actual reported values, one full-report link and a visible report date. Do not animate scores or substitute decorative financial data.
- Give the three featured products individual tier accents, a clear name, concise description and visible destination action. Remove the former low-emphasis product footer; do not repeat capability chips or plan-comparison summaries.
- Use an introductory orbit arrival, section reveals and small hover responses. No automatic carousel, continuous animation, new library or forced delay is needed.
- Give service names more editorial prominence and retain the enquiry flow, team and essential disclosure.

These changes apply to the marketing homepage and header. The wider page-specific redesign remains a separate follow-through; this revision does not claim that all tool screens have been rebuilt.

Verification of this revision: all 134 frontend test files / 1,805 tests passed and the production build passed. In-app checks covered snapshot/pillar switching, direct product-directory and Plans navigation, 390 px and 320 px layouts without horizontal overflow, equal 52 px phone actions and dark-mode contrast. The product directory also receives the prominent Plans action and tier-accented catalogue cards so the browsing destination follows the homepage direction.

## Navigation correction — 1 November 2026

- Separate header navigation into `SiteNavigation.tsx` with owned styles in `headerlinks.css`. Remove the `.mt`, `.mg` and `.ddm` coupling that caused page styles to alter mobile disclosures.
- Use one 1,100 px breakpoint. Mobile menus use stacked, labelled native disclosures, nested More categories, 46–52 px destinations and an internal viewport-limited scroll area. Selecting a destination closes the menu, including same-page selections.
- Centre desktop panels inside the full header, with a maximum viewport width and height and internal scrolling. More no longer uses the old negative right offset. Explicit state, outside clicks, focus leaving and Escape control visibility; hover alone cannot leave the menu visually open.
- Keep one Products header entry; retain the prominent product and plan actions in the hero and product collection. The mobile Dashboard shortcut is not repeated inside More.
- Give the account dropdown the same explicit close behaviour and constrain it inside narrow screens.
- Use the existing light-background logo on the light footer and the dark-background logo in dark mode.

In-app checks: expanded Products stacks correctly at 390 px; nested More remains scrollable at 320 px with no page overflow. At 1,100 × 640, More spans x=70–1,030 and y=70–618, with later groups reachable by scrolling and Escape returning to the trigger. The light footer logo is visibly restored. Navigation/overlay regression checks and the frontend suite passed (135 files, 1,810 tests); production build passed.
