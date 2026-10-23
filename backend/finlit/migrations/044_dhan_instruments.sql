-- Dhan's public instrument file (see finlit/dhan.py): every NSE and BSE equity with its ISIN, the exchange's surveillance flag (ASM/GSM),
-- margin-trading eligibility and whether the stock has futures and options. Replaced as a whole on each load, so a delisted scrip leaves.
--
-- exch        NSE or BSE
-- security_id Dhan's id for the scrip: what its price and history calls ask for
-- symbol      the exchange trading symbol (NSE) or the BSE scrip name
-- asm_gsm     N not under surveillance, Y under ASM or GSM, R removed from it; asm_gsm_cat the exchange's stage text
-- mtf_leverage margin-trading leverage Dhan offers (NULL when none)
-- fno / lot_size  the stock has futures contracts, and their lot size
CREATE TABLE IF NOT EXISTS dhan_instruments (
    exch         text NOT NULL,
    security_id  text NOT NULL,
    symbol       text NOT NULL,
    isin         text,
    name         text,
    series       text,
    asm_gsm      text,
    asm_gsm_cat  text,
    mtf_leverage double precision,
    fno          boolean NOT NULL DEFAULT false,
    lot_size     integer,
    loaded_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (exch, security_id)
);
CREATE INDEX IF NOT EXISTS dhan_instruments_isin_idx ON dhan_instruments (isin);
CREATE INDEX IF NOT EXISTS dhan_instruments_symbol_idx ON dhan_instruments (exch, symbol);
