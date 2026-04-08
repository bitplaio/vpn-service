# CLAUDE.md

VPN Server — WireGuard VPN + Vaultwarden (self-hosted Bitwarden) на Docker, деплой через docker-compose.

## Critical Rules

- **Все конфиги содержат секреты** — никогда не выводить приватные ключи, пароли, токены в чат
- **Docker — единственный способ запуска** — никаких прямых установок на хост
- **WireGuard ключи генерировать только через wg genkey/wg pubkey** — никогда не хардкодить
- **Бэкапы перед любыми изменениями** — конфигов, volumes, базы Vaultwarden
- **MUST use skills for operations** — /commit, /build-dev, /build-prod, /logs, /status, etc.
- **Firewall rules** — не открывать порты без явной инструкции пользователя

## Workflow

### Environments

| Environment | Branch | Server Path             | Compose File              |
|-------------|--------|-------------------------|---------------------------|
| dev         | dev    | ~/vpn-server            | docker-compose.yml        |
| prod        | main   | /opt/vpn-server         | docker-compose.prod.yml   |

### Standard Flow
```
Implement → /commit → /build-dev → /test → /build-prod
```

### Build Restrictions (CRITICAL)
NEVER trigger builds automatically. Builds ONLY via explicit skills.

## Session System — MANDATORY

Session logs live in `.claude/sessions/` (gitignored).

1. **Start of session:** Run `/session-start` — loads recent sessions + quality patterns
2. **After each significant change:** Update today's session file immediately
3. **End of session (code changed):** Run `/session-end` — writes quality analysis + updates patterns

### Self-Learning System
1. **Session logs** — what was done, decisions, outcomes
2. **Quality patterns** (`memory/quality_patterns.md`) — accumulated lessons
3. **Session-end analysis** — after each session, analyze what worked/failed
4. **Memory feedback entries** — corrections persist across conversations

## Safety Rules — NON-NEGOTIABLE

### Secrets & Keys Safety
- NEVER output WireGuard private keys, Vaultwarden admin tokens, or DB passwords
- NEVER commit .env files, private keys, or wg0.conf with real keys
- Always use .env.example with placeholder values for documentation

### Filesystem & Automation Safety
- Never `rm -rf` Docker volumes or /etc/wireguard
- Never modify .env directly without backup
- Never force push to main
- Never direct `docker build` — use skills only

### Production Protection
- Never target prod without explicit instruction
- Never restart WireGuard on prod without confirming active connections
- Always check `wg show` before config changes

## Code Patterns

- Docker configs: use named volumes, health checks, restart policies
- WireGuard: one config per peer, PostUp/PostDown for iptables
- Vaultwarden: environment-based config via docker-compose
- Secrets: .env files per environment, never in docker-compose directly
- See `.claude/rules/` for path-scoped rules

## Pre-Commit Checklist (MANDATORY)

- [ ] No secrets/keys in committed files
- [ ] .env.example updated if new env vars added
- [ ] Docker configs valid (docker-compose config)
- [ ] Firewall rules documented
- [ ] Session file updated

## Reference Docs (read on-demand)

| Doc | Purpose |
|-----|---------|
| `.claude/docs/architecture.md` | Services, ports, network topology |
| `.claude/docs/infrastructure.md` | Server setup, Docker, deploy state |
| `.claude/docs/database.md` | Vaultwarden DB, backups, credentials |

## Skills

| Skill | Purpose |
|-------|---------|
| `/commit` | Lint, check secrets, stage, commit |
| `/build-dev` | Deploy to dev environment |
| `/build-prod` | Deploy to production |
| `/test` | Run connectivity and health tests |
| `/review` | Code review + security audit |
| `/security-scan` | Grep-based security checks |
| `/logs` | View container/service logs |
| `/status` | Check containers, WireGuard peers, health |
| `/docs-update` | Update docs after changes |
| `/session-start` | Load context, start session |
| `/session-end` | Write session log, quality analysis |

## Agents

| Agent | Purpose | Model |
|-------|---------|-------|
| code-reviewer | Review configs against best practices | sonnet |
| security-auditor | Audit security: keys, ports, firewall | sonnet |
| debugger | Diagnose connectivity, container issues | opus |
| browser-inspector | Test Vaultwarden web UI | opus |

## Agent Teams vs Subagents

| Use Case | Approach |
|----------|----------|
| Full review (code + security) | Team: code-reviewer + security-auditor in parallel |
| Quick file lookup | Subagent: single search task |
| Debug connectivity issue | Team: debugger with full context |
| Check UI after deploy | Subagent: browser-inspector |

## Skill Self-Improvement
Skills are living documents. If outdated — update immediately. If new workflow — create skill.

## Plan Mode
Plans go in /plans/ as YYYYMMDD-HHMMSS-topic.md.
