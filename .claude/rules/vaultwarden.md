---
paths:
  - "**/vaultwarden/**"
  - "**/vw-*"
---

# Vaultwarden Rules

- NEVER expose admin panel without ADMIN_TOKEN protection
- ALWAYS disable SIGNUPS_ALLOWED after initial user creation
- NEVER output or log the ADMIN_TOKEN
- ALWAYS configure DOMAIN env var correctly for the deployment environment
- ALWAYS enable WebSocket support (WEBSOCKET_ENABLED=true) for live sync
- ALWAYS use HTTPS in production (via Caddy reverse proxy)
- NEVER access the SQLite database without creating a backup first
- ALWAYS use read-only mode for diagnostic queries
- Keep Vaultwarden image updated for security patches
- Configure LOG_LEVEL appropriately (warn for prod, info for dev)
- Set SENDS_ALLOWED and EMERGENCY_ACCESS_ALLOWED based on requirements
