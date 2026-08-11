#!/usr/bin/env python3
"""Server-side VPN telemetry collector.

Invoked from cron once a minute; takes SAMPLES snapshots INTERVAL seconds apart
and appends one JSON object per snapshot to /var/log/vpn-telemetry/YYYY-MM-DD.jsonl.

Each snapshot answers three questions:
  who was connected      — per-peer handshake age, labelled mac/phone by tunnel IP
  what they were doing   — per-peer rx/tx rate from wg byte counters
  was the server at fault — load, CPU steal, conntrack, DNS latency, uplink RTT/loss

Never logs peer public keys or full endpoint addresses: peers are identified by
their tunnel IP and endpoints are masked to /24 (enough to see roaming, not
enough to be a location log).
"""

import json
import os
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(os.environ.get("LOG_DIR", "/var/log/vpn-telemetry"))
LABELS_FILE = Path(os.environ.get("LABELS", "/root/vpn-server/peer-labels.conf"))
STATE_FILE = Path(os.environ.get("STATE", "/run/vpn-telemetry.state"))
LOCK_FILE = Path(os.environ.get("LOCK", "/run/vpn-telemetry.lock"))
SAMPLES = int(os.environ.get("SAMPLES", "6"))
INTERVAL = int(os.environ.get("INTERVAL", "10"))
KEEP_DAYS = int(os.environ.get("KEEP_DAYS", "14"))
WG_CONTAINER = os.environ.get("WG_CONTAINER", "wireguard")
DNS_ADDR = os.environ.get("DNS_ADDR", "10.2.0.100")
PING_TARGET = os.environ.get("PING_TARGET", "1.1.1.1")


def run(cmd, timeout=10):
    """Run a command, return stdout or '' — telemetry must never abort the run."""
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        return p.stdout
    except Exception:
        return ""


def load_labels():
    """tunnel-ip -> friendly name, e.g. 10.13.13.2=mac"""
    labels = {}
    if LABELS_FILE.exists():
        for line in LABELS_FILE.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if "=" in line:
                ip, name = line.split("=", 1)
                labels[ip.strip()] = name.strip()
    return labels


def mask_endpoint(ep):
    """1.2.3.4:51820 -> 1.2.3.0/24 ; keeps roaming visible, drops precision."""
    if not ep or ep == "(none)":
        return None
    host = ep.rsplit(":", 1)[0].strip("[]")
    parts = host.split(".")
    if len(parts) == 4:
        return ".".join(parts[:3]) + ".0/24"
    return "ipv6"


def wg_peers():
    """Parse `wg show wg0 dump`, skipping line 1 — it holds the server private key."""
    out = run(["docker", "exec", WG_CONTAINER, "wg", "show", "wg0", "dump"])
    peers = {}
    for line in out.splitlines()[1:]:
        f = line.split("\t")
        if len(f) < 8:
            continue
        tun_ip = f[3].split("/")[0].split(",")[0]
        peers[tun_ip] = {
            "endpoint": mask_endpoint(f[2]),
            "handshake": int(f[4] or 0),
            "rx": int(f[5] or 0),
            "tx": int(f[6] or 0),
        }
    return peers


def wg_iface():
    """wg0 error/drop counters — a rising tx_drop means the tunnel is shedding packets."""
    out = run(["docker", "exec", WG_CONTAINER, "ip", "-s", "-j", "link", "show", "wg0"])
    try:
        st = json.loads(out)[0]["stats64"]
        return {
            "rx_err": st["rx"]["errors"],
            "rx_drop": st["rx"]["dropped"],
            "tx_err": st["tx"]["errors"],
            "tx_drop": st["tx"]["dropped"],
        }
    except Exception:
        return {}


def cpu_times():
    line = Path("/proc/stat").read_text().split("\n", 1)[0].split()
    v = [int(x) for x in line[1:11]]
    return {"total": sum(v), "idle": v[3] + v[4], "steal": v[7]}


def host_stats():
    load1 = float(Path("/proc/loadavg").read_text().split()[0])
    mem = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k, _, v = line.partition(":")
        mem[k] = int(v.split()[0])
    try:
        ct = int(Path("/proc/sys/net/netfilter/nf_conntrack_count").read_text())
    except Exception:
        ct = None
    return {
        "load1": load1,
        "mem_avail_mb": mem.get("MemAvailable", 0) // 1024,
        "conntrack": ct,
    }


DIG_TIME = re.compile(r";; Query time: (\d+) msec")


def dig_ms(name, timeout=5):
    out = run(
        ["dig", "+tries=1", f"+time={timeout}", f"@{DNS_ADDR}", name, "A"],
        timeout=timeout + 3,
    )
    m = DIG_TIME.search(out)
    return int(m.group(1)) if m else None


# Rotated real names, not a random subdomain: `aggressive-nsec` lets unbound
# synthesise NXDOMAIN straight from cache, so a random label measures nothing
# (3 ms, never touching the network). Real domains cycle in and out of cache and
# reflect what resolution actually costs a peer.
DOMAINS = [
    "github.com", "youtube.com", "instagram.com", "telegram.org", "wikipedia.org",
    "reddit.com", "netflix.com", "spotify.com", "twitch.tv", "vk.com",
    "apple.com", "icloud.com", "amazon.com", "ebay.com", "aliexpress.com",
    "booking.com", "airbnb.com", "tripadvisor.com", "yandex.ru", "ozon.ru",
    "nytimes.com", "bbc.co.uk", "theguardian.com", "medium.com", "substack.com",
    "stackoverflow.com", "gitlab.com", "docker.com", "npmjs.com", "pypi.org",
    "protonmail.com", "signal.org", "mozilla.org", "duckduckgo.com", "wise.com",
    "revolut.com", "paypal.com", "steampowered.com", "epicgames.com", "discord.com",
    "zoom.us", "slack.com", "notion.so", "figma.com", "dropbox.com",
    "linkedin.com", "x.com", "facebook.com", "whatsapp.com", "tiktok.com",
]


def dns_probe():
    """Hot-cache baseline plus one rotated real domain."""
    name = random.choice(DOMAINS)
    cached = dig_ms("cloudflare.com")
    lookup = dig_ms(name)
    return {
        "cache_ms": cached,
        "lookup_ms": lookup,
        "name": name,
        "fail": int(cached is None) + int(lookup is None),
    }


PING_STATS = re.compile(r"(\d+)% packet loss")
PING_RTT = re.compile(r"= [\d.]+/([\d.]+)/[\d.]+/([\d.]+) ms")


def ping_probe():
    out = run(["ping", "-c", "3", "-i", "0.2", "-W", "2", PING_TARGET], timeout=8)
    loss = PING_STATS.search(out)
    rtt = PING_RTT.search(out)
    return {
        "loss": int(loss.group(1)) if loss else 100,
        "rtt_ms": float(rtt.group(1)) if rtt else None,
        "jitter_ms": float(rtt.group(2)) if rtt else None,
    }


def read_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def write_state(state):
    try:
        STATE_FILE.write_text(json.dumps(state))
    except Exception:
        pass


def rate_kbps(cur, prev, dt):
    if prev is None or cur < prev or dt <= 0:
        return 0.0
    return round((cur - prev) * 8 / 1000 / dt, 1)


def sample(prev, now):
    dt = now - prev.get("ts", now)
    peers_now = wg_peers()
    labels = load_labels()
    prev_peers = prev.get("peers", {})

    peers = []
    for ip, p in sorted(peers_now.items()):
        old = prev_peers.get(ip, {})
        hs_age = int(now - p["handshake"]) if p["handshake"] else None
        peers.append(
            {
                "id": labels.get(ip, ip),
                "ip": ip,
                # WireGuard rekeys every ~2 min while traffic flows; >180s idle.
                "online": hs_age is not None and hs_age < 180,
                "hs_age": hs_age,
                # wg counters are server-side: rx = received FROM the peer, so it
                # is the device's upload; tx = sent TO the peer, its download.
                "down_kbps": rate_kbps(p["tx"], old.get("tx"), dt),
                "up_kbps": rate_kbps(p["rx"], old.get("rx"), dt),
                "ep_net": p["endpoint"],
                "ep_changed": bool(
                    old.get("endpoint") and old["endpoint"] != p["endpoint"]
                ),
            }
        )

    iface = wg_iface()
    prev_iface = prev.get("iface", {})
    iface_d = {
        k: iface[k] - prev_iface.get(k, iface[k]) for k in iface if k in prev_iface
    }

    cpu = cpu_times()
    prev_cpu = prev.get("cpu")
    cpu_busy = steal = None
    if prev_cpu and cpu["total"] > prev_cpu["total"]:
        span = cpu["total"] - prev_cpu["total"]
        cpu_busy = round(100 * (1 - (cpu["idle"] - prev_cpu["idle"]) / span), 1)
        steal = round(100 * (cpu["steal"] - prev_cpu["steal"]) / span, 1)

    rec = {
        "t": datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="seconds"),
        "ts": now,
        "src": "server",
        "kind": "sample",
        "peers": peers,
        "host": {**host_stats(), "cpu_busy": cpu_busy, "steal": steal},
        "iface_d": iface_d,
        "dns": dns_probe(),
        "net": ping_probe(),
    }
    state = {
        "ts": now,
        "peers": {ip: p for ip, p in peers_now.items()},
        "iface": iface,
        "cpu": cpu,
    }
    return rec, state


def rotate():
    cutoff = time.time() - KEEP_DAYS * 86400
    for f in LOG_DIR.glob("*.jsonl"):
        if f.stat().st_mtime < cutoff:
            f.unlink(missing_ok=True)


def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    lock = open(LOCK_FILE, "w")
    try:
        import fcntl

        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except Exception:
        return 0  # previous run still going — skip this minute

    state = read_state()
    for i in range(SAMPLES):
        if i:
            time.sleep(INTERVAL)
        now = int(time.time())
        try:
            rec, state = sample(state, now)
        except Exception as e:
            rec = {
                "t": datetime.fromtimestamp(now, timezone.utc).isoformat(),
                "ts": now,
                "src": "server",
                "kind": "error",
                "err": str(e)[:200],
            }
        day = datetime.fromtimestamp(rec["ts"], timezone.utc).strftime("%Y-%m-%d")
        with open(LOG_DIR / f"{day}.jsonl", "a") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        write_state(state)

    rotate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
