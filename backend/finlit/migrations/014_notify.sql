-- "Tell me when it launches": addresses people leave on the website. One row per address.
CREATE TABLE IF NOT EXISTS notify_signups (
    email      text        PRIMARY KEY,
    source     text        NOT NULL DEFAULT 'home',
    created_at timestamptz NOT NULL DEFAULT now()
);
