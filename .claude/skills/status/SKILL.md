---
name: status
description: Check container status, WireGuard peers, service health, deploy state. Use to check system health.
allowed-tools: Bash, Read
---

# Status Skill

## Steps

1. **Container status:**
   ```bash
   docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>&1
   ```

2. **WireGuard peers:**
   ```bash
   docker exec vpn-wireguard wg show 2>&1 | tail -n 30
   ```

3. **Vaultwarden health:**
   ```bash
   curl -s -o /dev/null -w "HTTP %{http_code}" http://localhost:8080/alive 2>&1
   ```

4. **Resource usage:**
   ```bash
   docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" 2>&1
   ```

5. **Restart counts:**
   ```bash
   docker compose ps --format "{{.Name}}: {{.Status}}" 2>&1
   ```

6. **Recent errors (last 20 lines):**
   ```bash
   docker compose logs --tail=100 2>&1 | grep -i -E "(error|fatal|panic|failed)" | tail -n 10
   ```

7. **Deploy state:**
   ```bash
   cat .claude/docs/deploy-state.json 2>/dev/null || echo "No deploy state"
   ```

8. **Disk usage:**
   ```bash
   docker system df 2>&1
   ```

9. **Output summary:**
   ```
   ## System Status

   | Service | Status | Health |
   |---------|--------|--------|
   | wireguard | ✓ running | X peers connected |
   | vaultwarden | ✓ running | HTTP 200 |
   | caddy | ✓ running | — |

   Resources: CPU X%, Memory X MB
   Last deploy: <timestamp>
   Errors: none / [list]
   ```
