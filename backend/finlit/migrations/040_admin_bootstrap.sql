-- Fingerprint (argon2id hash) of the ADMIN_PASSWORD value that the start script last applied to this account. Each start compares the
-- variable with it: unchanged = leave the account alone (a password changed later under Account is kept); changed = the owner chose a new one.
ALTER TABLE users ADD COLUMN IF NOT EXISTS bootstrap_pw_hash text;
