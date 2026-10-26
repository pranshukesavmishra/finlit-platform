-- Banks are one FinLit industry, but the Nifty has separate private and public sector bank indices. A stock listed here is ranked in its own sub-group
-- (against that index); banks not listed stay in "Banks" against Nifty Bank. Configuration, not code: add a row to move a stock.
CREATE TABLE IF NOT EXISTS leadership_splits (
    symbol    text PRIMARY KEY,
    industry  text NOT NULL,                -- the FinLit industry it belongs to
    subgroup  text NOT NULL                 -- the peer group it is ranked in (a leadership_benchmarks.industry key)
);
INSERT INTO leadership_splits (symbol, industry, subgroup) VALUES
    ('SBIN', 'Banks', 'Banks - Public Sector'),
    ('PNB', 'Banks', 'Banks - Public Sector'),
    ('UNIONBANK', 'Banks', 'Banks - Public Sector'),
    ('BANKBARODA', 'Banks', 'Banks - Public Sector'),
    ('INDIANB', 'Banks', 'Banks - Public Sector'),
    ('CANBK', 'Banks', 'Banks - Public Sector'),
    ('BANKINDIA', 'Banks', 'Banks - Public Sector'),
    ('MAHABANK', 'Banks', 'Banks - Public Sector'),
    ('IOB', 'Banks', 'Banks - Public Sector'),
    ('UCOBANK', 'Banks', 'Banks - Public Sector'),
    ('CENTRALBK', 'Banks', 'Banks - Public Sector'),
    ('PSB', 'Banks', 'Banks - Public Sector'),
    ('HDFCBANK', 'Banks', 'Banks - Private'),
    ('ICICIBANK', 'Banks', 'Banks - Private'),
    ('KOTAKBANK', 'Banks', 'Banks - Private'),
    ('AXISBANK', 'Banks', 'Banks - Private'),
    ('INDUSINDBK', 'Banks', 'Banks - Private'),
    ('FEDERALBNK', 'Banks', 'Banks - Private'),
    ('IDFCFIRSTB', 'Banks', 'Banks - Private'),
    ('YESBANK', 'Banks', 'Banks - Private'),
    ('BANDHANBNK', 'Banks', 'Banks - Private'),
    ('RBLBANK', 'Banks', 'Banks - Private'),
    ('CUB', 'Banks', 'Banks - Private'),
    ('KARURVYSYA', 'Banks', 'Banks - Private'),
    ('SOUTHBANK', 'Banks', 'Banks - Private'),
    ('DCBBANK', 'Banks', 'Banks - Private'),
    ('CSBBANK', 'Banks', 'Banks - Private'),
    ('TMB', 'Banks', 'Banks - Private'),
    ('DHANBANK', 'Banks', 'Banks - Private'),
    ('J&KBANK', 'Banks', 'Banks - Private'),
    ('JKBANK', 'Banks', 'Banks - Private')
ON CONFLICT (symbol) DO NOTHING;
INSERT INTO leadership_benchmarks (industry, sector_code, sector_name, group_name, group_short) VALUES
    ('Banks - Public Sector', 'NIFPSUBAN', 'Nifty PSU Bank', 'public sector banks', 'PSU bank'),
    ('Banks - Private', 'NIFPRIBAN', 'Nifty Private Bank', 'private banks', 'private bank')
ON CONFLICT (industry) DO NOTHING;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON leadership_splits TO finlit_api;
    END IF;
END
$$;
