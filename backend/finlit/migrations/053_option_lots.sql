-- Option chain (Gold, finlit/options.py): the lot size of every option series in Dhan's instrument file, per underlying and expiry, so the
-- page shows the lot of the expiry being read (lot sizes are revised by the exchanges, and near and far expiries can differ for a while).
-- Replaced as a whole with dhan_instruments on each refresh-instruments run.
--
-- exch           NSE or BSE
-- instrument     OPTIDX (index options) or OPTSTK (stock options)
-- underlying     UNDERLYING_SYMBOL in the file: NIFTY, BANKNIFTY, SENSEX, RELIANCE, ...
-- underlying_id  UNDERLYING_SECURITY_ID in the file (for an index this is the exchange's id, not the IDX_I id the option chain call takes)
-- lot_size       the most common LOT_SIZE of the series; mixed = some contracts of it carry another (adjusted after a corporate action)
CREATE TABLE IF NOT EXISTS dhan_option_lots (
    exch          text    NOT NULL,
    instrument    text    NOT NULL,
    underlying    text    NOT NULL,
    underlying_id text    NOT NULL,
    expiry        date    NOT NULL,
    lot_size      integer NOT NULL,
    mixed         boolean NOT NULL DEFAULT false,
    loaded_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (exch, instrument, underlying, expiry)
);
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        -- the web process reads both to list the F&O stocks and their lot sizes (dhan_instruments had no grant before)
        GRANT SELECT ON dhan_option_lots, dhan_instruments TO finlit_api;
    END IF;
END
$$;
