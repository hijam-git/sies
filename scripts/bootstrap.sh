#!/usr/bin/env bash
# =============================================================================
# SIES — server onboarding. The FIRST script. Run it once, on a box with nothing.
#
#   sudo bash scripts/bootstrap.sh
#   sudo bash scripts/bootstrap.sh --repo https://github.com/you/sies.git
#   sudo bash scripts/bootstrap.sh --dir /opt/sies --user sies --audit
#
#   --audit    report what would change and change nothing
#   --no-swap  skip setup_swap.sh (a box that already has swap elsewhere)
#
# What it does:
#   1. apt update/upgrade, timezone Asia/Dhaka, unattended-upgrades
#   2. Docker CE + the compose plugin
#   3. ufw: 22, 80, 443 in; everything else denied
#   4. fail2ban
#   5. swap, via setup_swap.sh
#   6. the unprivileged deploy user, in the docker group
#   7. the repository, cloned AS that user
#   8. the directory layout (backups, logs) with the right ownership
#
# It deliberately does NOT deploy and does NOT write secrets. Those need your
# credentials and your decisions. It ends by telling you the two commands left.
#
# This file is standalone by design: scp it to a bare server and run it. That is
# the chicken-and-egg it exists to break — everything else lives in the repo it
# clones.
#
# SAFE TO RE-RUN. Every step checks the current state first and says "ok" rather
# than doing the work again. Nothing here is destructive.
# =============================================================================
set -euo pipefail

REPO="${SIES_REPO:-git@github.com:hijam-git/sies.git}"
DIR="${SIES_DIR:-/opt/sies}"
APP_USER="${SIES_USER:-sies}"
DO_SWAP=1
AUDIT=0

while [ $# -gt 0 ]; do
  case "$1" in
    --repo)    REPO="$2"; shift 2 ;;
    --dir)     DIR="$2";  shift 2 ;;
    --user)    APP_USER="$2"; shift 2 ;;
    --no-swap) DO_SWAP=0; shift ;;
    --audit)   AUDIT=1; shift ;;
    -h|--help) sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1  (try --help)" >&2; exit 1 ;;
  esac
done

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
PASS=0; FIXED=0; TODO=0; FAIL=0

step()  { printf '\n%b== %s%b\n' "${BOLD}${BLUE}" "$1" "$NC"; }
ok()    { printf '  %bok%b    %s\n'    "$GREEN"  "$NC" "$1"; PASS=$((PASS+1)); }
fixed() { printf '  %bfixed%b %s\n'    "$GREEN"  "$NC" "$1"; FIXED=$((FIXED+1)); }
todo()  { printf '  %btodo%b  %s\n'    "$YELLOW" "$NC" "$1"; TODO=$((TODO+1)); }
warn()  { printf '  %bwarn%b  %s\n'    "$YELLOW" "$NC" "$1"; }
bad()   { printf '  %bFAIL%b  %s\n'    "$RED"    "$NC" "$1"; FAIL=$((FAIL+1)); }
info()  { printf '  %b->%b    %s\n'    "$CYAN"   "$NC" "$1"; }
die()   { printf '  %bERROR%b %s\n'    "$RED"    "$NC" "$1" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run as root:  sudo bash $0 $*"

# In audit mode every mutating helper becomes a no-op that reports instead. One
# switch, so there is no path through this script that changes something in
# audit mode by accident.
apply() {
  if [ "$AUDIT" = 1 ]; then return 1; fi
  return 0
}

if [ "$AUDIT" = 1 ]; then
  printf '%bSIES bootstrap%b  %s  (AUDIT — nothing will be changed)\n' "$BOLD" "$NC" "$DIR"
else
  printf '%bSIES bootstrap%b  %s  (user: %s)\n' "$BOLD" "$NC" "$DIR" "$APP_USER"
fi

# ── 1. Base system ───────────────────────────────────────────────────────────
step "1. Base system"
. /etc/os-release 2>/dev/null || true
info "${PRETTY_NAME:-unknown OS} · $(uname -r) · $(uname -m)"
case "${ID:-}" in
  ubuntu|debian) ok "supported distribution" ;;
  *) warn "not Ubuntu/Debian — the apt steps below will not apply" ;;
esac

RAM_MB=$(awk '/MemTotal/{print int($2/1024)}' /proc/meminfo)
DISK_GB=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
info "RAM ${RAM_MB} MB · $(nproc) cores · ${DISK_GB} GB free on /"
if [ "$DISK_GB" -lt 20 ]; then
  bad "only ${DISK_GB} GB free — images, backups and Postgres need room to grow"
fi
if [ "$RAM_MB" -lt 3500 ]; then
  warn "under 4 GB RAM. It will run, but lower the mem_limit values in"
  warn "docker-compose.prod.yml first, and do not skip swap."
fi

if apply; then
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get -y -qq upgrade
  fixed "packages upgraded"
  [ -f /var/run/reboot-required ] && warn "a reboot is required to finish (kernel or libc)"
else
  UPGRADABLE=$(apt-get -s upgrade 2>/dev/null | grep -c '^Inst' || true)
  [ "${UPGRADABLE:-0}" -eq 0 ] && ok "packages up to date" || todo "${UPGRADABLE} package(s) upgradable"
fi

# Bare minimum for everything that follows.
NEED=()
for p in git curl ca-certificates gnupg; do
  command -v "${p%% *}" >/dev/null 2>&1 || NEED+=("$p")
done
if [ "${#NEED[@]}" -gt 0 ]; then
  if apply; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${NEED[@]}"
    fixed "installed: ${NEED[*]}"
  else
    todo "missing: ${NEED[*]}"
  fi
else
  ok "git, curl, ca-certificates present"
fi

# ── 2. Timezone ──────────────────────────────────────────────────────────────
# Asia/Dhaka on the host as well as in every container. Container TZ is set in
# the compose files; this is for cron, systemd timers, syslog and `date` — i.e.
# for whoever reads a log at 3 a.m. and needs the timestamps to mean the same
# thing as the ones in the application.
step "2. Timezone"
CURRENT_TZ=$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo unknown)
if [ "$CURRENT_TZ" = "Asia/Dhaka" ]; then
  ok "timezone is Asia/Dhaka"
elif apply; then
  timedatectl set-timezone Asia/Dhaka
  fixed "timezone ${CURRENT_TZ} -> Asia/Dhaka"
else
  todo "timezone is ${CURRENT_TZ}, should be Asia/Dhaka"
fi

# ── 3. Docker ────────────────────────────────────────────────────────────────
step "3. Docker"
if command -v docker >/dev/null 2>&1; then
  ok "docker $(docker --version | awk '{print $3}' | tr -d ,)"
  if docker compose version >/dev/null 2>&1; then
    ok "compose plugin $(docker compose version --short 2>/dev/null)"
  elif apply; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq docker-compose-plugin
    fixed "compose plugin installed"
  else
    bad "docker compose plugin missing — the deploy cannot run without it"
  fi
elif apply; then
  # get.docker.com installs the engine AND the compose plugin from Docker's own
  # repository, which is more current than Debian's docker.io package and is the
  # combination this project is tested against.
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
  fixed "docker installed and enabled at boot"
else
  todo "docker not installed"
fi

if command -v docker >/dev/null 2>&1; then
  if systemctl is-enabled docker >/dev/null 2>&1; then
    ok "docker starts at boot"
  elif apply; then
    systemctl enable --now docker >/dev/null
    fixed "docker enabled at boot"
  else
    todo "docker is not enabled at boot — a reboot would leave the site down"
  fi
fi

# ── 4. Firewall ──────────────────────────────────────────────────────────────
# 22, 80, 443. Nothing else. Traefik is the only container that publishes a
# port, so there is nothing else to open — and Postgres reachable from the
# internet is the single worst outcome available on this box.
step "4. Firewall (ufw)"
if ! command -v ufw >/dev/null 2>&1; then
  if apply; then
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ufw
    fixed "ufw installed"
  else
    todo "ufw not installed — the server has no firewall"
  fi
fi

if command -v ufw >/dev/null 2>&1; then
  UFW_STATUS="$(ufw status 2>/dev/null || echo unknown)"
  if printf '%s' "$UFW_STATUS" | head -1 | grep -q active; then
    ok "ufw is active"
  elif apply; then
    # Order matters absolutely: allow SSH BEFORE enabling, or this command ends
    # the session that is running it and locks you out of the server.
    ufw allow 22/tcp  >/dev/null
    ufw allow 80/tcp  >/dev/null
    ufw allow 443/tcp >/dev/null
    ufw default deny incoming  >/dev/null
    ufw default allow outgoing >/dev/null
    ufw --force enable >/dev/null
    UFW_STATUS="$(ufw status)"
    fixed "ufw enabled — 22/80/443 in, everything else denied"
  else
    todo "ufw installed but INACTIVE"
  fi

  if printf '%s' "$UFW_STATUS" | head -1 | grep -q active; then
    for p in 22 80 443; do
      # A port can be allowed by number or by an application profile (OpenSSH,
      # 'WWW Full'). Checking only the number reports a perfectly good firewall
      # as broken, which teaches people to ignore this output.
      case "$p" in
        22)  profile='OpenSSH|SSH' ;;
        80)  profile='WWW$|WWW Full|Nginx HTTP|Nginx Full|Apache' ;;
        443) profile='WWW Secure|WWW Full|Nginx HTTPS|Nginx Full|Apache Full|Apache Secure' ;;
      esac
      if printf '%s' "$UFW_STATUS" | grep -qE "^${p}(/tcp)?[[:space:]]" \
         || printf '%s' "$UFW_STATUS" | grep -qE "^(${profile})[[:space:]]"; then
        ok "port ${p} allowed"
      elif apply; then
        ufw allow "${p}/tcp" >/dev/null
        fixed "port ${p} opened"
      else
        bad "port ${p} NOT allowed"
      fi
    done
    if printf '%s' "$UFW_STATUS" | grep -qE "^8080(/tcp)?[[:space:]]+ALLOW"; then
      bad "port 8080 is open to the world — that is the Traefik dashboard. Close it: ufw delete allow 8080/tcp"
    else
      ok "8080 (Traefik dashboard) not exposed"
    fi
  fi
fi

# Docker publishes ports by writing its own iptables rules, which are consulted
# BEFORE ufw's. A container mapped to 0.0.0.0 is on the public internet even
# with ufw denying everything. This is the most-missed hole on a Docker box, and
# it is why every service but Traefik uses `expose:` and not `ports:`.
step "4b. Docker vs the firewall"
if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Ports}}' 2>/dev/null | grep -q '0\.0\.0\.0:'; then
  docker ps --format '    {{.Names}}  {{.Ports}}' | grep '0\.0\.0\.0:' || true
  warn "the above bypass ufw — only 80 and 443 belong there"
else
  ok "nothing published to 0.0.0.0 (or docker not running yet)"
fi

# ── 5. fail2ban and unattended upgrades ──────────────────────────────────────
step "5. Patching and brute-force protection"
if command -v fail2ban-server >/dev/null 2>&1; then
  ok "fail2ban installed"
elif apply; then
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq fail2ban
  systemctl enable --now fail2ban
  fixed "fail2ban installed and enabled"
else
  todo "fail2ban missing — SSH brute force goes unthrottled"
fi

if dpkg -l unattended-upgrades 2>/dev/null | grep -q '^ii'; then
  ok "unattended-upgrades installed"
elif apply; then
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq unattended-upgrades
  dpkg-reconfigure -f noninteractive unattended-upgrades || true
  fixed "unattended-upgrades installed"
else
  todo "unattended-upgrades missing — security patches will not auto-apply"
fi

# cron is installed here, as root, because scripts/setup_backup_cron.sh runs as
# the unprivileged deploy user and cannot install or start it. Without cron
# running, that script's schedule lands in a scheduler that never fires, and the
# fee ledger is silently never backed up.
if command -v crontab >/dev/null 2>&1; then
  ok "cron installed"
  if systemctl is-active cron >/dev/null 2>&1 || systemctl is-active crond >/dev/null 2>&1; then
    ok "cron is running"
  elif apply; then
    systemctl enable --now cron >/dev/null 2>&1 || systemctl enable --now crond >/dev/null 2>&1
    fixed "cron started"
  else
    todo "cron installed but not running — scheduled backups would never fire"
  fi
elif apply; then
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq cron
  systemctl enable --now cron
  fixed "cron installed and enabled"
else
  todo "cron missing — scheduled backups would silently never run"
fi

# ── 6. Swap ──────────────────────────────────────────────────────────────────
step "6. Swap"
if [ "$DO_SWAP" = 0 ]; then
  info "skipped (--no-swap)"
elif swapon --show 2>/dev/null | grep -q .; then
  ok "swap active ($(free -h | awk '/Swap/{print $2}') total)"
elif apply && [ -f "$DIR/scripts/setup_swap.sh" ]; then
  bash "$DIR/scripts/setup_swap.sh" && fixed "swapfile created and enabled"
elif apply && [ -f "$(dirname "$0")/setup_swap.sh" ]; then
  # bootstrap.sh may be running from a scp'd copy before the repo exists.
  bash "$(dirname "$0")/setup_swap.sh" && fixed "swapfile created and enabled"
else
  todo "no swap — Postgres has no safety valve (scripts/setup_swap.sh)"
fi

SWAPPINESS=$(cat /proc/sys/vm/swappiness)
if [ "$SWAPPINESS" -le 20 ]; then
  ok "vm.swappiness=${SWAPPINESS}"
else
  warn "vm.swappiness=${SWAPPINESS} — 10 suits a database box (setup_swap.sh sets it)"
fi

# ── 7. Deploy user ───────────────────────────────────────────────────────────
# A system account with no login shell: reached with `sudo -u sies`, never
# logged into. Membership of the docker group is what lets it run Compose — and
# is also why this is a guard against accidents, not against an attacker who
# already has a shell as this user. Docker group access is root-equivalent.
step "7. Deploy user"
# The home directory is deliberately NOT the checkout. The deploy key lives in
# ~/.ssh, and `git clone` refuses a non-empty destination — so making the
# checkout the home would mean the key blocks the clone that needs it.
APP_HOME="/var/lib/${APP_USER}"

if id "$APP_USER" >/dev/null 2>&1; then
  ok "user ${APP_USER} exists"
elif apply; then
  adduser --system --group --shell /usr/sbin/nologin --home "$APP_HOME" "$APP_USER"
  fixed "created ${APP_USER} (system account, no login shell)"
else
  todo "user ${APP_USER} does not exist"
fi

if id "$APP_USER" >/dev/null 2>&1 && apply; then
  mkdir -p "$APP_HOME/.ssh"
  chown -R "$APP_USER":"$APP_USER" "$APP_HOME"
  chmod 700 "$APP_HOME/.ssh"

  getent group docker >/dev/null || groupadd docker
  if id -nG "$APP_USER" | tr ' ' '\n' | grep -qx docker; then
    ok "${APP_USER} is in the docker group"
  else
    usermod -aG docker "$APP_USER"
    fixed "${APP_USER} added to the docker group"
  fi
fi

# ── 8. Repository ────────────────────────────────────────────────────────────
# Cloned AS the app user so ownership is right from the first byte. A
# `chown -R` afterwards is the step people half-apply.
step "8. Repository"
if [ -d "$DIR/.git" ]; then
  ok "git repo present at ${DIR}"
  OWNER="$(stat -c '%U' "$DIR")"
  if [ "$OWNER" != "$APP_USER" ]; then
    warn "owned by ${OWNER}, not ${APP_USER}"
    info "if nothing is running from it:  chown -R ${APP_USER}:${APP_USER} ${DIR}"
    info "if the stack IS live, do that in a maintenance window, not now"
  else
    ok "owned by ${APP_USER}"
  fi
  # This script provisions; pull_and_deploy.sh releases. It deliberately does
  # not pull — but silently running against stale code is a confusing way to
  # learn that, so say where you stand.
  if sudo -u "$APP_USER" -H git -C "$DIR" fetch --quiet 2>/dev/null; then
    BEHIND="$(sudo -u "$APP_USER" -H git -C "$DIR" rev-list --count HEAD..@{u} 2>/dev/null || echo 0)"
    [ "${BEHIND:-0}" -gt 0 ] && warn "${BEHIND} commit(s) behind the remote — pull_and_deploy.sh will pick them up"
  fi
elif [ -d "$DIR" ] && [ -n "$(ls -A "$DIR" 2>/dev/null)" ]; then
  die "${DIR} exists, is not empty, and is not a git repo — refusing to touch it"
elif ! apply; then
  todo "would clone ${REPO} into ${DIR}"
else
  mkdir -p "$DIR"
  chown "$APP_USER":"$APP_USER" "$DIR"
  case "$REPO" in
    git@*|ssh://*)
      # A private repo over SSH needs a key THIS user can read; the one you use
      # interactively does not count. Rather than dead-ending, generate it and
      # print it — the only step left is a paste into GitHub.
      KEY="$APP_HOME/.ssh/id_ed25519"
      # accept-new so the first connection does not stop on a prompt nobody is
      # there to answer; BatchMode so it fails instead of asking for a password.
      GIT_SSH="ssh -o StrictHostKeyChecking=accept-new -o BatchMode=yes -i $KEY"
      if [ ! -f "$KEY" ]; then
        sudo -u "$APP_USER" -H ssh-keygen -q -t ed25519 -f "$KEY" -N '' \
          -C "${APP_USER}@$(hostname -s) (sies deploy)"
        info "generated a deploy key at ${KEY}"
      fi
      if ! sudo -u "$APP_USER" -H env GIT_SSH_COMMAND="$GIT_SSH" \
             git ls-remote "$REPO" >/dev/null 2>&1; then
        # Not a failure — a handover. Nothing has gone wrong; the script has
        # done its half and is waiting on the one step only you can do.
        echo
        printf '%b────────────────────────────────────────────────────%b\n' "$YELLOW" "$NC"
        printf '%b  One step for you, then run this script again.%b\n' "$BOLD" "$NC"
        printf '%b────────────────────────────────────────────────────%b\n' "$YELLOW" "$NC"
        echo
        echo "  1. Copy the whole line below."
        echo "  2. GitHub -> the sies repo -> Settings -> Deploy keys -> Add deploy key."
        echo "     Leave write access UNCHECKED; this server only ever pulls."
        echo "  3. Re-run: sudo bash $0"
        echo
        cat "$KEY.pub"
        echo
        printf '  %b(or skip keys entirely: --repo https://github.com/<you>/sies.git)%b\n' "$CYAN" "$NC"
        echo
        # Non-zero so an automated caller knows the run did not finish, but with
        # no ERROR: nothing is broken here.
        exit 2
      fi
      export GIT_SSH_COMMAND="$GIT_SSH"
      ;;
  esac
  # sudo scrubs the environment, so GIT_SSH_COMMAND has to be passed explicitly
  # or the key just proven to work would not be used by the clone itself.
  sudo -u "$APP_USER" -H env GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh}" \
    git clone "$REPO" "$DIR"
  fixed "cloned to ${DIR}"
fi

# ── 9. Directory layout and secrets ──────────────────────────────────────────
step "9. Directories and secrets"
if apply && [ -d "$DIR" ]; then
  for d in backups logs; do
    if [ -d "$DIR/$d" ]; then
      ok "${d}/ exists"
    else
      mkdir -p "$DIR/$d"
      fixed "created ${d}/"
    fi
    chown "$APP_USER":"$APP_USER" "$DIR/$d"
    # 0750: backups contain the entire student and fee database in plain text.
    # Anyone who can read this directory can read every record in the system.
    chmod 750 "$DIR/$d"
  done
fi

# Put each secret file in place from its example, owned by the deploy user and
# 0600, so nobody has to remember the chown/chmod dance — editing as root
# through sudo leaves them root-owned, which the deploy then cannot read.
#
# A file is never overwritten. But a copy that was never edited is as useless as
# a missing one and looks finished, so that case is called out separately.
MISSING=0
if [ -d "$DIR" ]; then
  for f in .env.production traefik/traefik.env; do
    target="$DIR/$f"; example="$DIR/$f.example"
    if [ ! -f "$target" ] && [ -f "$example" ] && apply; then
      cp "$example" "$target"
      info "$f created from its example"
    fi
    if [ -f "$target" ]; then
      apply && { chown "$APP_USER":"$APP_USER" "$target"; chmod 600 "$target"; }
      if grep -q 'CHANGE_ME\|REPLACE' "$target" 2>/dev/null; then
        warn "$f still contains placeholders — fill it in:  sudo -u ${APP_USER} nano $target"
        MISSING=$((MISSING+1))
      else
        ok "$f present (0600, owned by ${APP_USER})"
      fi
    else
      warn "$f missing"
      MISSING=$((MISSING+1))
    fi
  done
fi

# ── Summary ──────────────────────────────────────────────────────────────────
printf '\n%b────────────────────────────────────────────────────%b\n' "$BOLD" "$NC"
printf '  %b%s ok%b   %b%s fixed%b   %b%s to do%b   %b%s failing%b\n' \
  "$GREEN" "$PASS" "$NC" "$GREEN" "$FIXED" "$NC" "$YELLOW" "$TODO" "$NC" "$RED" "$FAIL" "$NC"

if [ "$AUDIT" = 1 ]; then
  printf '\n  Nothing was changed. Re-run without --audit to apply.\n'
  exit 0
fi
if [ "$FAIL" -gt 0 ]; then
  printf '\n  %bResolve the failures above before deploying.%b\n' "$RED" "$NC"
  exit 1
fi

printf '\n  Next:\n'
[ "$MISSING" -gt 0 ] && printf '    1. fill in the %s secret file(s) flagged above\n' "$MISSING"
printf '    2. %bsudo -u %s %s/scripts/fresh_deploy.sh%b\n' "$BOLD" "$APP_USER" "$DIR" "$NC"
printf '\n  Note: %s joined the docker group in this run. If you hit a permission\n' "$APP_USER"
printf '  error on the docker socket, log out and back in first.\n'
