-- Discussion forum boards by plan: Basic, Silver and Gold members each have their own board.
-- A post belongs to the board of the plan its author held when writing it; replies stay on the thread's board.
-- Posts written before this migration (none were live) stay on the Basic board.
ALTER TABLE forum_posts ADD COLUMN IF NOT EXISTS plan text NOT NULL DEFAULT 'basic';
DO $$ BEGIN
    ALTER TABLE forum_posts ADD CONSTRAINT forum_posts_plan_chk CHECK (plan IN ('basic', 'silver', 'gold'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
CREATE INDEX IF NOT EXISTS forum_posts_plan_board_idx ON forum_posts (plan, last_activity_at DESC) WHERE thread_id IS NULL AND status = 'visible';
