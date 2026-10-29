-- The few figures the Advanced score screener lists for each company's newest FinLit Prism rating (final, label and status are columns already):
-- the four category scores and the short/long-term technical readings. Kept beside the report so the screener never reads the big report json.
-- Written whenever a report is stored (finlit/prism.py, _save); filled once here for the reports that already exist.
ALTER TABLE prism_reports ADD COLUMN IF NOT EXISTS card jsonb;
UPDATE prism_reports SET card = jsonb_build_object(
    'parts', CASE WHEN status = 'NOT RATED' THEN NULL ELSE report #> '{rating,parts}' END,
    'st', jsonb_build_object('score', report #> '{technicalAssessment,shortTerm,score}', 'rating', report #> '{technicalAssessment,shortTerm,rating}'),
    'lt', jsonb_build_object('score', report #> '{technicalAssessment,longTerm,score}', 'rating', report #> '{technicalAssessment,longTerm,rating}'),
    'confidence', report #> '{rating,confidence}')
WHERE card IS NULL;
