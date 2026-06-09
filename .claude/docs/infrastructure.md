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

After CF Tunnel migration — only two inbound ports:

```bash
# Required:
# 22/tcp    — SSH (rate-limited)
# 443/udp   — WireGuard VPN

# UFW state:
ufw allow 51820/udp comment 'WireGuard VPN'  # or 443/udp if using port 443
ufw limit 22/tcp
ufw enable
```

80/tcp and 443/tcp are deliberately **closed** — Vaultwarden is reached only through outbound CF Tunnel.

## Safety Rules

- Never modify .env without creating .env.backup first
- Never delete Docker volumes without backup
- Always use `docker compose config` to validate before deploying
- Keep WireGuard private keys ONLY in .env or wg0.conf (both gitignored)
- Cloudflare Tunnel token is a secret — treat like a private key. If leaked, rotate by deleting+recreating the tunnel in CF dashboard.
- CF Access policy must remain restricted to `/admin` only; opening it wider breaks Bitwarden Chrome extension and mobile clients (they cannot navigate the email-OTP browser flow).
