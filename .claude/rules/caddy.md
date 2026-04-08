---
paths:
  - "caddy/**"
  - "**/Caddyfile"
---

# Caddy Rules

- ALWAYS use automatic HTTPS (Let's Encrypt) in production
- ALWAYS configure proper reverse proxy headers (X-Real-IP, X-Forwarded-For, X-Forwarded-Proto)
- ALWAYS enable WebSocket proxying for Vaultwarden (/notifications/hub)
- NEVER expose Caddy admin API externally
- Configure proper timeouts for WebSocket connections
- Use `encode gzip` for compression
- Set appropriate HSTS headers
- Log to stdout for Docker log collection
