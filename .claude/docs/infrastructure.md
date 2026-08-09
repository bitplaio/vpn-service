# Infrastructure

## Environments

| Environment | Branch | Server Path | Compose File | Domain |
|-------------|--------|-------------|--------------|--------|
| dev | dev | /root/vpn-server | docker-compose.yml | vault.halobolan.cc |
| prod | main | /opt/vpn-server | docker-compose.prod.yml | vault.halobolan.cc |

Dev and prod currently share the same droplet (157.230.98.224); prod compose is checked in for future split.

## Server Access

- **SSH:** `ssh vpn` (user `root`, key `~/key`)
- **GitHub:** https://github.com/bitplaio/vpn-service.git
- **Cloudflare Zero Trust:** team `bitplaio.cloudflareaccess.com`

## Docker Commands

### Dev
```bash
docker compose up -d
docker compose down
docker compose ps
docker compose logs -f cloudflared      # tunnel connection logs
docker compose logs -f vaultwarden
docker compose config
```

### Prod
```bash
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml logs -f
```

## Cloudflare Tunnel Management

```bash
# Tunnel connector logs (4 QUIC connections to CF edge expected)
docker logs cloudflared --tail 50

# Restart tunnel (token rotation, config change)
docker compose restart cloudflared

# Verify edge reachability
curl -sI https://vault.halobolan.cc/alive | grep cf-ray
```

Tunnel config is managed in Cloudflare dashboard (Networks → Tunnels → vaultwarden):
- Public hostname: `vault.halobolan.cc` → `http://vaultwarden:80`
- Token lives in `.env` as `CLOUDFLARE_TUNNEL_TOKEN`

## WireGuard Management

```bash
docker exec wireguard wg show
docker exec wireguard wg syncconf wg0 /config/wg_confs/wg0.conf
./scripts/add-peer.sh <peer-name>
```

## Common Server Tasks

```bash
# Health
curl -s http://localhost:80/alive       # vaultwarden (via container only)
docker exec wireguard wg show
docker logs cloudflared --tail 20 | grep 'Registered tunnel'

# Backup Vaultwarden data
docker run --rm -v vpn-server_vaultwarden-data:/data -v ~/backups:/backup alpine \
  tar czf /backup/vw-$(date +%Y%m%d-%H%M%S).tar.gz -C /data .
```

## Automatic Updates

Daily unattended image update via `scripts/auto-update.sh` + host cron.

- **Cron:** `0 4 * * * /root/vpn-server/scripts/auto-update.sh` (daily 04:00 server time)
- **Scope:** updates **vaultwarden + cloudflared** only. WireGuard and Unbound are
  deliberately excluded so routine updates never drop VPN sessions or peer DNS.
- **Flow:** backup Vaultwarden volume → `docker compose pull` → `up -d` →
  health check → prune dangling images → rotate backups (keeps last 7).
- **Safety:** `flock` prevents overlapping runs; a failed backup aborts the update.
- **Log:** `/var/log/vpn-auto-update.log`
- **Backups:** auto runs write `~/backups/vw-auto-*.tar.gz`; manual/pre-deploy use `vw-*`.

```bash
# Run manually / on demand
/root/vpn-server/scripts/auto-update.sh

# Tail the update log
tail -f /var/log/vpn-auto-update.log

# Inspect / edit schedule
crontab -l
```

Tunables via env (override before invoking): `SERVICES`, `KEEP_BACKUPS`, `BACKUP_DIR`,
`COMPOSE_FILE`. Note: this intentionally relies on the `:latest` tag — daily `pull`
is what keeps the stack current; every run backs up first as the safety net.

## Firewall Rules (Host)

Inbound ports after adding the parallel proxy stack:

| Port | Service | Reachable from |
|------|---------|----------------|
| 443/udp | WireGuard | anywhere (ufw rule) |
| 22/tcp | SSH | **only 10.2.0.0/24**, i.e. only through the WireGuard tunnel |
| 8443/udp | Hysteria2 | anywhere (Docker DNAT) |
| 443/tcp | Xray VLESS+REALITY | anywhere (Docker DNAT) |

80/tcp remains free and closed. Vaultwarden is still reached only through the
outbound CF Tunnel and publishes no inbound port.

### SSH depends on WireGuard — read before touching either

The SSH rule allows source `10.2.0.0/24` only. A connection arriving through the
WireGuard tunnel is NATed to the wg container's docker address in that subnet, so
it passes; a connection from the open internet does not. **If WireGuard stops, SSH
access is lost** and the only way back in is the DigitalOcean web console. Never
restart or reconfigure the wireguard service without that console at hand.

### ufw does not govern the container ports

Docker publishes ports by inserting DNAT rules into the `DOCKER` chain, which is
traversed **before** ufw's filter rules. `8443/udp` and `443/tcp` therefore became
world-reachable the moment the containers started, regardless of ufw's
default-deny policy. Adding `ufw allow 8443/udp` / `ufw allow 443/tcp` documents
intent but changes nothing.

Any real restriction on those two ports (rate limiting, source blocking, abuse
response) must go into the **`DOCKER-USER`** iptables chain, which is evaluated
before Docker's own rules:

```bash
# Example — drop a specific abusive source from the proxy ports
iptables -I DOCKER-USER -s <addr> -p udp --dport 8443 -j DROP
iptables -I DOCKER-USER -s <addr> -p tcp --dport 443  -j DROP
```

Access control for the proxies is otherwise enforced in-application: a Hysteria2
password and per-device Xray UUIDs. There is no management panel on this box by
design — one would add an authenticated web surface next to a password manager.

## Safety Rules

- Never modify .env without creating .env.backup first
- Never delete Docker volumes without backup
- Always use `docker compose config` to validate before deploying
- Keep WireGuard private keys ONLY in .env or wg0.conf (both gitignored)
- Cloudflare Tunnel token is a secret — treat like a private key. If leaked, rotate by deleting+recreating the tunnel in CF dashboard.
- CF Access policy must remain restricted to `/admin` only; opening it wider breaks Bitwarden Chrome extension and mobile clients (they cannot navigate the email-OTP browser flow).
