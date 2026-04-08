---
name: commit
description: Check for secrets, validate configs, stage specific files, commit with conventional format. Use for ALL commits.
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Commit Skill

## Steps

1. **Pull latest changes:**
   ```bash
   git pull --rebase origin $(git branch --show-current)
   ```

2. **Check for secrets in staged/changed files:**
   ```bash
   # Scan for private keys, tokens, passwords in changed files
   git diff --cached --name-only | xargs grep -l -i -E "(PRIVATE_KEY|private_key|password|token|secret|admin_token)" 2>/dev/null
   ```
   - If secrets found → STOP and warn user
   - Check that .env files are NOT staged

3. **Validate Docker configs (if changed):**
   ```bash
   docker compose config --quiet 2>&1
   ```

4. **Check session file:**
   - Verify today's session file in `.claude/sessions/` exists and is updated
   - If not, remind user to update it

5. **Show changes for review:**
   ```bash
   git status
   git diff --cached --stat
   ```

6. **Stage specific files:**
   - NEVER use `git add .` or `git add -A`
   - Stage only relevant files by name
   - Confirm with user before staging

7. **Commit with conventional format:**
   ```bash
   git commit -m "$(cat <<'EOF'
   type(scope): description

   Body if needed.

   Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
   EOF
   )"
   ```

   Types: feat, fix, chore, docs, refactor, security
   Scopes: wireguard, vaultwarden, docker, caddy, scripts

8. **Post-commit verification:**
   ```bash
   git log --oneline -1
   ```
