-- Rows copied from the data provider's IPO calendar carry their own key, so a refresh updates them in place and never touches IPOs
-- that administrators entered by hand (ext_key is empty for those).
ALTER TABLE ipos ADD COLUMN IF NOT EXISTS source text;
ALTER TABLE ipos ADD COLUMN IF NOT EXISTS ext_key text;
CREATE UNIQUE INDEX IF NOT EXISTS ipos_ext_key_idx ON ipos (ext_key) WHERE ext_key IS NOT NULL;
