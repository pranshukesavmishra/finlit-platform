-- The quarter-results page reads every result declaration of the last ~14 months (kind = 'result', with a symbol) and filters them by
-- announcement date. A partial index on exactly that slice keeps the read an index range scan as the feed grows with news and documents.
CREATE INDEX IF NOT EXISTS feed_results_date_idx ON feed_items (item_date DESC) WHERE kind = 'result' AND symbol IS NOT NULL;
