-- Commodity prices (finlit/commodities.py).
--
-- dhan_commodity_contracts: the MCX commodity futures (instrument FUTCOM, segment M, quoted under MCX_COMM) from Dhan's instrument file, loaded by
--   refresh-instruments. Security ids change with every contract month, so nothing is hard-coded: the worker resolves each commodity's
--   nearest contracts from this table. LOT_SIZE is 1.0 on every MCX row and is not stored.
--   tick_paise  Dhan's TICK_SIZE (paise: GOLD 100 = Rs 1 per 10 g); upper/lower  the exchange price band in quote units (0 = unknown)
-- commodity_duty: import duty by metal, effective-dated and edited by hand (SQL) when the Budget or a notification changes it. Never in code.
--   checked_on  the day a person last confirmed the rate against the notification; parity is hidden once this is over 120 days old
--   confirmed   false = the rate is an assumption (platinum's AIDC): the page then shows no import parity for that metal
-- mcx_hours / mcx_holidays: when MCX trades (IST), edited by hand when MCX circulars change it (US daylight saving moves the evening close).
-- commodity_snapshots: one international price per commodity per trading day (17:00 New York to 17:00), the base of the day change and later charts.
CREATE TABLE IF NOT EXISTS dhan_commodity_contracts (
    security_id  text PRIMARY KEY,
    symbol       text NOT NULL,
    display_name text NOT NULL,
    expiry       date NOT NULL,
    tick_paise   numeric,
    upper_limit  numeric,
    lower_limit  numeric,
    loaded_at    timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS dhan_commodity_contracts_symbol ON dhan_commodity_contracts (symbol, expiry);

CREATE TABLE IF NOT EXISTS commodity_duty (
    metal          text NOT NULL,
    effective_from date NOT NULL,
    bcd_pct        numeric NOT NULL,
    aidc_pct       numeric NOT NULL,
    gst_pct        numeric NOT NULL,
    checked_on     date NOT NULL,
    confirmed      boolean NOT NULL DEFAULT true,
    source         text,
    PRIMARY KEY (metal, effective_from)
);
-- From 13 May 2026: gold and silver BCD 10% + AIDC 5% (Notifications 15, 16 and 17/2026-Customs of 12 May 2026); GST 3%.
-- Platinum: BCD 10%, AIDC 5.4% is an ASSUMPTION (not confirmed), so it is not confirmed and no platinum parity is shown until a person sets it true.
INSERT INTO commodity_duty (metal, effective_from, bcd_pct, aidc_pct, gst_pct, checked_on, confirmed, source) VALUES
    ('gold',     '2026-05-13', 10, 5,   3, '2026-10-23', true,  'Customs Notifications 15, 16, 17/2026 (12 May 2026)'),
    ('silver',   '2026-05-13', 10, 5,   3, '2026-10-23', true,  'Customs Notifications 15, 16, 17/2026 (12 May 2026)'),
    ('platinum', '2026-05-13', 10, 5.4, 3, '2026-10-23', false, 'ASSUMED: AIDC for platinum bullion not confirmed')
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS mcx_hours (
    from_date date NOT NULL,
    to_date   date NOT NULL,
    open_time time NOT NULL,
    close_time time NOT NULL,
    confirmed boolean NOT NULL DEFAULT true,
    note      text,
    PRIMARY KEY (from_date)
);
-- 9 Mar to 30 Oct 2026: 09:00-23:30 (MCX circular MCX/TRD/068/2026). The evening close moves to 23:55 when US daylight time ends (1 Nov 2026);
-- no circular seen yet, so that row is unconfirmed. The end date of the winter row (US clocks go forward on 14 Mar 2027) is a guess as well.
INSERT INTO mcx_hours (from_date, to_date, open_time, close_time, confirmed, note) VALUES
    ('2026-03-09', '2026-10-30', '09:00', '23:30', true,  'MCX/TRD/068/2026'),
    ('2026-11-02', '2027-03-12', '09:00', '23:55', false, 'expected after US daylight time ends; no circular seen yet')
ON CONFLICT DO NOTHING;

-- kind 'full': closed all day; 'morning': closed until 17:00, then open until the normal close
CREATE TABLE IF NOT EXISTS mcx_holidays (
    day  date PRIMARY KEY,
    kind text NOT NULL DEFAULT 'full' CHECK (kind IN ('full', 'morning')),
    note text
);

CREATE TABLE IF NOT EXISTS commodity_snapshots (
    day    date NOT NULL,
    symbol text NOT NULL,
    kind   text NOT NULL,
    value  numeric NOT NULL,
    PRIMARY KEY (day, symbol, kind)
);
