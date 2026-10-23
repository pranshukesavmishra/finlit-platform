-- Dhan instrument file: the index rows (segment I, instrument INDEX), which Dhan prices under exchange segment IDX_I. Kept apart from
-- dhan_instruments so nothing that reads equities from that table (security_map, the ETF list) can ever pick up an index.
-- finlit/indices.py prices an index from Dhan only when its fixed mapping (our code -> security id and Dhan symbol) is confirmed here.
--
-- exch        NSE or BSE (both are quoted under IDX_I)
-- security_id Dhan's id for the index (13 is NIFTY 50; the 26000 that NIFTY futures name as their underlying is not it)
-- symbol      Dhan's SYMBOL_NAME for the index (NIFTY, BANKNIFTY, SENSEX ...); name its DISPLAY_NAME
CREATE TABLE IF NOT EXISTS dhan_indices (
    exch         text NOT NULL,
    security_id  text NOT NULL,
    symbol       text NOT NULL,
    name         text,
    loaded_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (exch, security_id)
);
