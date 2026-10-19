-- Broad sector (Energy, Financials, ...) for the screener's Sector filter.
ALTER TABLE scores ADD COLUMN IF NOT EXISTS macro_sector text;
