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

2. **Pull on server:**
   ```bash
   ssh vpn "cd ~/vpn-server && git pull --ff-only origin dev"
   ```
   Dev lives in `~/vpn-server` (i.e. `/root/vpn-server`). `/opt/vpn-server` does
   NOT exist — prod has never been deployed.

   **Check for divergence first.** On 2026-08-09 the server's checkout was sitting
   four commits behind on the initial commit while the files on disk matched a much
   later one, because configs had been copied in outside git. A blind pull fails or
   clobbers. Verify before pulling:
   ```bash
   ssh vpn "cd ~/vpn-server && git status --short && git diff origin/dev --stat"
   # and list untracked files that the pull would need to overwrite:
   ssh vpn 'cd ~/vpn-server && git ls-tree -r --name-only origin/dev | while read f; do
     [ -e "$f" ] && ! git ls-files --error-unmatch "$f" >/dev/null 2>&1 && echo "$f"; done'
   ```

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
