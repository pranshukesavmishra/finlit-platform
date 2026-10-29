# Revenue segments: history and trends

The stock page card "Where the revenue comes from" shows the latest year (strip and tiles), then "How the mix has changed" (stacked bars by fiscal year, rupees or share), "Segment trends" (table) and "Insights". Data: report section `segments`, built by `backend/finlit/normalize/events.py::segments` from FinEdge `/segment-revenue` (annual). Trend logic: `backend/finlit/normalize/segment_trends.py` (pure, tested in `backend/tests/test_segment_trends.py`). Frontend logic: `frontend/src/lib/segmentMix.ts`, view `frontend/src/stock/SegmentMix.tsx`.

## Stored shape
Unchanged keys: `unit`, `periods` (now up to 10 fiscal years instead of 6), `segments` {name: {revenue[], ebit[]}} (crore; `null` = not reported), `latest[]` (only segments reporting in the latest year; small ones folded into "Others"). Changes: `segments` now also holds segments that stopped being reported (all-zero or never-reported segments are dropped), and there is a new `insights` block. Reports stored earlier lack `insights`; the UI then shows the chart and a plain table and no tags or sentences.

## Rules and thresholds
- Share = segment revenue / sum of all segment revenues that year (inter-segment eliminations make the sum differ from reported revenue; the card says so). Percentages come from unrounded numbers; stored to 2 decimals, shown to 1.
- Comparable window: longest run of consecutive fiscal years, ending at the latest year, with positive revenue. A gap, zero or missing fiscal year ends the run.
- CAGR over the window needs 3 or more comparable years, otherwise "Not enough years".
- Trend tag: Discontinued / merged (no positive revenue in the latest year); New (first reported in the last 2 years, not the first year of data, no gap); Not enough history (under 3 years); Growing (CAGR >= +5% and share not down by more than 2 pp); Declining (CAGR <= -2%); Steady (otherwise).
- Margin = EBIT / revenue, change in pp from the window start. Negative EBIT is shown as is.
- Definition changed (flag only, numbers never adjusted): (a) a segment stops being reported in the year another is first reported; (b) a segment's revenue moves 3x or more in one year (over 1% of that year's total) while another segment moves the opposite way by 0.5x to 2x of that amount. Rows whose window contains such a break make no headline sentence. A 3x jump with no offsetting segment is only a caution.
- Sentences (descriptive, at most 5, none under 3 comparable years): fastest growing, largest share gainer, largest share loser (need 1% share at the end; moves under 0.5 pp not reported; "Others" never ranked), decline, segments no longer reported, change in the largest segment's share. Each gives its numbers and period.
- Cautions: "Segment definitions can change when a company reorganises; years before FYxx may not be comparable for ...", big single-year jumps, gaps in reported years.
- Empty states: "Segment history is not available for this company."; "This company reports a single business segment."; under 3 years: no trends drawn.
- Lower plans get the section redacted (`insights` removed with the rest).
- Colours: one per segment from --k1..--k8 by size order, "Others" neutral, beyond 8 segments grouped as "Remaining segments" in the chart.
