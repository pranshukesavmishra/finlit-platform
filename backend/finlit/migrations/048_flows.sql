-- FII / DII institutional flows (finlit/flows.py, worker refresh-flows). One row per trading day for the cash market, each side with its own
-- source ('nsdl' = NSDL's FPI Monitor, 'manual' = typed in by an administrator from the exchange's published report; manual always wins and
-- the nightly job never overwrites it). Amounts are Rs crore as published, NULL when no source publishes them. fpi_* is NSDL's all-asset
-- view of FPI flows for the same day. flows_oi keeps participant-wise open interest (contracts), flows_index the Nifty 50 closes used for
-- the correlation, flows_meta the last published payload (so the page survives a Redis flush) and each step's last run.
CREATE TABLE IF NOT EXISTS flows_daily (
    d              date             PRIMARY KEY,
    fii_buy        double precision,
    fii_sell       double precision,
    fii_net        double precision,
    fii_source     text,
    dii_buy        double precision,
    dii_sell       double precision,
    dii_net        double precision,
    dii_source     text,
    fpi_equity_net double precision,
    fpi_debt_net   double precision,
    fpi_hybrid_net double precision,
    fpi_total_net  double precision,
    fpi_usd_mn     double precision,
    fpi_inr        double precision,
    updated_at     timestamptz      NOT NULL DEFAULT now(),
    CONSTRAINT flows_fii_source CHECK (fii_source IS NULL OR fii_source IN ('nsdl', 'manual')),
    CONSTRAINT flows_dii_source CHECK (dii_source IS NULL OR dii_source IN ('nsdl', 'manual'))
);
CREATE TABLE IF NOT EXISTS flows_oi (
    d           date NOT NULL,
    participant text NOT NULL,
    instrument  text NOT NULL,
    long_       bigint,
    short_      bigint,
    PRIMARY KEY (d, participant, instrument)
);
CREATE TABLE IF NOT EXISTS flows_index (
    code  text             NOT NULL,
    d     date             NOT NULL,
    close double precision NOT NULL,
    PRIMARY KEY (code, d)
);
CREATE TABLE IF NOT EXISTS flows_meta (
    key        text        PRIMARY KEY,
    body       jsonb       NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON flows_daily, flows_oi, flows_index, flows_meta TO finlit_api;
    END IF;
END
$$;
