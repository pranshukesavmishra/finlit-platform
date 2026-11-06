# FinLit platform: working rules for Claude

## The founder's five-step method (apply to EVERY issue, one issue at a time)

The founder (Pranshu) sends 4-5 issues at a time. Solve them one at a time, with full effort on each, in these five steps:

1. **Analyze.** Find the real root cause, not the symptom. Think about the nearby problems that share the cause or will show up next, and include them.
2. **Plan the best fix.** Decide how to solve it properly and how to do it in an upgraded way, not just a patch.
3. **Implement.** Make the change. Touch only what the issue needs; never change an unrelated layout or feature.
4. **Test.** Prove it works: run the tests, look at UI changes in a real browser (desktop and phone width, light and dark), and confirm that the problem and the predicted nearby problems are all solved.
5. **Upgrade.** Once it works, improve it further where it clearly helps, and say what was added.

Report each issue in one message: cause, what changed, test results, what is still open. Give server or browser steps ONE at a time, say exactly where each runs (PowerShell on the PC, Git Bash on the PC, or the server window whose prompt starts `ubuntu@ip-`), and ask for a screenshot. For older issues the founder was not satisfied with, ask what looked wrong (a screenshot) before deciding the fix.

## Project facts

- Live site: https://finlitventures.com, https://www.finlitventures.com and https://app.finlitventures.com (AWS EC2 Sydney, 54.253.190.17; Docker Compose + Caddy in `deploy/aws/`).
- Source of truth: company repo `Yusra-Khan532/Financial-Portfolio`, folder `finlit-platform/` (this folder). Its `main` is deployed automatically by the server about every 5 minutes. Delivery from the founder's repo `pranshukesavmishra/finlit-platform` goes through `.github/workflows/sync-to-company.yml` as a pull request the founder merges with "Create a merge commit". Never edit the legacy root folders of the company repo.
- Background jobs: `docs/JOBS.md` (job supervisor; scheduled jobs are never switched off). Status: `/api/jobs/status`.
- Handover and open items: `docs/HANDOVER-PROMPT.md`.

## Rules that never change

- Accuracy first: numbers correct, current, never missing when data exists; every blank shows its reason; never guess.
- Wording: describe, never advise. Never buy / sell / hold / reduce / avoid / accumulate / target / "best" / multibagger / top pick. Keep the disclaimer "Describes the company's financial health from its filings and prices; not a recommendation. Information only, not investment advice."
- Everything stays free.
- Secrets (API keys, tokens, passwords) only in the server's `/opt/finlit/.env.aws` or GitHub/host dashboards; never in chat or in the repo.
- Deliver as you go (the founder said so on 5 Nov 2026): after the tests pass, commit, push and deliver without waiting for approval. Tell him what shipped and what he must do. No model names in commits or code.
- Always give the direct clickable link yourself (the founder said so on 6 Nov 2026): every time something is pushed, look up the new sync pull request on `Yusra-Khan532/Financial-Portfolio` and put its full URL in the message, plus links to the live pages to check. Never make him ask for a link.
