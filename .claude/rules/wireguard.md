---
paths:
  - "wireguard/**"
  - "**/wg*.conf"
---

# WireGuard Rules

- NEVER commit files containing real private keys
- ALWAYS generate keys via `wg genkey | tee privatekey | wg pubkey > publickey`
- ALWAYS include PostUp/PostDown iptables rules for NAT:
  ```
  PostUp = iptables -A FORWARD -i %i -j ACCEPT; iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
  PostDown = iptables -D FORWARD -i %i -j ACCEPT; iptables -t nat -D POSTROUTING -o eth0 -j MASQUERADE
  ```
- ALWAYS assign unique IPs within the VPN subnet (10.10.0.0/24)
- Server is 10.10.0.1, peers start from 10.10.0.2
- Each peer gets its own config file
- AllowedIPs on server side = peer's specific IP (/32)
- AllowedIPs on client side = 0.0.0.0/0 for full tunnel, or specific subnets for split tunnel
- ALWAYS set PersistentKeepalive = 25 for peers behind NAT
- Check `wg show` before modifying config on a running server
- Use `wg syncconf` for hot-reload instead of restarting the container
