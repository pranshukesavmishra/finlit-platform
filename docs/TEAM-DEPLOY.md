# How the team changes and deploys the FinLit site

## 1. Where to make changes (important)
The company repository `Yusra-Khan532/Financial-Portfolio` holds TWO things:
- the **old app** in its root folders (`frontend/`, `backend/`, ...): the server does NOT run this;
- the **new FinLit site** in the folder **`finlit-platform/`**: this is what runs on the AWS server (and on Render).
Make every change for the live site INSIDE `finlit-platform/` (its own `frontend/` (React + TypeScript + Vite), `backend/` (research API), `site-api/` (Prism model and chat)). A change in the old root `frontend/` (for example the "light theme foundation" commit `413f7b5`) never reaches the live site: port it into `finlit-platform/frontend/` instead. Do not put secrets in the repository.

## 2. How a change becomes live
1. Branch from `main`, change files inside `finlit-platform/`, run the checks in `finlit-platform/scripts/preflight.sh` (or at least `npx vitest run` and `npx tsc --noEmit` in `finlit-platform/frontend`, and the backend pytest).
2. Open a pull request to `main`; a second person reviews; merge.
3. **Deploy** (needs access to the server; see section 3). On the server, in `/opt/finlit`:
   `bash src/deploy/aws/deploy.sh`
   This fetches `main` of the company repository, rebuilds, restarts (the site may answer 503 for up to a minute), waits until `/api/health` is ok and prints the commit it runs. The kit's defaults are the company repository, branch `main`, folder `finlit-platform`.
4. Check: `bash src/scripts/smoke.sh http://54.253.190.17` and open the site. If something is wrong: `bash src/deploy/aws/deploy.sh rollback` (goes back to the previous build; run again to go forward).
Other commands: `status`, `logs [service]`, `restart`, `backup`, `backups`.

## 3. Giving a team member deploy access
The server accepts SSH only with a key and only from allowed addresses.
1. The team member creates their own key pair on their computer (`ssh-keygen -t ed25519`) and sends the **public** key (the `.pub` file; never the private one).
2. The server owner appends that public key as one line to `/home/ubuntu/.ssh/authorized_keys` on the server (log in, `nano ~/.ssh/authorized_keys`, paste, save).
3. The owner adds the member's public IP address to the EC2 security group rule for SSH (port 22), or opens the rule wider (fail2ban is on).
4. The member logs in with `ssh -i <their key> ubuntu@54.253.190.17` and runs the deploy command above. Remove their line from `authorized_keys` when they leave.
Secrets (FinEdge key, Mongo URL, passwords) live only in `/opt/finlit/.env.aws` on the server; a deployer never needs to see or copy them.

## 4. Bringing work from `pranshukesavmishra/finlit-platform` into the company repository
`scripts/sync-to-company.sh` (dry run) and `scripts/sync-to-company.sh --push` put everything done since the last delivery onto a new branch `pranshu-sync-<sha>` of the company repository, inside `finlit-platform/`, as a three-way patch: changes the team made inside that folder are kept, a conflict stops the script and nothing is pushed. Then open a pull request from that branch and merge it. (`scripts/export-to-company.sh` is only for the very first delivery.)

## 5. Automatic deploys (merge to `main` and the site updates by itself)
A timer on the server (`deploy/aws/auto-deploy.sh`, installed by `deploy/aws/install-auto-deploy.sh`) looks at the company repository every 5 minutes. When `main` has a new commit it:
1. takes a database backup,
2. runs the normal deploy (`deploy.sh`: fetch, rebuild, restart, wait for `/api/health`),
3. if the new version is not healthy, goes back to the previous build by itself and does NOT retry that commit (it waits for the next new commit),
4. writes everything to `/opt/finlit/logs/auto-deploy.log`.
So the team only merges a pull request to `main`; the change is live within about 5-10 minutes (the site may answer 503 for up to a minute while it restarts). Database changes (migrations) move forward and are not undone by a rollback; the nightly and pre-deploy backups exist for that.

**Install once, on the server** (after the company repository's `main` contains the kit, i.e. after the sync pull request is merged):
`bash /opt/finlit/src/finlit-platform/deploy/aws/install-auto-deploy.sh`
(the settings default to the company repository, branch `main`, folder `finlit-platform`; override with REPO_URL / REPO_BRANCH / REPO_SUBDIR).
Look: `bash /opt/finlit/bin/auto-deploy.sh status`. Check now: `... now`. Stop: `... pause` (and `... resume`). Remove: `sudo systemctl disable --now finlit-auto-deploy.timer`.
Private repository: put a read-only token alone in `/opt/finlit/git-token` (`chmod 600`).

**Protect `main` on GitHub** (repository Settings, Branches, rule for `main`: require a pull request and at least one approval, no direct pushes). Whatever lands on `main` runs on the server, so this review step is the safety gate. Do not give the server a token that can push.
