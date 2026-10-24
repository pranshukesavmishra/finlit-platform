-- FII / DII cash-market figures can now come from the exchange's own daily report ('nse'), the figure other sites and news quote for the session.
ALTER TABLE flows_daily DROP CONSTRAINT IF EXISTS flows_fii_source;
ALTER TABLE flows_daily DROP CONSTRAINT IF EXISTS flows_dii_source;
ALTER TABLE flows_daily ADD CONSTRAINT flows_fii_source CHECK (fii_source IS NULL OR fii_source IN ('nsdl', 'nse', 'manual'));
ALTER TABLE flows_daily ADD CONSTRAINT flows_dii_source CHECK (dii_source IS NULL OR dii_source IN ('nsdl', 'nse', 'manual'));
