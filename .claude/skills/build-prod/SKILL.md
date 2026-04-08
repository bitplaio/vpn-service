---
name: build-prod
description: Deploy to production. Merge dev→main, rebuild on prod server. Use for ALL prod deployments. REQUIRES explicit user confirmation.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Build Prod Skill

## Steps

1. **CONFIRM with user:** Ask "Deploy to production? (yes/no)" — do NOT proceed without explicit "yes"

2. **Merge dev → main:**
   ```bash
   git checkout main
   git merge dev
   git push origin main
   ```

3. **Pull on prod server:**
   ```bash
   ssh vpn "cd /opt/vpn-server && git pull origin main"
   ```

4. **Check active WireGuard connections:**
   ```bash
   ssh vpn "docker exec vpn-wireguard wg show | grep 'latest handshake'"
   ```
   - If active connections → warn user, ask to confirm

5. **Validate prod config:**
   ```bash
   ssh vpn "cd /opt/vpn-server && docker compose -f docker-compose.prod.yml config --quiet"
   ```

6. **Rebuild services:**
   ```bash
   ssh vpn "cd /opt/vpn-server && docker compose -f docker-compose.prod.yml up -d --build"
   ```

7. **Verify health:**
   ```bash
   ssh vpn "docker compose -f docker-compose.prod.yml ps"
   ssh vpn "docker exec vpn-wireguard wg show"
   ssh vpn "curl -s http://localhost:8080/alive"
   ```

8. **Check logs for errors:**
   ```bash
   ssh vpn "docker compose -f docker-compose.prod.yml logs --tail=30"
   ```

9. **Update deploy state:**
   Write to `.claude/docs/deploy-state.json` with prod section.

10. **Switch back to dev branch:**
    ```bash
    git checkout dev
    ```
