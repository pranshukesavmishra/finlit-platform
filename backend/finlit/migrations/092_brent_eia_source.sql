-- The Macro Outlook 'Brent crude' indicator now reads the U.S. EIA daily Brent series (stored by the macro job) instead of a vendor feed that is not connected.
-- Seeds never overwrite an existing definition, so the source text of the already-stored row is brought in line here. Idempotent.
UPDATE macro_indicator_defs
   SET source_name = 'U.S. EIA',
       source_url = 'https://www.eia.gov/dnav/pet/hist/RBRTED.htm',
       reading_note = 'U.S. EIA daily Europe Brent spot price, published with a lag of 1-2 business days; a commodity-price vendor feed is used instead when one is connected and newer.'
 WHERE indicator_code = 'BRENT' AND source_name <> 'U.S. EIA';

-- Copper, aluminium and natural gas read the World Bank Pink Sheet (monthly averages, CC BY 4.0): source text, frequency, staleness limit and the minimum
-- number of monthly readings in the year, for rows not already changed. The model version itself is upgraded by the outlook run (a new version, never an edit).
UPDATE macro_indicator_defs
   SET source_name = 'World Bank Commodity Price Data (Pink Sheet), CC BY 4.0',
       source_url = 'https://www.worldbank.org/en/research/commodity-markets',
       frequency = 'Monthly',
       stale_after_days = 75,
       norm = jsonb_set(norm, '{level,min_points}', '6'::jsonb),
       reading_note = 'World Bank monthly average (a daily vendor feed is used instead when one is connected and newer).'
 WHERE indicator_code IN ('COPPER', 'ALUMINIUM', 'NATGAS') AND source_name NOT LIKE 'World Bank%';
