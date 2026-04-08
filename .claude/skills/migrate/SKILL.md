---
name: migrate
description: Vaultwarden DB operations. Backup, verify, restore. Use for ALL database operations.
allowed-tools: Bash, Read, Write, Edit
---

# Migrate Skill

## Context
Vaultwarden uses SQLite with auto-migrations. Manual migrations are rarely needed.
This skill handles backup/restore and safe DB operations.

## Steps

### Backup (default action)

1. **Create backup:**
   ```bash
   docker compose exec vaultwarden sqlite3 /data/db.sqlite3 ".backup '/data/backup-$(date +%Y%m%d-%H%M%S).sqlite3'"
   ```

2. **Copy backup out of container:**
   ```bash
   docker cp vpn-vaultwarden:/data/backup-*.sqlite3 ./backups/
   ```

3. **Verify backup integrity:**
   ```bash
   sqlite3 ./backups/backup-*.sqlite3 "PRAGMA integrity_check;"
   ```

### Restore (requires explicit confirmation)

1. **CONFIRM with user:** "Restore database from backup? This will overwrite current data. (yes/no)"

2. **Stop Vaultwarden:**
   ```bash
   docker compose stop vaultwarden
   ```

3. **Backup current DB first:**
   ```bash
   docker cp vpn-vaultwarden:/data/db.sqlite3 ./backups/pre-restore-$(date +%Y%m%d).sqlite3
   ```

4. **Restore from backup:**
   ```bash
   docker cp ./backups/<backup-file> vpn-vaultwarden:/data/db.sqlite3
   ```

5. **Start and verify:**
   ```bash
   docker compose start vaultwarden
   docker compose exec vaultwarden sqlite3 /data/db.sqlite3 "PRAGMA integrity_check;"
   curl -s http://localhost:8080/alive
   ```

### Prod (double confirmation required)

1. Ask: "This targets PRODUCTION database. Are you sure? (yes/no)"
2. Ask again: "Final confirmation — restore prod Vaultwarden DB? (yes/no)"
3. Follow same steps with prod compose file
