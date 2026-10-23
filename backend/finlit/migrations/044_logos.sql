-- Company and fund-house logos for search results and lists. Each logo is the icon the company publishes on its OWN website
-- (apple-touch-icon or a large favicon), fetched once by `refresh-logos` with an identifying user agent, robots.txt respected,
-- checked (real PNG/ICO/JPEG/WebP, square-ish, 32-512 px, at most 16 KB; SVG is never accepted) and served from our own origin.
-- A site that refuses or challenges us is marked 'blocked' and the initials avatar is shown instead; nothing goes around a block.
ALTER TABLE companies ADD COLUMN IF NOT EXISTS website text;

CREATE TABLE IF NOT EXISTS logos (
    owner_kind  text        NOT NULL CHECK (owner_kind IN ('stock', 'amc')),
    owner_key   text        NOT NULL,              -- stock symbol, or mf.amc_key() of the fund house
    domain      text,
    status      text        NOT NULL CHECK (status IN ('ok', 'none', 'blocked', 'rejected', 'manual')),
    mime        text,
    width       smallint,
    height      smallint,
    sha8        text,                              -- first 16 hex digits of the image's SHA-256: the public, immutable file name
    bytes       bytea,
    source_url  text,
    note        text,                              -- why there is no logo (shown in the admin console)
    fetched_at  timestamptz NOT NULL DEFAULT now(),
    next_try_at timestamptz,
    PRIMARY KEY (owner_kind, owner_key)
);
CREATE INDEX IF NOT EXISTS logos_sha8_idx ON logos (sha8) WHERE sha8 IS NOT NULL;   -- not unique: group companies often share one logo

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'finlit_api') THEN
        GRANT SELECT, INSERT, UPDATE, DELETE ON logos TO finlit_api;
    END IF;
END
$$;
