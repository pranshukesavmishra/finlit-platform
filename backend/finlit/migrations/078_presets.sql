-- Prebuilt screens on the Advanced score screener (finlit/presets, docs/PRESETS.md).
-- Nothing here touches stored company data: every table is derived by the nightly `refresh-presets` job or kept by the research team.

-- Theme tags for "Emerging tech" (screen 6): one company can carry several sub-themes. Kept by the research team, reviewed every quarter.
CREATE TABLE IF NOT EXISTS theme_tags (
    symbol      text NOT NULL,
    theme       text NOT NULL,
    sub_theme   text NOT NULL,
    added_on    date NOT NULL DEFAULT CURRENT_DATE,
    reviewed_on date,
    PRIMARY KEY (symbol, theme, sub_theme)
);
CREATE INDEX IF NOT EXISTS theme_tags_theme_idx ON theme_tags (theme, sub_theme);

-- The seed list (spec p8-9). Only symbols that exist in `companies` are tagged now; the nightly job adds the rest as listings are mapped
-- (SIFY, SPEL, ASMTEC, CEINFO are on the list but missing from the data today). finlit/presets/seed.py is the source; a test compares the two.
INSERT INTO theme_tags (symbol, theme, sub_theme, added_on)
SELECT v.symbol, 'Emerging tech', v.sub_theme, CURRENT_DATE
FROM (VALUES
    ('DIXON', 'EMS and electronics'),
    ('KAYNES', 'EMS and electronics'),
    ('SYRMA', 'EMS and electronics'),
    ('AMBER', 'EMS and electronics'),
    ('AVALON', 'EMS and electronics'),
    ('CYIENTDLM', 'EMS and electronics'),
    ('CENTUM', 'EMS and electronics'),
    ('PGEL', 'EMS and electronics'),
    ('ELIN', 'EMS and electronics'),
    ('OPTIEMUS', 'EMS and electronics'),
    ('MOSCHIP', 'Semiconductors'),
    ('CGPOWER', 'Semiconductors'),
    ('BEL', 'Defence tech and drones'),
    ('DATAPATTNS', 'Defence tech and drones'),
    ('ASTRAMICRO', 'Defence tech and drones'),
    ('ZENTEC', 'Defence tech and drones'),
    ('PARAS', 'Defence tech and drones'),
    ('IDEAFORGE', 'Defence tech and drones'),
    ('MTARTECH', 'Defence tech and drones'),
    ('NETWEB', 'Data centres and cloud'),
    ('E2E', 'Data centres and cloud'),
    ('ANANTRAJ', 'Data centres and cloud'),
    ('RAILTEL', 'Data centres and cloud'),
    ('TATACOMM', 'Data centres and cloud'),
    ('TATAELXSI', 'AI, data and software products'),
    ('KPITTECH', 'AI, data and software products'),
    ('PERSISTENT', 'AI, data and software products'),
    ('COFORGE', 'AI, data and software products'),
    ('LATENTVIEW', 'AI, data and software products'),
    ('HAPPSTMNDS', 'AI, data and software products'),
    ('AFFLE', 'AI, data and software products'),
    ('TANLA', 'AI, data and software products'),
    ('NEWGEN', 'AI, data and software products'),
    ('INTELLECT', 'AI, data and software products'),
    ('RATEGAIN', 'AI, data and software products'),
    ('ZAGGLE', 'AI, data and software products'),
    ('ROUTE', 'AI, data and software products'),
    ('ETERNAL', 'Digital platforms'),
    ('SWIGGY', 'Digital platforms'),
    ('NYKAA', 'Digital platforms'),
    ('NAUKRI', 'Digital platforms'),
    ('INDIAMART', 'Digital platforms'),
    ('JUSTDIAL', 'Digital platforms'),
    ('CARTRADE', 'Digital platforms'),
    ('FIRSTCRY', 'Digital platforms'),
    ('MEESHO', 'Digital platforms'),
    ('LENSKART', 'Digital platforms'),
    ('URBANCO', 'Digital platforms'),
    ('IXIGO', 'Digital platforms'),
    ('EASEMYTRIP', 'Digital platforms'),
    ('NAZARA', 'Digital platforms'),
    ('TBOTEK', 'Digital platforms'),
    ('DELHIVERY', 'Digital platforms'),
    ('BLACKBUCK', 'Digital platforms'),
    ('PAYTM', 'Fintech and market infrastructure'),
    ('POLICYBZR', 'Fintech and market infrastructure'),
    ('BSE', 'Fintech and market infrastructure'),
    ('MCX', 'Fintech and market infrastructure'),
    ('CDSL', 'Fintech and market infrastructure'),
    ('CAMS', 'Fintech and market infrastructure'),
    ('KFINTECH', 'Fintech and market infrastructure'),
    ('ANGELONE', 'Fintech and market infrastructure'),
    ('GODIGIT', 'Fintech and market infrastructure'),
    ('ATHERENERG', 'EV and batteries'),
    ('OLAELEC', 'EV and batteries'),
    ('OLECTRA', 'EV and batteries'),
    ('JBMA', 'EV and batteries'),
    ('GREAVESCOT', 'EV and batteries'),
    ('SONACOMS', 'EV and batteries'),
    ('EXIDEIND', 'EV and batteries'),
    ('ARE&M', 'EV and batteries'),
    ('HBLENGINE', 'EV and batteries'),
    ('WAAREEENER', 'Solar and clean-energy manufacturing'),
    ('PREMIERENE', 'Solar and clean-energy manufacturing'),
    ('WEBELSOLAR', 'Solar and clean-energy manufacturing'),
    ('INOXWIND', 'Solar and clean-energy manufacturing'),
    ('SUZLON', 'Solar and clean-energy manufacturing'),
    ('KPIGREEN', 'Solar and clean-energy manufacturing'),
    ('STLTECH', 'Telecom tech (5G, fibre)'),
    ('HFCL', 'Telecom tech (5G, fibre)'),
    ('TEJASNET', 'Telecom tech (5G, fibre)'),
    ('ITI', 'Telecom tech (5G, fibre)'),
    ('VINDHYATEL', 'Telecom tech (5G, fibre)'),
    ('SIFY', 'Data centres and cloud'),
    ('SPEL', 'Semiconductors'),
    ('ASMTEC', 'EMS and electronics'),
    ('CEINFO', 'Digital platforms')
) AS v(symbol, sub_theme)
WHERE EXISTS (SELECT 1 FROM companies c WHERE c.symbol = v.symbol)
ON CONFLICT DO NOTHING;

-- The cleaned industry of every company: DERIVED from the stored raw industry (never rewritten there) by finlit/presets/industry.py, rebuilt nightly.
-- `industry_override` is the research team's hand-made list (for example moving a company off a generic industry onto the exchange's specific one);
-- an override always wins over the derived name.
CREATE TABLE IF NOT EXISTS industry_clean (
    symbol     text PRIMARY KEY,
    raw        text,
    clean      text,
    rule       text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS industry_clean_clean_idx ON industry_clean (clean);
CREATE TABLE IF NOT EXISTS industry_override (
    symbol   text PRIMARY KEY,
    industry text NOT NULL,
    note     text,
    set_on   date NOT NULL DEFAULT CURRENT_DATE
);

-- Nightly fields (spec p16): the momentum and growth scores of every company in the universe (market cap 1,000 Cr or more).
CREATE TABLE IF NOT EXISTS preset_scores (
    symbol         text PRIMARY KEY,
    as_of          date NOT NULL,
    momentum_score real,
    growth_score   real,
    updated_at     timestamptz NOT NULL DEFAULT now()
);

-- Breadth per industry and for the whole market (spec p10): B50 and B200 (share above the 50- and 200-day average), R3 (median 3-month return),
-- NH (share within 10% of the 52-week high), RS3 (industry R3 minus market R3). 60 sessions are kept. `industry` = '*' is the market itself.
CREATE TABLE IF NOT EXISTS industry_breadth_daily (
    as_of    date NOT NULL,
    industry text NOT NULL,
    members  integer NOT NULL,
    b50      real,
    b200     real,
    r3       real,
    nh       real,
    rs3      real,
    in_play  boolean NOT NULL DEFAULT false,
    state    text,
    PRIMARY KEY (as_of, industry)
);

-- The cached answer of every screen for every chip set: one list for every user, written by the nightly job (or by the first request after a deploy).
CREATE TABLE IF NOT EXISTS preset_results (
    preset_id   text NOT NULL,
    chips       text NOT NULL,
    registry    integer NOT NULL,
    as_of       date NOT NULL,
    body        jsonb NOT NULL,
    computed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (preset_id, chips, registry)
);

-- Small facts of the job: outlier caps, last run summary.
CREATE TABLE IF NOT EXISTS preset_meta (
    key        text PRIMARY KEY,
    value      jsonb NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Usage, for the 60-day review (spec p16: "after 60 days drop or rework screens few people open"). Counts per day, screen, event and plan only:
-- no user id, no IP, no query text.
CREATE TABLE IF NOT EXISTS preset_usage (
    day       date NOT NULL,
    preset_id text NOT NULL,
    event     text NOT NULL CHECK (event IN ('open', 'export')),
    plan      text NOT NULL DEFAULT 'gold',
    n         integer NOT NULL DEFAULT 0,
    PRIMARY KEY (day, preset_id, event, plan)
);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON theme_tags, industry_clean, industry_override, preset_scores, industry_breadth_daily, preset_results, preset_meta, preset_usage TO finlit_api;
    END IF;
END
$$;
