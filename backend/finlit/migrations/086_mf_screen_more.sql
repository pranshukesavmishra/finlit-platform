-- Mutual Fund Screener, more figures (docs/MF-FILTERS.md sections 6 and 8): the biggest monthly gain, downside deviation, volatility against the category and the last three
-- calendar-year returns. Filled by the nightly `refresh-mf-screen` job from month-end NAVs we already hold. Idempotent.
ALTER TABLE mf_screen ADD COLUMN IF NOT EXISTS x_up_month double precision;   -- biggest single monthly gain of the last 36, return in % (negative when every month fell)
ALTER TABLE mf_screen ADD COLUMN IF NOT EXISTS x_down_dev   double precision;   -- downside deviation of the last 36 monthly returns (below 0 only) x sqrt 12, %
ALTER TABLE mf_screen ADD COLUMN IF NOT EXISTS x_vol_rel    double precision;   -- 3-year volatility / median 3-year volatility of the same category and plan
ALTER TABLE mf_screen ADD COLUMN IF NOT EXISTS x_cy1        double precision;   -- return of the calendar year before the run's year, % (Dec to Dec month-end NAV)
ALTER TABLE mf_screen ADD COLUMN IF NOT EXISTS x_cy2        double precision;   -- the year before that
ALTER TABLE mf_screen ADD COLUMN IF NOT EXISTS x_cy3        double precision;   -- and the one before that
