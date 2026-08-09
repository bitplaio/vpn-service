# Architecture

## Services

| Service | Image | Public Port | Description |
|---------|-------|-------------|-------------|
| wireguard | linuxserver/wireguard | 443/udp | VPN server (UDP on 443 for firewall bypass) |
| vaultwarden | vaultwarden/server | — (internal :80 only) | Password manager, integrated WebSocket |
| cloudflared | cloudflare/cloudflared | — (outbound only) | Cloudflare Tunnel connector |
| unbound | mvance/unbound | — (internal :53) | DNS for VPN peers (vpn-net only) |
| hysteria | tobyxdd/hysteria:v2.12.1 | 8443/udp | Hysteria2 proxy, QUIC, BBR congestion control |
| xray | ghcr.io/xtls/xray-core:26.7.28 | 443/tcp | VLESS + REALITY + XTLS-Vision, TCP fallback |
| unbound-proxy | klutchell/unbound:1.25.2 | — (internal :53) | Dedicated resolver for proxy-net |

Vaultwarden is still reached only through the Cloudflare Tunnel and publishes no
inbound port. 80/tcp remains free.

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
        │   ├── /admin       → CF Access (email OTP, only bitplaio@gmail.com)
        │   └── /*           → bypass
        │
        ▼ tunnel (QUIC, outbound from server)
      cloudflared (10.2.0.5)
        │
        └── http://vaultwarden:80 (10.2.0.4) — integrated WebSocket
```

Direct IP access blocked at UFW (80/tcp, 443/tcp closed).

## Docker Network

- `vpn-net` (bridge, 10.2.0.0/24) — wireguard, vaultwarden, cloudflared, unbound
- `proxy-net` (bridge, 10.4.0.0/24) — hysteria (.20), xray (.30), unbound-proxy (.100)
- WireGuard needs `NET_ADMIN`, `SYS_MODULE`, `/lib/modules:ro`

### Why two networks, and why two resolvers

The proxy stack is deliberately kept out of `vpn-net`. Two things live there that a
proxy user must never reach: Vaultwarden at 10.2.0.4, which has no authentication of
its own and is protected only by Cloudflare Access at the edge, and SSH, which ufw
allows from `10.2.0.0/24`. A proxy container inside that subnet would hand any
credential holder both.

The first draft of this design shared one `unbound` across both networks so that DNS
would stay self-hosted. Review caught that this reopened the hole through the back
door: the resolver itself had a live address in `10.2.0.0/24`, and the proxy ACLs
constrain what a *client* may dial, not where the *unbound process* can go. Since the
resolver handles fully attacker-controlled input — any credential holder can make it
query a domain served by their own authoritative nameserver — it is exactly the wrong
process to straddle a trust boundary. Hence a second, dedicated resolver that has no
leg in `vpn-net` at all, running a maintained image with rate limits and full
recursion from the root.

Defence in depth on top of the segmentation:
- Hysteria2 `acl.inline` and Xray `routing.rules` both reject RFC1918, link-local,
  loopback, IPv6 equivalents and **the droplet's own public IP** (needed separately:
  `geoip:private` does not cover it, and ufw permits SSH from within the docker subnet).
- The single deliberate exception is the resolver, scoped to `10.4.0.100:53`.
- Ordering matters in both engines — first match wins, so the exception precedes the
  rejects and `direct(all)` comes last.

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
