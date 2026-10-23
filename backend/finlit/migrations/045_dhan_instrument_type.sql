-- Dhan instrument file: the exchange's instrument type (ES share, ETF, MF closed-ended fund unit, ...) and its own name for the scrip,
-- so ETFs can be told apart from listed fund units that share the INF ISIN prefix (finlit/etf.py takes type ETF, series EQ).
ALTER TABLE dhan_instruments ADD COLUMN IF NOT EXISTS inst_type text;
ALTER TABLE dhan_instruments ADD COLUMN IF NOT EXISTS exch_name text;
CREATE INDEX IF NOT EXISTS dhan_instruments_type_idx ON dhan_instruments (exch, inst_type);
