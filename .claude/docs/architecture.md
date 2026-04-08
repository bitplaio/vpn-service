# Architecture

## Services

| Service | Image | Dev Port | Prod Port | Description |
|---------|-------|----------|-----------|-------------|
| wireguard | linuxserver/wireguard | 51820/udp | 51820/udp | VPN server |
| vaultwarden | vaultwarden/server | 8080 (http), 3012 (ws) | 443 (via reverse proxy) | Password manager |
| caddy | caddy:2 | — | 443, 80 | Reverse proxy + auto-TLS (prod only) |

## Network Topology

```
Internet
  │
  ├── :51820/udp → WireGuard VPN
  │     └── VPN subnet: 10.10.0.0/24
  │           ├── 10.10.0.1 — server
  │           └── 10.10.0.2+ — peers/clients
  │
  └── :443 → Caddy (prod) → Vaultwarden :8080
        └── WebSocket → :3012
```

## Docker Network

- `vpn-net` — bridge network connecting all services
- WireGuard needs `NET_ADMIN` and `SYS_MODULE` capabilities
- WireGuard needs `/lib/modules` mounted for kernel module access

## Volumes

| Volume | Container | Mount Point | Purpose |
|--------|-----------|-------------|---------|
| wg-config | wireguard | /config | WireGuard configs and keys |
| vw-data | vaultwarden | /data | Vaultwarden SQLite DB + attachments |
| caddy-data | caddy | /data | TLS certificates |
| caddy-config | caddy | /config | Caddy configuration |

## Data Flow

1. **VPN Clients** connect via WireGuard protocol (UDP 51820)
2. **Vaultwarden** accessible directly in dev (8080), via Caddy reverse proxy in prod (443)
3. **Caddy** handles TLS termination and auto-renewal via Let's Encrypt (prod)

## Key Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Dev environment |
| `docker-compose.prod.yml` | Production environment |
| `.env` | Environment variables (secrets) |
| `.env.example` | Template for .env |
| `wireguard/` | WireGuard config templates |
| `caddy/Caddyfile` | Reverse proxy config |
| `scripts/` | Helper scripts (add-peer, backup, etc.) |
| `backups/` | Backup storage (gitignored) |
