#!/usr/bin/env bash
# One-time setup of automatic deploys on THIS server (run once, as the ubuntu user; it uses sudo for the systemd files):
#   REPO_URL=https://github.com/Yusra-Khan532/Financial-Portfolio.git REPO_BRANCH=main REPO_SUBDIR=finlit-platform bash install-auto-deploy.sh
# With no variables it follows the company repository, branch main, folder finlit-platform. Re-running it only updates the settings and the units.
#   Stop it:   bash /opt/finlit/bin/auto-deploy.sh pause     (or: sudo systemctl disable --now finlit-auto-deploy.timer)
#   Look:      bash /opt/finlit/bin/auto-deploy.sh status
set -euo pipefail
FINLIT_HOME="${FINLIT_HOME:-/opt/finlit}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_USER="${SUDO_USER:-$(id -un)}"
[ "$(id -u)" != 0 ] || RUN_USER="${RUN_USER:-ubuntu}"
mkdir -p "$FINLIT_HOME/bin" "$FINLIT_HOME/state" "$FINLIT_HOME/logs"
install -m 755 "$HERE/auto-deploy.sh" "$FINLIT_HOME/bin/auto-deploy.sh"
CONF="$FINLIT_HOME/auto-deploy.conf"
{
  echo "# Written by install-auto-deploy.sh. What the server follows and deploys by itself."
  echo "REPO_URL=${REPO_URL:-https://github.com/Yusra-Khan532/Financial-Portfolio.git}"
  echo "REPO_BRANCH=${REPO_BRANCH:-main}"
  echo "REPO_SUBDIR=${REPO_SUBDIR:-finlit-platform}"
} > "$CONF"
echo "settings written to $CONF:"; sed 's/^/    /' "$CONF"
sudo tee /etc/systemd/system/finlit-auto-deploy.service >/dev/null <<UNIT
[Unit]
Description=FinLit: deploy the newest commit of the followed branch (if there is one)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
User=$RUN_USER
Environment=FINLIT_HOME=$FINLIT_HOME
ExecStart=$FINLIT_HOME/bin/auto-deploy.sh
TimeoutStartSec=45min
Nice=10
UNIT
sudo tee /etc/systemd/system/finlit-auto-deploy.timer >/dev/null <<UNIT
[Unit]
Description=FinLit: look for a new commit every 5 minutes

[Timer]
OnBootSec=4min
OnUnitActiveSec=5min
RandomizedDelaySec=30
Persistent=true

[Install]
WantedBy=timers.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now finlit-auto-deploy.timer
echo
echo "Automatic deploys are ON. A commit merged into the followed branch goes live within about 5-10 minutes."
echo "  see it:  bash $FINLIT_HOME/bin/auto-deploy.sh status        run a check now:  bash $FINLIT_HOME/bin/auto-deploy.sh now"
