-- The highest close in each company's stored long price history ("all-time high" for the results calendar's price-position filter).
-- Worked out once here from the weekly closes already stored, then kept by `backfill-history` (whole history again) and by `refresh-listing` (a newer price
-- raises it). ath is on the same adjusted basis as the closes; ath_date is the week it was set. Null: no long history held for that company.
ALTER TABLE price_history_long ADD COLUMN IF NOT EXISTS ath real;
ALTER TABLE price_history_long ADD COLUMN IF NOT EXISTS ath_date date;
UPDATE price_history_long h SET ath = m.mx, ath_date = h.dates[m.pos]
FROM (SELECT symbol, max(c) AS mx, (array_positions(closes, max(c)))[1] AS pos FROM price_history_long, unnest(closes) AS c GROUP BY symbol, closes) m
WHERE m.symbol = h.symbol AND h.ath IS NULL AND m.mx IS NOT NULL AND m.mx > 0;
