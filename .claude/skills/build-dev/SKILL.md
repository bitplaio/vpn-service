---
name: build-dev
description: Deploy to dev environment. Push to dev branch, rebuild changed services. Use for ALL dev deployments.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Build Dev Skill

## Steps

1. **Push to dev branch:**
   ```bash
   git push origin dev
   ```

2. **Pull on server (if remote):**
   ```bash
   ssh vpn "cd /opt/vpn-server && git pull origin dev"
   ```
   If local dev — skip this step.

3. **Read deploy state:**
   ```bash
   cat .claude/docs/deploy-state.json 2>/dev/null || echo "No deploy state found"
   ```

4. **Diff changed files since last deploy:**
   ```bash
   git diff --name-only HEAD~1
   ```

5. **Map changes to services:**
   - `docker-compose.yml` → all services
   - `wireguard/` → wireguard service
   - `caddy/` → caddy service
   - `.env` → all services
   - `scripts/` → no rebuild needed

6. **Validate config before rebuild:**
   ```bash
   docker compose config --quiet
   ```

7. **Rebuild changed services:**
   ```bash
   docker compose up -d --build <changed-services>
   ```

8. **Verify health:**
   ```bash
   docker compose ps
   docker compose logs --tail=20 <changed-services>
   ```

9. **Update deploy state:**
   Write to `.claude/docs/deploy-state.json`:
   ```json
   {
     "dev": {
       "last_deploy": "<ISO timestamp>",
       "commit": "<git hash>",
       "services_rebuilt": ["<list>"],
       "status": "ok"
     }
   }
   ```
