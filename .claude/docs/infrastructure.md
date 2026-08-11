# Infrastructure

## Environments

| Environment | Branch | Server Path | Compose File | Domain |
|-------------|--------|-------------|--------------|--------|
| dev | dev | /root/vpn-server | docker-compose.yml | vault.halobolan.cc |
| prod | main | /opt/vpn-server | docker-compose.prod.yml | vault.halobolan.cc |

Dev and prod currently share the same droplet (157.230.98.224); prod compose is checked in for future split.

## Server Access

- **SSH:** `ssh vpn` (user `root`, key `~/.ssh/satoshihero-prod-20260809`)
  Always use the `vpn` alias. `ssh root@157.230.98.224` bypasses the `Host vpn`
  block in `~/.ssh/config` and therefore its `IdentityFile`, and fails with
  `Permission denied (publickey)` even though access is fine.
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

## Edge access control — vault is VPN-only

Since 2026-08-10 a WAF custom rule blocks `vault.halobolan.cc` from every source
except the VPN egress IP. Full rationale in `architecture.md`; operational notes:

```bash
# Verify from a VPN-connected machine — A/B without dropping the tunnel.
# --interface <LAN-IP> routes around the tunnel on the same box.
curl -s -o /dev/null -w "vpn=%{http_code}\n"  https://vault.halobolan.cc/alive
curl -s -o /dev/null -w "open=%{http_code}\n" --interface "$(ipconfig getifaddr en0)" \
     https://vault.halobolan.cc/alive
# expected: vpn=200  open=403
```

Verified 2026-08-10 on `/`, `/alive`, `/api/config`, `/identity/accounts/prelogin`.
A 403 carrying `server: cloudflare` and no application body means the edge blocked
it before the tunnel. `/admin` still redirects to CF Access — the two layers stack.

**Break-glass:** disable the rule in the Cloudflare dashboard. The dashboard is
not behind the rule, so any device works. Needed if the droplet's public IP
changes — the rule would then lock out the VPN as well.

## WireGuard Management

```bash
docker exec wireguard wg show                      # full dump prints peer endpoint IPs — avoid
docker exec wireguard wg show wg0 latest-handshakes
docker exec wireguard wg syncconf wg0 /config/wg_confs/wg0.conf
```

### Peers — one key per device, never shared

| Tunnel IP | Key prefix | Device | Origin |
|-----------|-----------|--------|--------|
| 10.13.13.2 | `YrIYfP` | Mac | peer1, image-generated |
| 10.13.13.3 | `SWtWeb` | third client | peer2, image-generated |
| 10.13.13.4 | `Ci8ecg` | phone | `peer_phone`, added by hand 2026-08-11 |

**A key must never be used by two devices.** WireGuard tracks exactly one
endpoint per public key — the source of the last packet received. Two devices
sharing a key take turns overwriting it, and all return traffic follows the
latest writer, so each device loses whatever arrives during the other's turn.
Symptom: ping shows 100% loss while HTTP still completes, alternating on the
period of the peers' keepalive. That is what "everything lags" turned out to be
on 2026-08-11 — the phone and the Mac were both on `YrIYfP`/10.13.13.2.

### Adding a peer without downtime

Raising `PEERS` and recreating the container works but drops the tunnel, and SSH
only arrives through it. `wg set` is additive, applies instantly and cannot
disturb existing peers:

```bash
# inside the container; keys never leave it
docker exec wireguard sh -c 'umask 077 && mkdir -p /config/peer_X && cd /config/peer_X && \
  wg genkey | tee privatekey | wg pubkey > publickey && wg genpsk > presharedkey'
docker exec wireguard sh -c 'wg set wg0 peer "$(cat /config/peer_X/publickey)" \
  preshared-key /config/peer_X/presharedkey allowed-ips 10.13.13.N/32'
# then append the same [Peer] block to /config/wg_confs/wg0.conf so a restart keeps it,
# and confirm the file still parses:
docker exec wireguard wg-quick strip wg0 > /dev/null && echo ok
```

Hand the config to the device as a QR **from your own terminal**, never through
a tool transcript — the file contains the device's private key:

```bash
ssh vpn 'docker exec wireguard sh -c "qrencode -t ansiutf8 < /config/peer_phone/peer_phone.conf"'
```

**Caveat:** a hand-added peer lives in `wg0.conf` only. Changing `PEERS` re-renders
that file from `/config/templates/` and would silently drop it — re-add it in the
same maintenance window.

Peers are otherwise added by raising `PEERS` in `.env` and recreating the container —
the linuxserver image regenerates configs itself. There is no `add-peer.sh`.
Note that **any** change to `PEERS` re-renders configs from
`/config/templates/{server,peer}.conf`, wiping hand edits to the live files;
MTU and MSS-clamp are already mirrored into those templates.

## Common Server Tasks

```bash
# Health
curl -s http://10.2.0.4/alive           # vaultwarden — port 80 is NOT published
                                        # on the host, so localhost:80 fails
docker exec wireguard wg show wg0 latest-handshakes
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

## Telemetry — who connected, and where the lag was (2026-08-10)

Two collectors write JSONL, one line per sample; `vpn-analyze.py` joins them.

| Where | What | Cadence | Log |
|-------|------|---------|-----|
| droplet | `scripts/vpn-telemetry.py` via cron | 6 samples/min | `/var/log/vpn-telemetry/YYYY-MM-DD.jsonl` |
| Mac | `scripts/vpn-probe.py` via launchd | every 20 s | `~/Library/Logs/vpn-probe/YYYY-MM-DD.jsonl` |

Both keep 14 days and rotate themselves.

```bash
scripts/vpn-telemetry-install.sh server    # cron on the droplet
scripts/vpn-telemetry-install.sh client    # launchd agent + ~/bin/vpn-lag
scripts/vpn-telemetry-install.sh status    # both sides
scripts/vpn-telemetry-install.sh stop      # unload the Mac agent

scripts/vpn-analyze.py                     # today's report, pulls server log over ssh
scripts/vpn-analyze.py --date 2026-08-11
~/bin/vpn-lag youtube буферит              # mark a lag while it happens
```

**Server side** identifies devices by tunnel IP via `peer-labels.conf`
(`10.13.13.2=mac`, `10.13.13.3=phone`) and records per-peer handshake age and
up/down rate, load/steal/conntrack, wg0 error+drop deltas, DNS latency and
uplink RTT/loss.

**Client side** measures three ping legs every sample — Mac→router, Mac→droplet
outside the tunnel, Mac→10.13.13.1 inside it — plus DNS and HTTP TTFB. Which leg
degrades is what assigns blame: router → Wi-Fi, outside-tunnel → ISP, only-inside
→ WireGuard or the server, DNS alone → unbound, TTFB alone → the site or CF edge.

Gotchas worth remembering:
- **Peer rate direction is inverted in `wg dump`.** `rx` is what the server
  received *from* the peer — the device's **upload**; `tx` is its download.
- **A random subdomain does not measure DNS recursion.** `aggressive-nsec: yes`
  lets unbound synthesise NXDOMAIN from cache in ~3 ms without a packet leaving.
  Both probes rotate over real domains instead.
- **The Mac agent cannot run from `~/Documents`.** macOS TCC denies launchd
  agents there (`Operation not permitted`), so the installer copies the script to
  `~/Library/Application Support/vpn-probe/` and injects `SERVERURL`/`PEERDNS`/
  `INTERNAL_SUBNET` from `.env` into the plist as env vars.
- Cron holds a `flock` for ~50 s of every minute; a manual run during that window
  exits silently rather than double-writing.

Privacy: peer public keys are never written, and endpoints are masked to /24 —
enough to see a device roam between networks, not enough to be a location log.

## Firewall Rules (Host)

After CF Tunnel migration — only two inbound ports. Actual `ufw status` as verified
on 2026-08-09:

```
443/udp   ALLOW IN   Anywhere            # WireGuard VPN
22/tcp    ALLOW IN   10.2.0.0/24         # SSH only over the WireGuard tunnel
```

80/tcp and 443/tcp are deliberately **closed** — Vaultwarden is reached only through outbound CF Tunnel.

### SSH depends on WireGuard — read before touching either

SSH is **not** merely rate-limited; it is reachable only from `10.2.0.0/24`. A session
arriving through the WireGuard tunnel is NATed to the wg container's address in that
subnet and passes; a connection from the open internet does not. **If WireGuard stops,
SSH access is lost** and the only way back in is the DigitalOcean web console.

Consequences for any future work:
- Never `docker compose down` — it takes WireGuard with it. Stop services by name.
- When bringing up individual services, pass `--no-deps` so compose cannot decide to
  recreate wireguard as a dependency.
- Have the DO web console open before restarting or reconfiguring wireguard.

## Safety Rules

- Never modify .env without creating .env.backup first
- Never delete Docker volumes without backup
- Always use `docker compose config` to validate before deploying
- Keep WireGuard private keys ONLY in .env or wg0.conf (both gitignored)
- Cloudflare Tunnel token is a secret — treat like a private key. If leaked, rotate by deleting+recreating the tunnel in CF dashboard.
- CF Access policy must remain restricted to `/admin` only; opening it wider breaks Bitwarden Chrome extension and mobile clients (they cannot navigate the email-OTP browser flow). The same reasoning is why the VPN-only restriction is a WAF `Block` rule rather than a challenge or a zone-wide Access app.
- The WAF rule hardcodes `157.230.98.224`. Anything that changes the droplet's public address (rebuild, floating IP) must update the rule in the same maintenance window, or access is lost from the VPN too.
