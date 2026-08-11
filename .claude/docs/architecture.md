# Architecture

## Services

| Service | Image | Public Port | Description |
|---------|-------|-------------|-------------|
| wireguard | linuxserver/wireguard | 443/udp | VPN server (UDP on 443 for firewall bypass) |
| vaultwarden | vaultwarden/server | — (internal :80 only) | Password manager, integrated WebSocket |
| cloudflared | cloudflare/cloudflared | — (outbound only) | Cloudflare Tunnel connector |
| unbound | mvance/unbound | — (internal :53) | Recursive DNS for VPN peers |

No public HTTP/HTTPS ports — Vaultwarden reached only through Cloudflare Tunnel,
and since 2026-08-10 only from the VPN's egress IP (see WAF rule below).

## Network Topology

```
Internet
  │
  ├── :443/udp ──────────────────────────► WireGuard VPN
  │                                           └── VPN subnet 10.13.13.0/24
  │
  └── vault.halobolan.cc (CF DNS, proxied)
        ▲
        │ Cloudflare Edge
        │   ├── WAF custom rule → Block unless ip.src == 157.230.98.224
        │   ├── /admin         → CF Access (email OTP, only bitplaio@gmail.com)
        │   └── /*             → bypass
        │
        ▼ tunnel (QUIC, outbound from server)
      cloudflared (10.2.0.5)
        │
        └── http://vaultwarden:80 (10.2.0.4) — integrated WebSocket
```

Direct IP access blocked at UFW (80/tcp, 443/tcp closed).

## Docker Network

- `vpn-net` (bridge, 10.2.0.0/24) — all services
- WireGuard needs `NET_ADMIN`, `SYS_MODULE`, `/lib/modules:ro`

## Volumes

| Volume | Container | Mount | Purpose |
|--------|-----------|-------|---------|
| wireguard-config | wireguard | /config | Peer configs + server keys |
| vaultwarden-data | vaultwarden | /data | SQLite DB + attachments |

Caddy volumes (`caddy-data`, `caddy-config`) removed in CF Tunnel migration — TLS now terminated at CF edge.

## Cloudflare Setup

- **Domain:** `halobolan.cc` on Cloudflare DNS
- **Tunnel:** named `vaultwarden`, ID `39a25257-351e-4aac-bd2c-78c997849f56`
- **Route:** `vault.halobolan.cc` → `http://vaultwarden:80`
- **Access app:** `Vaultwarden Admin`, protects `/admin` path only
- **Access policy:** `Only me`, allow `bitplaio@gmail.com` via One-time PIN
- **Zero Trust team:** `bitplaio.cloudflareaccess.com`
- **WAF custom rule:** `vault: only VPN` — see below

### WAF rule — access restricted to the VPN (2026-08-10)

Security → WAF → Custom rules, placed **first**:

```
(http.host eq "vault.halobolan.cc" and ip.src ne 157.230.98.224)
→ Block
```

`157.230.98.224` is the droplet's own public address, which is also the egress
IP of every WireGuard peer. So the rule reads "only clients inside the VPN".
The tunnel is IPv4-only, so there is no IPv6 egress to cover.

Why the filtering lives at the edge and not on the host: 80/tcp and 443/tcp are
closed in UFW and traffic arrives through the **outbound** tunnel, so the server
never sees an inbound connection to filter.

Why `Block` and not `Managed Challenge`: an interactive challenge breaks the
Bitwarden desktop app, browser extension and mobile clients. `Block` returns a
plain 403, and from inside the VPN the request never reaches it.

The `http.host` condition is mandatory — WAF custom rules are zone-wide.

Consequences to keep in mind:
- The vault is unreachable from any device not on the VPN. That is the point,
  but on mobile it means "WireGuard first, then Bitwarden".
- Every VPN peer gets in; they all share one egress address, so this cannot
  distinguish between peers.
- **If the droplet's IP ever changes, the rule locks you out too.** The
  Cloudflare dashboard is unaffected, so the break-glass move is to toggle the
  rule off from any device.

## Data Flow

1. **VPN clients** → UDP 443 → WireGuard → tunnel out via DNS=unbound
2. **Browser/extension** → `vault.halobolan.cc` → CF Edge → tunnel → vaultwarden:80
3. **Admin login** → adds CF Access OTP layer on top of vaultwarden ADMIN_TOKEN

## Key Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Dev compose (full stack including cloudflared) |
| `docker-compose.prod.yml` | Prod compose (mirrors dev structurally) |
| `.env` | Secrets: ADMIN_TOKEN, CLOUDFLARE_TUNNEL_TOKEN, WireGuard env |
| `.env.example` | Template (sanitized) |
| `unbound/unbound.conf` | DNS recursor config |
