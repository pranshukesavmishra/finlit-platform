-- Macro & Sector Outlook (finlit/macro_outlook, docs/MACRO-OUTLOOK.md): raw observations with provenance, normalised signals, a versioned sector
-- sensitivity matrix, immutable score snapshots with their contributions, company-to-sector mapping, an audit trail of every configuration change.
-- Every statement is idempotent (the test fixtures drop schema_migrations and replay the folder).

-- ------------------------------------------------------------------------------------------------ model versions (K, coverage rule, bands, indicator settings)
CREATE TABLE IF NOT EXISTS macro_model_configuration (
    model_version     integer      PRIMARY KEY,
    k                 numeric(8,3) NOT NULL CHECK (k > 0),
    signal_scale      numeric(8,3) NOT NULL CHECK (signal_scale > 0),
    min_coverage      numeric(5,4) NOT NULL CHECK (min_coverage BETWEEN 0 AND 1),
    stale_after_hours integer      NOT NULL DEFAULT 48 CHECK (stale_after_hours > 0),
    bands             jsonb        NOT NULL,
    indicators        jsonb        NOT NULL,           -- the indicator settings frozen with this version (normalisation, stale limits, priority, active)
    effective_from    timestamptz  NOT NULL DEFAULT now(),
    active            boolean      NOT NULL DEFAULT false,
    parent_version    integer,
    change_note       text         NOT NULL DEFAULT '',
    created_by        text         NOT NULL DEFAULT 'system',
    created_at        timestamptz  NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS macro_model_one_active ON macro_model_configuration (active) WHERE active;

-- ------------------------------------------------------------------------------------------------ indicators
CREATE TABLE IF NOT EXISTS macro_indicator_defs (
    indicator_code  text PRIMARY KEY,
    name            text    NOT NULL,
    group_code      text    NOT NULL,
    unit            text    NOT NULL,
    frequency       text    NOT NULL,
    source_name     text    NOT NULL,
    source_url      text,
    sort_order      integer NOT NULL DEFAULT 100,
    priority        integer NOT NULL DEFAULT 100,        -- the driver tie-break: lower first
    stale_after_days integer NOT NULL DEFAULT 90,
    valid_min       numeric,
    valid_max       numeric,
    norm            jsonb   NOT NULL DEFAULT '{}'::jsonb,
    reading_note    text,
    active          boolean NOT NULL DEFAULT true,
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- the current reading of each indicator
CREATE TABLE IF NOT EXISTS macro_indicators (
    indicator_code        text PRIMARY KEY REFERENCES macro_indicator_defs (indicator_code),
    value                 numeric(20,6),
    unit                  text NOT NULL,
    observation_date      date,
    publication_date      date,
    pub_date_basis        text,
    source                text NOT NULL,
    source_url            text,
    frequency             text NOT NULL,
    status                text NOT NULL CHECK (status IN ('Available', 'Stale', 'Missing', 'Invalid', 'Revised')),
    detail                text,
    prev_value            numeric(20,6),
    prev_observation_date date,
    revision_number       integer NOT NULL DEFAULT 1,
    retrieved_at          timestamptz NOT NULL DEFAULT now()
);

-- every observation and every revision of it
CREATE TABLE IF NOT EXISTS macro_indicator_history (
    id               bigserial PRIMARY KEY,
    indicator_code   text NOT NULL REFERENCES macro_indicator_defs (indicator_code),
    observation_date date NOT NULL,
    publication_date date NOT NULL,
    pub_date_basis   text NOT NULL,
    value            numeric(20,6) NOT NULL,
    unit             text NOT NULL,
    revision_number  integer NOT NULL DEFAULT 1 CHECK (revision_number >= 1),
    status           text NOT NULL CHECK (status IN ('Available', 'Stale', 'Missing', 'Invalid', 'Revised')),
    source           text NOT NULL,
    source_url       text,
    frequency        text NOT NULL,
    detail           text,
    retrieved_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (indicator_code, observation_date, revision_number)
);
CREATE INDEX IF NOT EXISTS macro_hist_code_obs ON macro_indicator_history (indicator_code, observation_date);
CREATE INDEX IF NOT EXISTS macro_hist_code_pub ON macro_indicator_history (indicator_code, publication_date);

-- ------------------------------------------------------------------------------------------------ sectors and the sensitivity matrix
CREATE TABLE IF NOT EXISTS sector_master (
    id          serial PRIMARY KEY,
    sector_code text    NOT NULL UNIQUE,
    name        text    NOT NULL,
    description text    NOT NULL DEFAULT '',
    sort_order  integer NOT NULL DEFAULT 100,
    active      boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sector_sensitivity (
    id                   bigserial PRIMARY KEY,
    model_version        integer NOT NULL REFERENCES macro_model_configuration (model_version),
    sector_id            integer NOT NULL REFERENCES sector_master (id),
    indicator_code       text    NOT NULL REFERENCES macro_indicator_defs (indicator_code),
    coefficient          numeric(4,2) NOT NULL CHECK (coefficient BETWEEN -1 AND 1),
    weight               numeric(6,3) NOT NULL CHECK (weight > 0),
    critical             boolean NOT NULL DEFAULT false,
    normalisation_method text,
    effective_from       date NOT NULL DEFAULT CURRENT_DATE,
    effective_to         date,
    active               boolean NOT NULL DEFAULT true,
    UNIQUE (model_version, sector_id, indicator_code)
);
CREATE INDEX IF NOT EXISTS sector_sens_sector ON sector_sensitivity (sector_id);
CREATE INDEX IF NOT EXISTS sector_sens_indicator ON sector_sensitivity (indicator_code);

-- ------------------------------------------------------------------------------------------------ company to sector
CREATE TABLE IF NOT EXISTS company_sector_mapping (
    id             bigserial PRIMARY KEY,
    symbol         text    NOT NULL REFERENCES companies (symbol) ON DELETE CASCADE,
    sector_id      integer NOT NULL REFERENCES sector_master (id),
    revenue_weight numeric(7,6) CHECK (revenue_weight IS NULL OR (revenue_weight > 0 AND revenue_weight <= 1)),
    is_primary     boolean NOT NULL DEFAULT false,
    segment_name   text,
    effective_from date    NOT NULL DEFAULT CURRENT_DATE,
    effective_to   date,
    source         text    NOT NULL DEFAULT 'label_map',   -- label_map | admin | segments_auto
    basis_label    text,                                    -- the label or rule that produced it
    created_by     text    NOT NULL DEFAULT 'system',
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS csm_symbol ON company_sector_mapping (symbol);
CREATE INDEX IF NOT EXISTS csm_sector ON company_sector_mapping (sector_id);
CREATE UNIQUE INDEX IF NOT EXISTS csm_one_open_primary ON company_sector_mapping (symbol) WHERE is_primary AND effective_to IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS csm_one_open_row ON company_sector_mapping (symbol, sector_id, (COALESCE(segment_name, ''))) WHERE effective_to IS NULL;

-- a listed company with no primary mapping says why
CREATE TABLE IF NOT EXISTS company_macro_unmapped (
    symbol         text PRIMARY KEY REFERENCES companies (symbol) ON DELETE CASCADE,
    reason         text NOT NULL,
    sector_label   text,
    industry_label text,
    checked_at     timestamptz NOT NULL DEFAULT now()
);

-- the reviewable rules from the exchange's Sector / Industry labels (and named symbols and revenue segments) to the macro sectors
CREATE TABLE IF NOT EXISTS macro_label_map (
    id          serial PRIMARY KEY,
    label_kind  text NOT NULL CHECK (label_kind IN ('sector', 'industry', 'symbol', 'segment')),
    match_type  text NOT NULL CHECK (match_type IN ('exact', 'contains')),
    pattern     text NOT NULL,
    sector_code text NOT NULL REFERENCES sector_master (sector_code),
    priority    integer NOT NULL DEFAULT 50,
    note        text,
    active      boolean NOT NULL DEFAULT true,
    UNIQUE (label_kind, match_type, pattern)
);

-- ------------------------------------------------------------------------------------------------ signals, snapshots, contributions
CREATE TABLE IF NOT EXISTS macro_indicator_signals (
    id               bigserial PRIMARY KEY,
    indicator_code   text    NOT NULL REFERENCES macro_indicator_defs (indicator_code),
    model_version    integer NOT NULL REFERENCES macro_model_configuration (model_version),
    calculation_date date    NOT NULL,
    observation_date date,
    value            numeric(20,6),
    level_signal     numeric(9,6) CHECK (level_signal BETWEEN -1 AND 1),
    momentum_signal  numeric(9,6) CHECK (momentum_signal BETWEEN -1 AND 1),
    final_signal     numeric(9,6) CHECK (final_signal BETWEEN -1 AND 1),
    status           text    NOT NULL,
    coverage         numeric(5,4),
    calculated_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (indicator_code, model_version, calculation_date)
);
CREATE INDEX IF NOT EXISTS macro_sig_date ON macro_indicator_signals (calculation_date);

CREATE TABLE IF NOT EXISTS sector_macro_scores (
    id              bigserial PRIMARY KEY,
    sector_id       integer NOT NULL REFERENCES sector_master (id),
    model_version   integer NOT NULL REFERENCES macro_model_configuration (model_version),
    snapshot_date   date    NOT NULL,
    as_of           timestamptz NOT NULL,
    basis           text    NOT NULL CHECK (basis IN ('live', 'reconstructed')),
    status          text    NOT NULL CHECK (status IN ('ok', 'insufficient_data')),
    score           numeric(5,2) CHECK (score BETWEEN 0 AND 100),
    label           text    NOT NULL,
    weighted_signal numeric(10,6),
    coverage        numeric(5,4) NOT NULL,
    min_coverage    numeric(5,4) NOT NULL,
    critical_missing jsonb  NOT NULL DEFAULT '[]'::jsonb,
    missing         jsonb   NOT NULL DEFAULT '[]'::jsonb,
    top_drivers     jsonb   NOT NULL DEFAULT '[]'::jsonb,
    explanation     jsonb   NOT NULL DEFAULT '{}'::jsonb,
    config          jsonb   NOT NULL DEFAULT '{}'::jsonb,
    inputs_hash     text    NOT NULL,
    calculated_at   timestamptz NOT NULL DEFAULT now(),
    CHECK ((status = 'ok') = (score IS NOT NULL)),
    UNIQUE (sector_id, model_version, basis, snapshot_date, inputs_hash)
);
CREATE INDEX IF NOT EXISTS sms_sector_date ON sector_macro_scores (sector_id, snapshot_date DESC);
CREATE INDEX IF NOT EXISTS sms_date ON sector_macro_scores (snapshot_date);

CREATE TABLE IF NOT EXISTS sector_macro_contributions (
    id               bigserial PRIMARY KEY,
    score_id         bigint  NOT NULL REFERENCES sector_macro_scores (id) ON DELETE RESTRICT,
    indicator_code   text    NOT NULL REFERENCES macro_indicator_defs (indicator_code),
    value            numeric(20,6),
    unit             text,
    observation_date date,
    publication_date date,
    pub_date_basis   text,
    status           text    NOT NULL,
    level_signal     numeric(9,6),
    momentum_signal  numeric(9,6),
    signal           numeric(9,6) CHECK (signal BETWEEN -1 AND 1),
    coefficient      numeric(4,2) NOT NULL,
    weight           numeric(6,3) NOT NULL,
    contribution     numeric(14,8),
    direction        text    NOT NULL,
    critical         boolean NOT NULL DEFAULT false,
    counted          boolean NOT NULL,
    reason           text,
    UNIQUE (score_id, indicator_code)
);
CREATE INDEX IF NOT EXISTS smc_indicator ON sector_macro_contributions (indicator_code);

-- ------------------------------------------------------------------------------------------------ audit trail and run log
CREATE TABLE IF NOT EXISTS macro_audit_log (
    id            bigserial PRIMARY KEY,
    at            timestamptz NOT NULL DEFAULT now(),
    actor         text    NOT NULL,
    action        text    NOT NULL,
    entity        text    NOT NULL,
    entity_key    text    NOT NULL,
    old_value     jsonb,
    new_value     jsonb,
    model_version integer,
    note          text,
    ip            text
);
CREATE INDEX IF NOT EXISTS macro_audit_at ON macro_audit_log (at DESC);

CREATE TABLE IF NOT EXISTS macro_run_log (
    id            bigserial PRIMARY KEY,
    started_at    timestamptz NOT NULL DEFAULT now(),
    finished_at   timestamptz,
    trigger       text    NOT NULL,
    status        text    NOT NULL,
    as_of         date,
    model_version integer,
    fingerprint   text,
    detail        jsonb   NOT NULL DEFAULT '{}'::jsonb,
    error         text
);
CREATE INDEX IF NOT EXISTS macro_run_started ON macro_run_log (started_at DESC);

-- ------------------------------------------------------------------------------------------------ immutability: a published snapshot, its inputs and the audit trail are never changed or removed
CREATE OR REPLACE FUNCTION macro_outlook_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: a published snapshot or audit row is never changed or removed', TG_TABLE_NAME USING ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS sector_macro_scores_immutable ON sector_macro_scores;
CREATE TRIGGER sector_macro_scores_immutable BEFORE UPDATE OR DELETE ON sector_macro_scores FOR EACH ROW EXECUTE FUNCTION macro_outlook_immutable();
DROP TRIGGER IF EXISTS sector_macro_contributions_immutable ON sector_macro_contributions;
CREATE TRIGGER sector_macro_contributions_immutable BEFORE UPDATE OR DELETE ON sector_macro_contributions FOR EACH ROW EXECUTE FUNCTION macro_outlook_immutable();
DROP TRIGGER IF EXISTS macro_audit_log_immutable ON macro_audit_log;
CREATE TRIGGER macro_audit_log_immutable BEFORE UPDATE OR DELETE ON macro_audit_log FOR EACH ROW EXECUTE FUNCTION macro_outlook_immutable();

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON macro_model_configuration, macro_indicator_defs, macro_indicators, macro_indicator_history, sector_master, sector_sensitivity,
            company_sector_mapping, company_macro_unmapped, macro_label_map, macro_indicator_signals, macro_run_log TO finlit_api;
        GRANT SELECT, INSERT ON sector_macro_scores, sector_macro_contributions, macro_audit_log TO finlit_api;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO finlit_api;
    END IF;
END
$$;
