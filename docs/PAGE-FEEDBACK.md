# Raise a Query and Share Feedback (tasks #90 and #56)

**What members see.** Every page banner (`components/PageHeader.tsx`) has a **Raise a Query** button after the page's own buttons. A page without a banner (home, company report, forum) gets the same button in the dock at the bottom right. **Share feedback** is always at the bottom right. Both open one dialog (`components/PageFeedback.tsx`): a query takes a type (question, something is wrong, explain this to me) and at least 10 characters; feedback takes a 1 to 5 star rating, a type and optional words. A visitor who is not signed in must leave an email address; a member is reached through the account.

**What is captured.** The page address (no query string or fragment), the name the page gives itself (`pageNameFor` in `lib/pageHeader.ts`, else its heading or title), and a few short facts: company symbol, title, heading, plan, screen size. The server keeps only those whitelisted keys, cut to length (`finlit/page_feedback.py`).

**Where it goes.** Table `page_feedback` (migration 095). `POST /api/page-feedback` needs our own Origin, the CSRF token for a signed-in member, and is limited per address (20 an hour) and per member (12 an hour, 40 a day); an identical message from the same sender on the same page within a day is stored once.

**The team's side.** `/admin/feedback` (administrators with the two-step sign-in): filter by kind, status and page, see which pages people write about most with the average rating, mark read, resolve with a note. A short email goes to `FEEDBACK_NOTIFY_EMAIL` (falls back to `ADMIN_EMAIL`) when it is set; the message is stored either way, and a mail problem never fails the member's request.

**Server step for the founder.** Add `FEEDBACK_NOTIFY_EMAIL=<team address>` to `/opt/finlit/.env.aws` to be emailed on every new message; without it, read them at `/admin/feedback`.
