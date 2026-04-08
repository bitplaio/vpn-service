---
name: docs-update
description: Update architecture/infrastructure/database docs after implementation changes. Use after significant changes.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Docs Update Skill

## Steps

1. **Get recent changes:**
   ```bash
   git log --oneline -10
   git diff --name-only HEAD~3
   ```

2. **Determine what docs need updating:**
   - `docker-compose*.yml` changed → update architecture.md, infrastructure.md
   - `wireguard/` changed → update architecture.md (network topology)
   - `caddy/` changed → update architecture.md (reverse proxy)
   - `.env.example` changed → update infrastructure.md
   - `scripts/` changed → update infrastructure.md
   - DB-related changes → update database.md

3. **Read current docs:**
   - Read `.claude/docs/architecture.md`
   - Read `.claude/docs/infrastructure.md`
   - Read `.claude/docs/database.md`

4. **Update relevant docs:**
   - Keep format consistent
   - Update ports, paths, commands as needed
   - Add new services/volumes/networks if added
   - Remove deprecated entries

5. **Verify accuracy:**
   - Cross-reference with actual docker-compose files
   - Check that all listed ports match reality
   - Verify commands work

6. **Report what was updated:**
   ```
   ## Docs Updated
   - architecture.md: [what changed]
   - infrastructure.md: [what changed]
   ```
