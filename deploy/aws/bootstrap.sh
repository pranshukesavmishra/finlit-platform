#!/usr/bin/env bash
# One-time preparation of a fresh Ubuntu 24.04 (x86_64) EC2 server for FinLit. Run as the normal "ubuntu" user (NOT root); it uses sudo itself:
#   bash bootstrap.sh
# Safe to run again: every step first checks whether it is already done, and says what it did.
# Optional settings (environment variables):
#   ADMIN_IP=203.0.113.7      only this address (or CIDR, e.g. 203.0.113.0/24) may reach SSH (port 22). Default: anyone (fail2ban still guards it).
#   FINLIT_HOME=/opt/finlit   where the site lives
#   SWAP_GB=2                 swapfile size
#   FORCE=1                   skip the safety stop described under ADMIN_IP below
# Does: updates, Docker (official repo) + compose plugin, swapfile (swappiness 10), firewall (22, 80, 443 only), fail2ban, automatic
# security updates, and the /opt/finlit folder. It does not start the site: that is deploy.sh.
set -Eeuo pipefail

FINLIT_HOME="${FINLIT_HOME:-/opt/finlit}"
SWAP_GB="${SWAP_GB:-2}"
ADMIN_IP="${ADMIN_IP:-}"
DONE=()
say()  { printf '\n==> %s\n' "$*"; }
did()  { DONE+=("$*"); printf '    done: %s\n' "$*"; }
skip() { printf '    already ok: %s\n' "$*"; }
die()  { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
trap 'printf "\nbootstrap stopped at line %s. Fix the message above and run it again: it continues where it stopped.\n" "$LINENO" >&2' ERR

[ "$(id -u)" -ne 0 ] || die "run this as the ubuntu user, not root (no sudo in front)."
sudo -n true 2>/dev/null || sudo true || die "this user cannot use sudo."
[ -r /etc/os-release ] && . /etc/os-release
[ "${ID:-}" = ubuntu ] || die "this script is written for Ubuntu (found: ${PRETTY_NAME:-unknown})."
[ "${VERSION_ID:-}" = "24.04" ] || echo "WARNING: tested on Ubuntu 24.04, this is ${VERSION_ID:-?}. Continuing."
[ "$(dpkg --print-architecture)" = amd64 ] || echo "WARNING: written for x86_64; this is $(dpkg --print-architecture)."
ME="$(id -un)"
APT=(sudo env DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=300 -o Dpkg::Options::=--force-confold -y)

if [ -n "$ADMIN_IP" ]; then
  printf '%s' "$ADMIN_IP" | grep -Eq '^([0-9]{1,3}\.){3}[0-9]{1,3}(/[0-9]{1,2})?$' || die "ADMIN_IP must be an IPv4 address like 203.0.113.7 (or a range like 203.0.113.0/24)."
  # Closing SSH to everyone except ADMIN_IP while you are connected from somewhere else would lock you out.
  me_ip="${SSH_CLIENT:-}"; me_ip="${me_ip%% *}"
  if [ -n "${me_ip:-}" ] && [ "${ADMIN_IP%%/*}" != "$me_ip" ] && [ "$ADMIN_IP" = "${ADMIN_IP%%/*}" ] && [ "${FORCE:-0}" != 1 ]; then
    die "you are connected from $me_ip but ADMIN_IP is $ADMIN_IP: the firewall would lock you out. Use your current address (ADMIN_IP=$me_ip), or FORCE=1 if you are sure."
  fi
fi

say "1/8 System update"
sudo apt-get -o DPkg::Lock::Timeout=300 update -y
"${APT[@]}" upgrade
did "apt update + upgrade"

say "2/8 Basic tools"
"${APT[@]}" install ca-certificates curl gnupg git ufw fail2ban unattended-upgrades openssl
did "ca-certificates curl gnupg git ufw fail2ban unattended-upgrades openssl installed"

say "3/8 Docker Engine and the compose plugin (Docker's official apt repository)"
DOCKER_FPR="9DC858229FC7DD38854AE2D88D81803C0EBFCD88"   # Docker's published release-signing key fingerprint
if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
  sudo install -m 0755 -d /etc/apt/keyrings
  tmpkey="$(mktemp)"
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o "$tmpkey"
  got="$(gpg --show-keys --with-colons "$tmpkey" | awk -F: '/^fpr/ {print $10}')"
  printf '%s\n' "$got" | grep -qx "$DOCKER_FPR" || { rm -f "$tmpkey"; die "Docker's signing key does not have the expected fingerprint. Stopping."; }
  sudo install -m 0644 "$tmpkey" /etc/apt/keyrings/docker.asc; rm -f "$tmpkey"
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${UBUNTU_CODENAME:-$VERSION_CODENAME} stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get -o DPkg::Lock::Timeout=300 update -y
  "${APT[@]}" install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  did "Docker $(sudo docker --version | cut -d, -f1) and $(sudo docker compose version)"
else
  skip "Docker $(docker --version | cut -d, -f1) with compose"
fi
sudo systemctl enable --now docker >/dev/null 2>&1 || true
if id -nG "$ME" | tr ' ' '\n' | grep -qx docker; then skip "$ME is in the docker group"; else sudo usermod -aG docker "$ME"; did "added $ME to the docker group (log out and in again to use it)"; fi

say "4/8 Swapfile (${SWAP_GB} GB) and memory behaviour"
if swapon --show=NAME --noheadings | grep -q .; then
  skip "swap already active: $(swapon --show=NAME,SIZE --noheadings | tr '\n' ' ')"
else
  if [ ! -f /swapfile ]; then
    sudo fallocate -l "${SWAP_GB}G" /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=$((SWAP_GB * 1024)) status=none
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile >/dev/null
  fi
  sudo swapon /swapfile
  did "created and enabled /swapfile (${SWAP_GB} GB)"
fi
grep -qE '^/swapfile[[:space:]]' /etc/fstab || { echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null; did "added /swapfile to /etc/fstab (survives reboots)"; }
SYSCTL=/etc/sysctl.d/99-finlit.conf
want=$'vm.swappiness=10\nvm.vfs_cache_pressure=50\n'
if [ "$(sudo cat "$SYSCTL" 2>/dev/null || true)" = "${want%$'\n'}" ] ; then skip "swappiness 10"; else printf '%s' "$want" | sudo tee "$SYSCTL" >/dev/null; sudo sysctl --system >/dev/null; did "vm.swappiness=10 (applied now and at every boot)"; fi

say "5/8 Firewall (ufw): SSH, 80, 443 in; everything else denied"
sudo ufw default deny incoming >/dev/null
sudo ufw default allow outgoing >/dev/null
if [ -n "$ADMIN_IP" ]; then
  sudo ufw allow from "$ADMIN_IP" to any port 22 proto tcp comment 'ssh admin' >/dev/null
  sudo ufw delete allow 22/tcp >/dev/null 2>&1 || true
  did "SSH (22) only from $ADMIN_IP"
elif sudo ufw status | awk '$1 == "22/tcp" && $2 == "ALLOW" && $3 != "Anywhere" {found = 1} END {exit !found}'; then
  skip "SSH already limited to one address by an earlier run; left as it is (to open it to everyone: sudo ufw allow 22/tcp)"
else
  sudo ufw allow 22/tcp comment 'ssh' >/dev/null
  did "SSH (22) open to everyone (set ADMIN_IP=your.ip and rerun to restrict it)"
fi
sudo ufw allow 80/tcp comment 'http' >/dev/null
sudo ufw allow 443/tcp comment 'https' >/dev/null
sudo ufw --force enable >/dev/null
did "ufw enabled: 22, 80, 443 allowed, the rest denied"
echo "    note: Docker publishes only Caddy (80, 443). The database and Redis have no published ports at all."

say "6/8 fail2ban (blocks addresses that keep guessing SSH passwords)"
JAIL=/etc/fail2ban/jail.d/finlit.local
{
  echo "[DEFAULT]"
  [ -z "$ADMIN_IP" ] || echo "ignoreip = 127.0.0.1/8 ::1 $ADMIN_IP"
  echo "bantime = 1h"; echo "findtime = 10m"; echo "maxretry = 5"
  echo; echo "[sshd]"; echo "enabled = true"; echo "backend = systemd"
} | sudo tee "$JAIL" >/dev/null
sudo systemctl enable fail2ban >/dev/null 2>&1 || true
sudo systemctl restart fail2ban
did "fail2ban active for SSH (5 failures in 10 minutes = 1 hour ban)"

say "7/8 Automatic security updates"
printf 'APT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\nAPT::Periodic::AutocleanInterval "7";\n' | sudo tee /etc/apt/apt.conf.d/20auto-upgrades >/dev/null
sudo systemctl enable --now unattended-upgrades >/dev/null 2>&1 || true
did "unattended-upgrades on (Ubuntu security fixes install themselves; the server never reboots by itself)"

say "8/8 Folder $FINLIT_HOME"
sudo install -d -o "$ME" -g "$ME" -m 0755 "$FINLIT_HOME" "$FINLIT_HOME/state"
did "$FINLIT_HOME owned by $ME"

say "Summary"
for line in "${DONE[@]}"; do echo "  - $line"; done
echo
echo "Memory: $(free -m | awk '/^Mem:/ {print $2" MB RAM"} /^Swap:/ {print ", "$2" MB swap"}' | tr -d '\n')"
echo "Next:  1) log out and log in again (so the docker group applies)"
echo "       2) follow the runbook from 'create the settings file': docs/AWS-DEPLOY.md"
