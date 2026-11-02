-- The macro backdrop per sector (finlit/macro_sectors.py): off for members until the owner switches it on in the Console (the spec asks for a legal check first);
-- administrators always see it.
INSERT INTO feature_flags (name, enabled) VALUES ('macro_sectors', false) ON CONFLICT (name) DO NOTHING;
