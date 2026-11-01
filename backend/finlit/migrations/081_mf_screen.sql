-- Mutual Fund Screener (docs/MF-FILTERS.md, finlit/mfscreen/): figures the filter panel needs that are too heavy to work out per request over 14,000 schemes.
-- Filled once a night by `refresh-mf-screen` (registered job "mf-screen"); the API only reads. Every statement is idempotent. Nothing here is a score or a ranking
-- by quality: they are plain figures worked out from month-end NAVs (mf_monthly), the fund facts, the monthly portfolio files and AMFI's category report.
--
--   mf_screen        one row per scheme; every column is x_-prefixed so it never clashes with mf_schemes in the joined list query
--   mf_screen_hold   (family, ISIN) -> share of net assets in the latest portfolio: answers "funds that hold this stock" without scanning holdings JSON
--   mf_cat_flow      per sub-category and month: AMFI's net flow, net assets and folios (last 13 months), for the category-view filters and the flow bars
--   mf_tags          theme / index / factor / global tags with the scheme-name keywords that earn a fund the tag; staff edit this table, the job reads it
CREATE TABLE IF NOT EXISTS mf_screen (
    x_code          integer PRIMARY KEY REFERENCES mf_schemes(code) ON DELETE CASCADE,
    x_run           date NOT NULL,
    x_ckey          text,                -- sub-category key (finlit.mf.classify), e.g. 'mid-cap'
    x_is_etf        boolean NOT NULL DEFAULT false,
    x_tags          text[] NOT NULL DEFAULT '{}',
    -- size and age
    x_launch        date,
    x_age           double precision,                -- years from launch to the newest NAV
    x_house_aum_cr  double precision,    -- the fund house's total (each scheme family counted once), rupees crore
    x_aum_rk        smallint,            -- rank by fund size among the families of the sub-category (1 = largest)
    x_aum_rn        smallint,
    x_aum_share     double precision,                -- fund size as % of its category's net assets in AMFI's monthly report
    x_na_chg        double precision,                -- change of month-end net assets across the stored portfolio months, %
    x_na_months     smallint,
    -- returns against the same sub-category and plan (Growth, active; needs 3 peers with a figure)
    x_ex1y          double precision, x_ex3y double precision, x_ex5y double precision,       -- percentage points over the peer median
    x_rk1           smallint, x_rn1 smallint,             -- rank (1 = highest return) and how many peers have a figure
    x_rk3           smallint, x_rn3 smallint,
    x_rk5           smallint, x_rn5 smallint,
    x_consist       double precision,                -- % of the last 36 months the fund beat the peer median month
    x_n_months      smallint,            -- month-end NAVs held
    -- cost
    x_ter_rel       double precision,                -- TER / peer median TER
    x_ter_gap       double precision,                -- Regular TER minus Direct TER, percentage points
    x_fee_share     double precision,                -- TER / (3-year return + TER), %
    x_exit_pct      double precision,                -- highest exit-load percentage read from the text (0 when nil)
    x_exit_days     integer,             -- longest holding period the load applies to
    x_exit_state    text,                -- nil | read | unread | NULL when the fund house gave no text
    -- risk, all from month-end NAVs
    x_vol1          double precision, x_vol3 double precision,                    -- annualised, % (standard deviation of monthly returns x sqrt 12)
    x_worst_loss    double precision,                -- worst single month of the last 36, as a loss in % (0 when no month fell)
    x_worst12_loss  double precision,                -- worst rolling 12 months of the last 4 years, loss in %
    x_neg_share     double precision,                -- share of the last 36 months with a negative return, %
    x_below_high    double precision,                -- share of the last 36 month-ends below the previous high, %
    x_down_cap      double precision,                -- the fund's average loss in the peers' bad months as % of the peers' average loss
    x_sharpe        double precision,                -- (3-year return - 6%) / volatility, the assumption the head-to-head page uses
    x_worst_less    boolean,             -- worst year smaller than the peer median worst year
    -- portfolio (latest month-end file of the fund's family; NULL for houses with no parsed file)
    x_port_asof     date,
    x_eq_pct        double precision, x_debt_pct double precision, x_cash_pct double precision, x_other_pct double precision,
    x_n_hold        integer,
    x_top10         double precision,
    x_max_hold      double precision,
    x_top_sector    text, x_top_sector_pct double precision,
    x_sectors       jsonb,
    -- category view (AMFI monthly category report)
    x_cf_month      date,
    x_cf_flow       double precision,    -- net flow of the latest month, rupees crore
    x_cf_streak     smallint,            -- 3 = inflow three months running, -3 = outflow three months running, 0 = mixed
    x_cf_aum_mom    double precision, x_cf_aum_yoy double precision, x_cf_folio_mom double precision,
    x_cf_share      double precision                 -- category's share of the industry's net assets, %
);
CREATE INDEX IF NOT EXISTS mf_screen_ckey_idx ON mf_screen (x_ckey);
CREATE INDEX IF NOT EXISTS mf_screen_tags_idx ON mf_screen USING gin (x_tags);

CREATE TABLE IF NOT EXISTS mf_screen_hold (
    fkey    text NOT NULL,
    isin    text NOT NULL,
    pct     double precision NOT NULL,
    as_of   date NOT NULL,
    PRIMARY KEY (fkey, isin)
);
CREATE INDEX IF NOT EXISTS mf_screen_hold_isin_idx ON mf_screen_hold (isin);

CREATE TABLE IF NOT EXISTS mf_cat_flow (
    ckey      text NOT NULL,
    month     date NOT NULL,
    net_flow  double precision,
    aum       double precision,
    folios    bigint,
    PRIMARY KEY (ckey, month)
);

CREATE TABLE IF NOT EXISTS mf_tags (
    tag         text PRIMARY KEY,                  -- stable key, e.g. 'defence'
    kind        text NOT NULL CHECK (kind IN ('theme', 'tech', 'global', 'factor', 'index')),
    label       text NOT NULL,
    keywords    text[] NOT NULL DEFAULT '{}',      -- whole-word phrases matched against the scheme name (lower case, & = and)
    sectors     text[] NOT NULL DEFAULT '{}',      -- rule 2: words found in the sector names of the latest portfolio
    sector_min  double precision NOT NULL DEFAULT 40,          -- rule 2 threshold: % of net assets in those sectors
    tabs        text[] NOT NULL DEFAULT '{equity,hybrid,other,solution}',   -- the tag is only given to schemes in these category tabs
    active      boolean NOT NULL DEFAULT true,
    source      text NOT NULL DEFAULT 'FinLit editorial seed',
    reviewed_on date,                              -- the review date, so the table does not rot (spec F-F)
    updated_at  timestamptz NOT NULL DEFAULT now()
);

INSERT INTO mf_tags (tag, kind, label, keywords, sectors, tabs, reviewed_on) VALUES
 ('defence',      'theme', 'Defence & Aerospace',           '{defence,defense,aerospace}',                         '{aerospace,defense,defence}', '{equity,other}', '2026-11-01'),
 ('banking',      'theme', 'Banking & Financial Services',  '{banking,"banking and financial services",bfsi,"financial services",bank}', '{banks}', '{equity,other}', '2026-11-01'),
 ('nbfc',         'theme', 'NBFC & Insurance',              '{nbfc,insurance}',                                    '{insurance}', '{equity,other}', '2026-11-01'),
 ('it',           'theme', 'IT & Software',                 '{"it fund",it,"information technology",software}',    '{software,"it -","information technology"}', '{equity,other}', '2026-11-01'),
 ('pharma',       'theme', 'Pharma & Healthcare',           '{pharma,healthcare,"health care",health}',            '{pharma,healthcare,hospital}', '{equity,other}', '2026-11-01'),
 ('infra',        'theme', 'Infrastructure & Capital Goods','{infrastructure,infra,"capital goods"}',              '{construction,"capital goods"}', '{equity,other}', '2026-11-01'),
 ('consumption',  'theme', 'Consumption & FMCG',            '{consumption,consumer,fmcg}',                         '{consumer,fmcg}', '{equity,other}', '2026-11-01'),
 ('mfg',          'theme', 'Manufacturing & Make in India', '{manufacturing,"make in india"}',                     '{}', '{equity,other}', '2026-11-01'),
 ('auto',         'theme', 'Auto & EV',                     '{auto,automobile,mobility,"electric vehicle",ev}',    '{automobile,auto}', '{equity,other}', '2026-11-01'),
 ('energy',       'theme', 'Energy & Power',                '{energy,power,oil}',                                  '{power,"oil, gas"}', '{equity,other}', '2026-11-01'),
 ('green',        'theme', 'Renewable & Green',             '{renewable,green,"clean energy"}',                    '{}', '{equity,other}', '2026-11-01'),
 ('psu',          'theme', 'PSU',                           '{psu,"public sector"}',                               '{}', '{equity,other}', '2026-11-01'),
 ('realty',       'theme', 'Real Estate & Housing',         '{"real estate",realty,housing}',                      '{realty,"real estate"}', '{equity,other}', '2026-11-01'),
 ('metals',       'theme', 'Metals & Mining',               '{metal,metals,mining,"metals and mining"}',           '{metals,mining}', '{equity,other}', '2026-11-01'),
 ('chemicals',    'theme', 'Chemicals',                     '{chemical,chemicals}',                                '{chemicals}', '{equity,other}', '2026-11-01'),
 ('railways',     'theme', 'Railways',                      '{railway,railways}',                                  '{}', '{equity,other}', '2026-11-01'),
 ('newage',       'theme', 'Digital & New-age',             '{digital,"new age",innovation,"new economy"}',        '{}', '{equity,other}', '2026-11-01'),
 ('services',     'theme', 'Services',                      '{services}',                                          '{}', '{equity,other}', '2026-11-01'),
 ('esg',          'theme', 'Sustainability & ESG',          '{esg,sustainable,sustainability}',                    '{}', '{equity,other}', '2026-11-01'),
 ('mnc',          'theme', 'MNC',                           '{mnc,multinational}',                                 '{}', '{equity,other}', '2026-11-01'),
 ('logistics',    'theme', 'Transportation & Logistics',    '{transportation,logistics,transport}',                '{transport,logistics}', '{equity,other}', '2026-11-01'),
 ('ai',           'tech',  'AI & Machine Learning',         '{ai,"artificial intelligence","machine learning"}',   '{}', '{equity,other}', '2026-11-01'),
 ('semis',        'tech',  'Semiconductors',                '{semiconductor,semiconductors,chip}',                 '{}', '{equity,other}', '2026-11-01'),
 ('robotics',     'tech',  'Robotics & Automation',         '{robotics,automation}',                               '{}', '{equity,other}', '2026-11-01'),
 ('cloud',        'tech',  'Cloud & Software',              '{cloud}',                                             '{}', '{equity,other}', '2026-11-01'),
 ('cyber',        'tech',  'Cybersecurity',                 '{cybersecurity,cyber}',                               '{}', '{equity,other}', '2026-11-01'),
 ('g_nasdaq',     'global','US Technology (Nasdaq 100)',    '{nasdaq,"us technology"}',                            '{}', '{equity,other}', '2026-11-01'),
 ('g_sp500',      'global','S&P 500',                       '{"s and p 500","sp 500","s p 500"}',                  '{}', '{equity,other}', '2026-11-01'),
 ('g_uslarge',    'global','US Large Cap',                  '{"us large cap","us equity","us bluechip","us blue chip"}', '{}', '{equity,other}', '2026-11-01'),
 ('g_china',      'global','China',                         '{china,"hang seng","hong kong"}',                     '{}', '{equity,other}', '2026-11-01'),
 ('g_europe',     'global','Europe',                        '{europe,european}',                                   '{}', '{equity,other}', '2026-11-01'),
 ('g_em',         'global','Emerging Markets',              '{"emerging markets","emerging market"}',              '{}', '{equity,other}', '2026-11-01'),
 ('g_innov',      'global','Global Innovation',             '{"global innovation","global advantage"}',            '{}', '{equity,other}', '2026-11-01'),
 ('g_health',     'global','Global Healthcare',             '{"global healthcare","global health"}',               '{}', '{equity,other}', '2026-11-01'),
 ('g_clean',      'global','Global Clean Energy',           '{"global clean energy","global climate"}',            '{}', '{equity,other}', '2026-11-01'),
 ('f_momentum',   'factor','Momentum',                      '{momentum}',                                          '{}', '{equity,other}', '2026-11-01'),
 ('f_quality',    'factor','Quality',                       '{quality}',                                           '{}', '{equity,other}', '2026-11-01'),
 ('f_lowvol',     'factor','Low Volatility',                '{"low volatility","low vol"}',                        '{}', '{equity,other}', '2026-11-01'),
 ('f_alpha',      'factor','Alpha',                         '{alpha}',                                             '{}', '{equity,other}', '2026-11-01'),
 ('f_equal',      'factor','Equal Weight',                  '{"equal weight"}',                                    '{}', '{equity,other}', '2026-11-01'),
 ('f_dividend',   'factor','High Dividend',                 '{"high dividend","dividend yield"}',                  '{}', '{equity,other}', '2026-11-01'),
 ('f_multi',      'factor','Multifactor',                   '{multifactor,"multi factor"}',                        '{}', '{equity,other}', '2026-11-01'),
 ('i_nifty50',    'index', 'Nifty 50',                      '{"nifty 50",nifty50}',                                '{}', '{other,equity}', '2026-11-01'),
 ('i_sensex',     'index', 'Sensex',                        '{sensex}',                                            '{}', '{other,equity}', '2026-11-01'),
 ('i_next50',     'index', 'Nifty Next 50',                 '{"nifty next 50","next 50"}',                         '{}', '{other,equity}', '2026-11-01'),
 ('i_nifty100',   'index', 'Nifty 100',                     '{"nifty 100"}',                                       '{}', '{other,equity}', '2026-11-01'),
 ('i_nifty500',   'index', 'Nifty 500',                     '{"nifty 500"}',                                       '{}', '{other,equity}', '2026-11-01'),
 ('i_midcap150',  'index', 'Nifty Midcap 150',              '{"midcap 150"}',                                      '{}', '{other,equity}', '2026-11-01'),
 ('i_smallcap250','index', 'Nifty Smallcap 250',            '{"smallcap 250"}',                                    '{}', '{other,equity}', '2026-11-01'),
 ('i_bank',       'index', 'Nifty Bank',                    '{"nifty bank","bank nifty"}',                         '{}', '{other,equity}', '2026-11-01'),
 ('i_it',         'index', 'Nifty IT',                      '{"nifty it"}',                                        '{}', '{other,equity}', '2026-11-01'),
 ('i_pharma',     'index', 'Nifty Pharma',                  '{"nifty pharma"}',                                    '{}', '{other,equity}', '2026-11-01'),
 ('i_psubank',    'index', 'Nifty PSU Bank',                '{"psu bank"}',                                        '{}', '{other,equity}', '2026-11-01')
ON CONFLICT (tag) DO NOTHING;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT ON mf_screen, mf_screen_hold, mf_cat_flow, mf_tags TO finlit_api;   -- the API only reads; the worker writes (staff edit mf_tags with the admin role)
    END IF;
END
$$;
