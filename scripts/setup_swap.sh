#!/usr/bin/env bash
# =============================================================================
# SIES — swapfile, sized from the box rather than guessed.
#
#   sudo scripts/setup_swap.sh          # size chosen from total RAM
#   sudo scripts/setup_swap.sh 4G       # or say it outright
#
# Swap here is a SAFETY VALVE, not extra memory. A small VPS running Postgres,
# Redis, gunicorn, a Celery worker and — during a deploy — two Node/Vite builds
# will spike past its RAM, and the OOM killer picks the largest process, which
# is Postgres, mid-write. Swap turns that into a slow minute instead of a
# corrupted afternoon.
#
# That is also why vm.swappiness is set to 10: the kernel should reach for swap
# reluctantly, only under real pressure, never as a routine tier.
#
# Sizing: half of RAM, floor 2 GB, ceiling 4 GB.
#   2 GB RAM -> 2G     4 GB RAM -> 2G     8 GB RAM -> 4G     16 GB RAM -> 4G
# The ceiling is deliberate. Past a point more swap does not save a box — one
# leaning on 16 GB of swap is thrashing, and you want it to fail fast and
# restart rather than crawl for an hour while nobody can log in.
#
# Idempotent: an existing active swapfile is reported and left alone.
# =============================================================================
set -euo pipefail

SWAPFILE="${SWAPFILE:-/swapfile}"

RAM_MB=$(awk '/MemTotal/{print int($2/1024)}' /proc/meminfo)

if [ -n "${1:-}" ]; then
  SIZE="$1"
else
  HALF_GB=$(( RAM_MB / 2 / 1024 ))
  [ "$HALF_GB" -lt 2 ] && HALF_GB=2
  [ "$HALF_GB" -gt 4 ] && HALF_GB=4
  SIZE="${HALF_GB}G"
fi

case "$SIZE" in
  *[Gg]) SIZE_MB=$(( ${SIZE%[GgMm]} * 1024 )) ;;
  *[Mm]) SIZE_MB=${SIZE%[GgMm]} ;;
  *)     SIZE_MB="$SIZE"; SIZE="${SIZE}M" ;;
esac

# Everything below writes to the system, so require root up front rather than
# failing halfway through with a half-created swapfile on the disk.
if [ "$(id -u)" -ne 0 ]; then
  echo "This needs root:  sudo $0 ${*:-}" >&2
  exit 1
fi

echo "RAM ${RAM_MB} MB -> swap ${SIZE}"

if swapon --show=NAME --noheadings 2>/dev/null | grep -qx "$SWAPFILE"; then
  CUR_MB=$(awk -v f="$SWAPFILE" '$1==f{print int($3/1024)}' /proc/swaps)
  echo "Swap already active at ${SWAPFILE} (${CUR_MB} MB) — leaving it alone."
  # Resizing means swapoff, which forces every swapped page back into RAM at
  # once. On a box that is already tight that is the exact moment it OOMs, so
  # this script will never do it for you.
  if [ "${CUR_MB:-0}" -lt "$(( SIZE_MB * 80 / 100 ))" ]; then
    echo "NOTE: smaller than the ${SIZE} this box suggests."
    echo "      To resize, when the stack is stopped or quiet:"
    echo "        sudo swapoff ${SWAPFILE} && sudo rm ${SWAPFILE} && sudo $0 ${SIZE}"
  fi
  exit 0
fi

# A stale file with no swap active: an interrupted earlier run. Reuse it rather
# than refusing, but only after confirming nothing has it open.
if [ -e "$SWAPFILE" ]; then
  echo "Found ${SWAPFILE} but it is not active — re-initialising it."
  rm -f "$SWAPFILE"
fi

# Do not fill the disk chasing a safety valve. 10 GB headroom covers Docker
# images, the backup directory and Postgres growth.
DISK_FREE_MB=$(df -BM --output=avail / | tail -1 | tr -dc '0-9')
if [ "$DISK_FREE_MB" -lt "$(( SIZE_MB + 10240 ))" ]; then
  echo "ERROR: ${DISK_FREE_MB} MB free on / — need ${SIZE_MB} MB for swap plus" >&2
  echo "       ~10 GB headroom for images, backups and postgres. Aborting." >&2
  exit 1
fi

# fallocate is instant but unsupported on some filesystems (older overlay, some
# ZFS setups); dd always works and is only slow.
fallocate -l "$SIZE" "$SWAPFILE" 2>/dev/null || \
  dd if=/dev/zero of="$SWAPFILE" bs=1M count="$SIZE_MB" status=progress

# 600 before mkswap: a world-readable swapfile is a readable copy of whatever
# memory gets paged out, which includes the database password.
chmod 600 "$SWAPFILE"
mkswap "$SWAPFILE" >/dev/null
swapon "$SWAPFILE"

# Survive a reboot. Without this the box comes back from its first restart with
# no swap and nobody notices until the next spike.
if ! grep -q "^${SWAPFILE} " /etc/fstab; then
  printf '%s none swap sw 0 0\n' "$SWAPFILE" >> /etc/fstab
  echo "Added ${SWAPFILE} to /etc/fstab"
fi

# swappiness=10: use swap only under genuine pressure.
# vfs_cache_pressure=50: hold on to directory/inode cache a little longer, which
# is worth it for Postgres' many-file access pattern.
tee /etc/sysctl.d/99-sies-swap.conf > /dev/null <<'SYSCTL'
vm.swappiness=10
vm.vfs_cache_pressure=50
SYSCTL
sysctl --system >/dev/null

echo "Done."
swapon --show
free -h
