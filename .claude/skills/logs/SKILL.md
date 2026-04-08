---
name: logs
description: View container and service logs from any environment. Always pipe through tail.
allowed-tools: Bash, Read
---

# Logs Skill

## Usage

`/logs` — show all services (last 50 lines)
`/logs wireguard` — show specific service
`/logs prod` — show prod logs
`/logs prod vaultwarden` — show specific prod service

## Steps

1. **Parse arguments:**
   - Default: all services, dev environment, last 50 lines
   - If service specified: filter to that service
   - If "prod" specified: use prod compose file

2. **Show logs:**

   **Dev (default):**
   ```bash
   docker compose logs --tail=50 <service> 2>&1 | tail -n 60
   ```

   **Prod:**
   ```bash
   ssh vpn "cd /opt/vpn-server && docker compose -f docker-compose.prod.yml logs --tail=50 <service> 2>&1" | tail -n 60
   ```

3. **Highlight issues:**
   - Scan output for ERROR, FATAL, PANIC, WARN
   - Summarize any issues found

4. **WireGuard-specific:**
   ```bash
   docker exec vpn-wireguard wg show 2>&1 | tail -n 30
   ```

## IMPORTANT
- Always pipe through `tail` to prevent context flooding
- Never output more than 60 lines
- Summarize long outputs
