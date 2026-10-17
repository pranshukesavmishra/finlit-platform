-- The middle plan is now called Silver (was Bronze). Existing Bronze members and requests move over.
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_plan_check;
ALTER TABLE plan_requests DROP CONSTRAINT IF EXISTS plan_requests_plan_check;
UPDATE users SET plan = 'silver' WHERE plan = 'bronze';
UPDATE plan_requests SET plan = 'silver' WHERE plan = 'bronze';
ALTER TABLE users ADD CONSTRAINT users_plan_check CHECK (plan IN ('basic', 'silver', 'gold'));
ALTER TABLE plan_requests ADD CONSTRAINT plan_requests_plan_check CHECK (plan IN ('silver', 'gold'));
