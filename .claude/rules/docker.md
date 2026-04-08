---
paths:
  - "docker-compose*.yml"
  - "Dockerfile*"
  - ".env*"
---

# Docker Rules

- NEVER hardcode secrets in docker-compose files — use ${VAR} referencing .env
- ALWAYS define health checks for every service
- ALWAYS use restart policy: `unless-stopped`
- ALWAYS use named volumes for persistent data
- ALWAYS pin image versions (e.g., `vaultwarden/server:1.30.0`, never `:latest`)
- NEVER expose ports beyond what's documented in architecture.md
- ALWAYS validate config with `docker compose config` before committing
- NEVER use `privileged: true` unless the service specifically requires it (only WireGuard)
- Use `cap_add` with minimal capabilities instead of privileged where possible
- Keep dev and prod compose files in sync structurally — differences only in ports, volumes, and env vars
