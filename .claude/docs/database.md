# Database

## Vaultwarden Database

Vaultwarden uses **SQLite** by default. The database file lives inside the Docker volume.

### Location
- Container path: `/data/db.sqlite3`
- Volume: `vw-data`
- Host access: `docker compose exec vaultwarden sqlite3 /data/db.sqlite3`

### Connection Commands

**Dev:**
```bash
docker compose exec vaultwarden sqlite3 /data/db.sqlite3
```

**Prod:**
```bash
docker compose -f docker-compose.prod.yml exec vaultwarden sqlite3 /data/db.sqlite3
```

### NEVER Rules
- NEVER delete or truncate tables directly
- NEVER modify user password hashes
- NEVER access DB without creating a backup first
- NEVER run VACUUM on prod without stopping the service
- NEVER share or output DB file contents

### ALWAYS Rules
- ALWAYS backup before any DB operation: `cp /data/db.sqlite3 /data/db.sqlite3.bak`
- ALWAYS use read-only mode for diagnostics: `sqlite3 -readonly /data/db.sqlite3`
- ALWAYS check DB integrity after restore: `PRAGMA integrity_check;`

### Useful Diagnostic Queries

```sql
-- Check DB size and integrity
PRAGMA page_count;
PRAGMA integrity_check;

-- Count users
SELECT COUNT(*) FROM users;

-- Check organizations
SELECT name, billing_email FROM organizations;

-- Recent logins (ciphers access)
SELECT u.email, MAX(c.updated_at) 
FROM users u 
JOIN ciphers c ON c.user_uuid = u.uuid 
GROUP BY u.email;
```

## Backup Workflow

```bash
# Manual backup
docker compose exec vaultwarden sqlite3 /data/db.sqlite3 ".backup '/data/backup.sqlite3'"

# Copy backup out of container
docker cp vpn-vaultwarden:/data/backup.sqlite3 ./backups/vw-$(date +%Y%m%d).sqlite3

# Full backup (DB + attachments + config)
./scripts/backup.sh
```

## Restore Workflow

```bash
# Stop Vaultwarden
docker compose stop vaultwarden

# Replace DB
docker cp ./backups/vw-YYYYMMDD.sqlite3 vpn-vaultwarden:/data/db.sqlite3

# Start and verify
docker compose start vaultwarden
docker compose exec vaultwarden sqlite3 /data/db.sqlite3 "PRAGMA integrity_check;"
```
