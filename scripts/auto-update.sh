#!/usr/bin/env bash
#
# auto-update.sh — daily unattended update of web-facing Docker services.
#
# Backs up Vaultwarden data, pulls newer images and recreates ONLY the
# vaultwarden + cloudflared containers. WireGuard and Unbound are deliberately
# left untouched so a routine update never drops VPN sessions or peer DNS.
#
# Idempotent: safe to run repeatedly; if no new image exists, `up -d` is a no-op.
# Intended to run from cron. All output is appended to $LOG_FILE.
#
set -euo pipefail

# --- Config (override via env) ---------------------------------------------
COMPOSE_DIR="${COMPOSE_DIR:-/root/vpn-server}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
BACKUP_DIR="${BACKUP_DIR:-/root/backups}"
LOG_FILE="${LOG_FILE:-/var/log/vpn-auto-update.log}"
SERVICES="${SERVICES:-vaultwarden cloudflared}"
KEEP_BACKUPS="${KEEP_BACKUPS:-7}"
# ---------------------------------------------------------------------------

PROJECT="$(basename "$COMPOSE_DIR")"          # compose project name = dir basename
VW_VOLUME="${PROJECT}_vaultwarden-data"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

# Single instance only — avoid overlapping runs.
exec 9>"/tmp/vpn-auto-update.lock"
if ! flock -n 9; then
  echo "another auto-update run is in progress; exiting" >&2
  exit 0
fi

mkdir -p "$BACKUP_DIR"
exec >>"$LOG_FILE" 2>&1

log "===== auto-update start (services: $SERVICES) ====="

# Preconditions
command -v docker >/dev/null 2>&1 || { log "ERROR: docker not found"; exit 1; }
cd "$COMPOSE_DIR" || { log "ERROR: compose dir $COMPOSE_DIR missing"; exit 1; }

# 1. Backup Vaultwarden data before touching anything.
if docker volume inspect "$VW_VOLUME" >/dev/null 2>&1; then
  BACKUP_FILE="$BACKUP_DIR/vw-auto-$(date +%Y%m%d-%H%M%S).tar.gz"
  if docker run --rm -v "$VW_VOLUME":/data -v "$BACKUP_DIR":/backup alpine \
       tar czf "/backup/$(basename "$BACKUP_FILE")" -C /data .; then
    log "backup ok: $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
  else
    log "ERROR: backup failed — aborting update"; exit 1
  fi
else
  log "WARN: volume $VW_VOLUME not found — skipping backup"
fi

# 2. Record current image digests (for the log trail).
for svc in $SERVICES; do
  log "before: $svc -> $(docker inspect --format '{{.Config.Image}} {{.Image}}' "$svc" 2>/dev/null || echo 'not running')"
done

# 3. Pull + recreate only the targeted services.
log "pulling images..."
docker compose -f "$COMPOSE_FILE" pull $SERVICES
log "recreating containers..."
docker compose -f "$COMPOSE_FILE" up -d $SERVICES

# 4. Health check.
sleep 8
HEALTH="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' vaultwarden 2>/dev/null || echo unknown)"
log "vaultwarden status: $HEALTH"
[ "$HEALTH" = "unhealthy" ] && log "WARN: vaultwarden reports unhealthy — check logs"

# 5. Housekeeping: prune dangling images, rotate backups.
docker image prune -f >/dev/null 2>&1 && log "pruned dangling images"
ls -t "$BACKUP_DIR"/vw-auto-*.tar.gz 2>/dev/null | tail -n +"$((KEEP_BACKUPS + 1))" | while read -r f; do
  rm -f "$f" && log "rotated old backup: $f"
done

log "===== auto-update done ====="
