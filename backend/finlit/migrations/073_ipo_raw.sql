-- IPO calendar: the provider's own row for each issue (`raw`, trimmed to a few KB) and the extra facts read from it (`details`: exchange, registrar, lead managers,
-- subscription, allotment/refund dates, issue breakdown, promoter holding, objectives, document links). Both are filled by `refresh-calendars`; NULL for hand-entered issues.
-- Additive: no existing column changes.
ALTER TABLE ipos ADD COLUMN IF NOT EXISTS raw jsonb;
ALTER TABLE ipos ADD COLUMN IF NOT EXISTS details jsonb;
