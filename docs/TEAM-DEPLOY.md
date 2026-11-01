# How the team changes and deploys the FinLit site

## 0. Source of truth

The AWS server runs `finlit-platform/` from `Yusra-Khan532/Financial-Portfolio`, branch `main`. The retired root app and alternate hosting configurations have been removed.

## 1. Where to make changes

Make application changes inside `finlit-platform/`: `frontend/` for the React website, `backend/` for the research API and `site-api/backend/` for CMS, forms, chat and the premium model. Repository-level CI and Dependabot settings live in the root `.github/` and target this folder. Secrets remain outside the clone.

## 2. How a change becomes live
1. Branch from `main`, change files inside `finlit-platform/`, run the checks in `finlit-platform/scripts/preflight.sh` (or at least `npx vitest run` and `npx tsc --noEmit` in `finlit-platform/frontend`, and the backend pytest).
2. Open a pull request to `main`; a second person reviews; merge.
3. **Deploy** (needs access to the server; see section 3). On the server, in `/opt/finlit`:
   `bash src/finlit-platform/deploy/aws/deploy.sh`
   This fetches `main` of the company repository, rebuilds, restarts (the site may answer 503 for up to a minute), waits until `/api/health` is ok and prints the commit it runs. The kit's defaults are the company repository, branch `main`, folder `finlit-platform`.
4. Check: `bash src/finlit-platform/scripts/smoke.sh http://54.253.190.17` and open the site. If something is wrong: `bash src/finlit-platform/deploy/aws/deploy.sh rollback` (goes back to the previous build; run again to go forward).
Other commands: `status`, `logs [service]`, `restart`, `backup`, `backups`.

## 3. Giving a team member deploy access
The server accepts SSH only with a key and only from allowed addresses.
1. The team member creates their own key pair on their computer (`ssh-keygen -t ed25519`) and sends the **public** key (the `.pub` file; never the private one).
2. The server owner appends that public key as one line to `/home/ubuntu/.ssh/authorized_keys` on the server (log in, `nano ~/.ssh/authorized_keys`, paste, save).
3. The owner adds the member's public IP address to the EC2 security group rule for SSH (port 22), or opens the rule wider (fail2ban is on).
4. The member logs in with `ssh -i <their key> ubuntu@54.253.190.17` and runs the deploy command above. Remove their line from `authorized_keys` when they leave.
Secrets (FinEdge key, Mongo URL, passwords) live only in `/opt/finlit/.env.aws` on the server; a deployer never needs to see or copy them.

## 4. Contributing changes

Open pull requests directly in the company repository. Run `bash finlit-platform/scripts/preflight.sh` from the repository root. The GitHub CI checks use the same platform paths; separate export/sync workflows from the former standalone repository have been removed.

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
