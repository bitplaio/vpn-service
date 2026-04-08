---
name: test
description: Run connectivity and health tests for all services. Use for ALL testing.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Test Skill

## Steps

1. **Check containers are running:**
   ```bash
   docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>&1 | tail -n 20
   ```

2. **Run health checks in parallel:**

   **WireGuard:**
   ```bash
   docker exec vpn-wireguard wg show 2>&1 | tail -n 20
   ```

   **Vaultwarden:**
   ```bash
   curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/alive
   ```

   **Vaultwarden WebSocket (if enabled):**
   ```bash
   curl -s -o /dev/null -w "%{http_code}" http://localhost:3012
   ```

3. **Test VPN connectivity (if peers configured):**
   ```bash
   # Ping VPN gateway
   ping -c 3 -W 2 10.10.0.1 2>&1 | tail -n 5
   ```

4. **Check DNS resolution through VPN (if configured):**
   ```bash
   docker exec vpn-wireguard nslookup google.com 2>&1 | tail -n 5
   ```

5. **Check container resource usage:**
   ```bash
   docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" 2>&1 | tail -n 10
   ```

6. **Check for errors in recent logs:**
   ```bash
   docker compose logs --tail=50 2>&1 | grep -i -E "(error|fatal|panic|failed)" | tail -n 20
   ```

7. **Report results:**
   Format: ✓ PASS / ✗ FAIL for each check with details on failures.
