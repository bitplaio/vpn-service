# Infrastructure

## Environments

| Environment | Branch | Server Path | Compose File | Domain |
|-------------|--------|-------------|--------------|--------|
| dev | dev | ~/vpn-server | docker-compose.yml | localhost |
| prod | main | /opt/vpn-server | docker-compose.prod.yml | (настроить домен) |

## Server Access

- **SSH:** `ssh vpn` (configured in ~/.ssh/config)
- **GitHub:** https://github.com/bitplaio/vpn-service.git
- **Docker:** pre-installed on droplet

## Docker Commands

### Dev
```bash
docker compose up -d                    # Start all services
docker compose down                     # Stop all services
docker compose ps                       # Check status
docker compose logs -f wireguard        # WireGuard logs
docker compose logs -f vaultwarden      # Vaultwarden logs
docker compose config                   # Validate config
```

### Prod
```bash
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f
```

## Container Naming

| Service | Container Name |
|---------|---------------|
| wireguard | vpn-wireguard |
| vaultwarden | vpn-vaultwarden |
| caddy | vpn-caddy |

## WireGuard Management

```bash
# Show active peers and handshakes
docker exec vpn-wireguard wg show

# Generate keypair
wg genkey | tee privatekey | wg pubkey > publickey

# Add peer (use script)
./scripts/add-peer.sh <peer-name>

# Reload config without restart
docker exec vpn-wireguard wg syncconf wg0 /config/wg_confs/wg0.conf
```

## Log Viewing

```bash
# Last 100 lines of any service
docker compose logs --tail=100 <service>

# Follow logs in real-time
docker compose logs -f <service>

# System logs (host)
journalctl -u docker -n 100
```

## Common Server Tasks

```bash
# Health check
curl -s http://localhost:8080/alive     # Vaultwarden health
docker exec vpn-wireguard wg show      # WireGuard status

# Resource usage
docker stats --no-stream

# Disk space (volumes)
docker system df -v

# Backup Vaultwarden data
./scripts/backup.sh
```

## Deploy State

Deploy state is tracked in `.claude/docs/deploy-state.json` (created on first deploy).

Format:
```json
{
  "dev": {
    "last_deploy": "ISO timestamp",
    "commit": "git hash",
    "services_rebuilt": ["list"],
    "status": "ok|error"
  },
  "prod": { ... }
}
```

## Firewall Rules (Host)

```bash
# Required open ports:
# 51820/udp — WireGuard VPN
# 443/tcp   — Vaultwarden HTTPS (prod only)
# 80/tcp    — Caddy HTTP->HTTPS redirect (prod only)
# 22/tcp    — SSH (management)

# UFW example:
ufw allow 51820/udp
ufw allow 443/tcp
ufw allow 80/tcp
ufw allow 22/tcp
ufw enable
```

## Safety Rules

- Never modify .env without creating .env.backup first
- Never delete Docker volumes without backup
- Always use `docker compose config` to validate before deploying
- Keep WireGuard private keys ONLY in .env or wg0.conf (both gitignored)
