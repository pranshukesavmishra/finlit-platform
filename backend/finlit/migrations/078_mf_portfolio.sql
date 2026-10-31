-- My mutual funds (finlit/mfportfolio, docs/MF-PORTFOLIO.md): the funds a member holds, kept in the member's account on the server.
--
-- mf_holdings      one row per member, scheme and folio: the same fund in two folios is two holdings (a blank folio only matches a blank folio).
-- mf_holding_lots  the purchases that make a holding up. A lot is units, the money paid for them (NULL = not known, which is not the same as 0) and an
--                  optional purchase date. A holding's XIRR needs every lot dated and costed; a statement that gives only a closing balance is one undated lot.
-- Both belong to the member: every query filters on user_id, and deleting the account deletes them (ON DELETE CASCADE).
-- Prices, NAVs, returns and scores are NOT stored here: they are read from mf_schemes / mf_scores when the page is asked for, so they are always current.
CREATE TABLE IF NOT EXISTS mf_holdings (
    id         uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    uuid        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    code       integer     NOT NULL,                  -- AMFI scheme code (mf_schemes.code)
    folio      text        NOT NULL DEFAULT '',       -- '' when the file or the member gave none
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, code, folio)
);
CREATE INDEX IF NOT EXISTS mf_holdings_user_idx ON mf_holdings (user_id);

CREATE TABLE IF NOT EXISTS mf_holding_lots (
    id         uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
    holding_id uuid          NOT NULL REFERENCES mf_holdings(id) ON DELETE CASCADE,
    units      numeric(20,4) NOT NULL CHECK (units > 0),
    invested   numeric(20,2) CHECK (invested IS NULL OR invested >= 0),
    bought_on  date,
    created_at timestamptz   NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS mf_holding_lots_holding_idx ON mf_holding_lots (holding_id);

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON mf_holdings, mf_holding_lots TO finlit_api;   -- the member's own data: the API writes it
    END IF;
END
$$;
