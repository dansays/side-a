#!/usr/bin/env bash
# One-command deploy of Side A to the Synology NAS.
#
#   ./scripts/deploy-nas.sh
#   ./scripts/deploy-nas.sh --no-cache   # force a full rebuild
#
# Syncs the repo to the NAS docker share (over the SMB mount) and rebuilds the
# container over SSH. Mirrors shoppr/scripts/deploy-nas.sh.
#
# Reuses the one-time NAS setup from shoppr (see shoppr/DEPLOY.md →
# "Remote updates over SSH"): SSH key auth to the NAS and passwordless sudo for
# the docker binary (/etc/sudoers.d/shoppr-docker covers all compose projects).
# Side A-specific prerequisites: the repo synced once to the share + side-a.env
# created on the NAS next to docker-compose.yml.
set -euo pipefail

NAS_HOST="${NAS_HOST:-dansays@Synology.local}"
NAS_PROJECT="${NAS_PROJECT:-/volume1/docker/side-a/app}"
# Sibling data dir (SQLite db, thumbnails, mp3s) — outside the synced repo, so
# `rsync --delete` on app/ never touches it. Synology's docker won't auto-create
# bind-mount sources, so pre-create it here (idempotent).
NAS_DATA="${NAS_DATA:-/volume1/docker/side-a/data}"
SHARE="${SHARE:-/Volumes/docker/side-a/app}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
BUILD_FLAGS="--build"
[ "${1:-}" = "--no-cache" ] && BUILD_FLAGS="--build --no-cache"

[ -d "$SHARE" ] || { echo "✗ NAS share not mounted at $SHARE (mount the 'docker' share first)"; exit 1; }

echo "→ syncing repo → $SHARE/"
rsync -a --delete \
	--exclude='.git' --exclude='.venv' --exclude='__pycache__' \
	--exclude='**/__pycache__' --exclude='*.egg-info' \
	--exclude='/data' --exclude='*.db' \
	--exclude='.DS_Store' --exclude='.env' --exclude='side-a.env' \
	"$REPO/" "$SHARE/"

echo "→ rebuilding on $NAS_HOST ($NAS_PROJECT)"
# shellcheck disable=SC2029
ssh -o StrictHostKeyChecking=accept-new "$NAS_HOST" \
	"mkdir -p '$NAS_DATA' && cd '$NAS_PROJECT' && sudo /usr/local/bin/docker compose up -d $BUILD_FLAGS"

echo "→ waiting for health…"
host="${NAS_HOST#*@}"
# Poll the container's Docker healthcheck on the NAS over one SSH connection —
# the authoritative readiness signal, avoiding flaky Mac→NAS mDNS curl loops.
state=$(ssh -o StrictHostKeyChecking=accept-new "$NAS_HOST" '
	i=0
	while [ "$i" -lt 40 ]; do
		i=$((i + 1))
		s=$(sudo /usr/local/bin/docker inspect -f "{{.State.Health.Status}}" side-a 2>/dev/null || true)
		case "$s" in
			healthy)   echo healthy;   exit 0 ;;
			unhealthy) echo unhealthy; exit 1 ;;
		esac
		sleep 2
	done
	echo "${s:-unknown}"
	exit 1
')
rc=$?
if [ "$rc" -eq 0 ]; then
	echo "✓ deployed — container healthy — http://$host:8099"
	exit 0
fi
echo "⚠ deployed, but health didn't pass in time (container: ${state:-unknown}) — check 'sudo docker compose logs side-a' on the NAS"
exit 1
