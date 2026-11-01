# FinLit landing page review

Status: **IMPLEMENTED for local review — user approved 1 November 2026**. Original recommendations below are retained; see [implementation and demo checks](demo-implementation.md).

## Updated emphasis

The later [minimalism and motion review](minimalism-and-motion.md) introduces both products and services in the hero. It moves company search into the product section and makes services directly visible in the header. The earlier proposal below is retained as review history.

## Purpose

The current AWS homepage combines a landing page, a product catalogue, a plan comparison and a launch-notification page. Remodel it around one task: **look up a company and understand what FinLit can help the reader examine**.

The public landing page introduces FinLit and demonstrates its value. The signed-in dashboard serves returning users and their followed companies. Give these pages separate roles. Keep services reachable through navigation and a small secondary link; the active research platform should lead the homepage.

The approved implementation leads with company research and retains portfolio reviews and planning services on Services and through the team section. The public domain still showed the earlier services website during the review; confirm the domain cutover separately.

## Proposed section order

| Section | What to show | Main action |
|---|---|---|
| A clear starting point | A short explanation, visible company-name or symbol search and one sample-report link. Use a simple background. | Search companies |
| A real report preview | One labelled example with its company, date, score name and a few actual findings. Match figures to the destination report. | View sample report |
| Three useful paths | Find stocks, understand a company, track companies. Give each one sentence and a destination. Explain access requirements at the destination. | Open the relevant tool |
| How the research works | Find a company, read the findings, inspect the figures and sources. Link to full methodology. | See how scores are calculated |
| The people behind FinLit | A compact founder introduction with the existing real photo, verified credentials, About link and contact route. | Meet the team |
| Plans and footer | Compact tier summaries, key differences, accurate access status and a link to the full comparison. Finish with company, help and legal links. | Compare plans |

Keep a small public header with Research, Markets, Funds and Plans; place company information and services under More. Show one Sign in action in the header. The full workspace navigation belongs inside tools. Exact labels and grouping need joint approval.

## First screen

Proposed headline: **Look up a company. Understand the numbers.**

Supporting text: **Read its financial statements, valuation and risks, with the figures behind each score.**

Search label: **Company name or symbol**. Primary action: **Search companies**. Secondary link: **View a sample company report**.

Start search empty; do not preselect a company for the visitor. A sample can use an explicitly labelled company such as Reliance, but remains a demonstration rather than the visitor's default search.

Keep the preview compact enough to support the main message. Show one relevant assessment rather than every score, chart and model explanation. State whether the sample is live or captured at a particular time. Never imply every company has a complete score if coverage does not support that claim.

## Content decisions

These are recommended removals from the landing page, not deletions of useful tools or research data.

| Current material | Decision | Destination or reason |
|---|---|---|
| All 13 feature cards and their bullet lists | Move | A platform overview or relevant tool pages; keep three task paths on home. |
| Full feature-by-feature pricing matrix | Move | Plans page. Home needs only tier differences and a comparison link. |
| Exact watchlist, filter and alert quotas | Move | Plans and contextual access messages. |
| Hero Notify me action | Remove from hero | Keep notifications beside the specific planned feature or on an updates page. |
| Broad Coming soon catalogue | Move | A roadmap or updates page. Mark planned features clearly where mentioned. |
| Rupee coin, 3D bars, market grid and floating decorations | Remove | One real report preview on a plain surface. |
| Repeated promise marquee | Remove | The headline and demonstration should explain the product. |
| Continuous market ticker on home | Move | Dashboard and Markets. Consider compact static market status only if visitor testing establishes a need. |
| Repeated methodology and how-it-works sections | Combine | One short section linking to full methodology. |
| Speed and universal report-coverage claims | Rewrite | Verifiable availability claims distinguishing listed companies, loaded reports and calculated scores. |
| Repeated plan prompts | Consolidate | One short introduction near the end. |
| Full tool directory and repeated account CTA in footer | Reduce | Compact footer; keep the full directory on an overview page or in product navigation. |
| Detailed portfolio-review and planning service pitch | Move | Services page, reached through navigation and a small secondary link. |
| Actual findings, team identity, methodology and disclosures | Keep | Help readers judge the product and the people responsible for it. |

## Rules for a calmer page

- Give each section one question to answer and at most one primary action. Avoid repeated account prompts before the visitor has seen the product.
- Follow [Design System v1.3](design-system-v1.3.md): navy, ivory, restrained gold, Inter for product data and Source Serif 4 for permitted editorial headings. Preserve semantic financial and status colours.
- Use short paragraphs and actual findings. Do not add invented testimonials, stock team images, unsupported success claims or fabricated returns.
- On a phone, the first screen should explain the product and expose search. No assistant or fixed bar should cover search, sign-in or the sample link.
- Shortening home does not justify removing statements, factor inputs or calculations from company and premium reports. Keep those details easy to reach within their own pages.

## Review and acceptance

Implementation uses company research as the main public promise, a live Reliance sample and the three paths above. Services remain reachable; Basic is free, and Silver/Gold are described as available by request with pricing unannounced, matching the existing activation flow. Validate these choices in the demo; do not add prices or response-time promises without business confirmation.

1. A new visitor can explain what FinLit does and locate search after one brief look.
2. A visitor can open a company or sample without understanding all plans and tools. Retain existing access requirements.
3. Every sample figure matches the report and shows its date and model name.
4. Team, methodology, help and plan information are easy to find.
5. The first phone viewport contains a useful explanation and search entry.
6. Check keyboard focus, both themes, 200% zoom, reduced motion and 320–390 px layouts before sign-off.

These recommendations still need validation with new visitors and experienced researchers. Observe search completion, wrong turns and their understanding of the report.
