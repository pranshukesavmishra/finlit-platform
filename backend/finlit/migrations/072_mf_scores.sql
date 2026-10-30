-- FinLit Mutual Fund Health Score (finlit/mfscore, docs/mf-score/README.md). Filled once a day by `score-mf`; the public API only reads.
--
-- mf_scores  the latest score of each Growth scheme (Direct and Regular separately) and each ETF: the final score, the four pillars, the label, the status
--            (RATED / PROVISIONAL / NOT RATED and why), the data confidence, flags, the breakdown of every metric (value, state, points, weight) as one jsonb
--            document, the size and kind of the peer set, and the rank and percentile inside the category. One row per fund: a run replaces the day before.
--            IDCW and other options have no row: they inherit the Growth scheme's score when read. A fund that cannot be scored still has a row that says why.
CREATE TABLE IF NOT EXISTS mf_scores (
    key         text PRIMARY KEY,                 -- 'mf:<AMFI scheme code>' or 'etf:<NSE symbol>'
    kind        text NOT NULL,                    -- mf | etf
    code        integer,                          -- AMFI scheme code (mf)
    symbol      text,                             -- NSE symbol (etf)
    plan        text NOT NULL,                    -- Direct | Regular | ETF
    grp         text NOT NULL,                    -- EQ-LARGE ... OT-OTHER
    mtype       text NOT NULL,                    -- Equity | Debt | Hybrid | Solution Oriented | Others
    sub         text NOT NULL,                    -- sub-category key (finlit.mf.classify)
    category    text,                             -- AMFI's category text
    run_date    date NOT NULL,                    -- the day the score was worked out
    nav_date    date,
    final       real,                             -- 0 to 100, NULL when NOT RATED
    raw_final   real,                             -- before the weak-fund cap
    perf        real,
    risk        real,
    cost        real,
    quality     real,
    label       text,                             -- Strong | Healthy | Average | Weak | Poor, NULL when NOT RATED
    status      text NOT NULL,                    -- RATED | PROVISIONAL | NOT RATED
    reason      text,                             -- why PROVISIONAL / NOT RATED
    confidence  real,                             -- share of the score's weight that rested on real data, 0 to 1
    months      integer,                          -- months of month-end NAV history used
    cap         text,                             -- text when the weak-fund cap lowered the score
    flags       text[] NOT NULL DEFAULT '{}',     -- NAV_BREAK, FROZEN_NAV, PROVISIONAL, WEAK_CAP, PILLAR_ALL_N, NEAR_IDENTICAL
    peer_kind   text,                             -- sub | grp | fam: the widest peer set a measure needed
    peer_n      integer,
    rank        integer,                          -- inside the category and plan (inside the tracking family for index funds and ETFs)
    rank_of     integer,
    rank_scope  text,                             -- sub | fam
    percentile  real,                             -- share of the other funds in that scope with a lower score
    breakdown   jsonb NOT NULL DEFAULT '{}'::jsonb,   -- {metrics: [...], reasons: {...}, pillarFlags: {...}}
    model       text NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS mf_scores_group_idx ON mf_scores (grp, plan, final DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS mf_scores_sub_idx ON mf_scores (sub, plan, final DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS mf_scores_code_idx ON mf_scores (code) WHERE code IS NOT NULL;
CREATE INDEX IF NOT EXISTS mf_scores_symbol_idx ON mf_scores (symbol) WHERE symbol IS NOT NULL;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT ON mf_scores TO finlit_api;   -- the API only reads; the worker writes
    END IF;
END
$$;
