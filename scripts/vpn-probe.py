#!/usr/bin/env python3
"""Client-side VPN probe (macOS).

Runs as a launchd agent in a loop. Every INTERVAL seconds it measures the same
request path the user actually experiences and writes one JSON line to
~/Library/Logs/vpn-probe/YYYY-MM-DD.jsonl.

The point is to split the blame. Three ping legs are measured every sample:

  lan     Mac -> home router            bad => Wi-Fi / home network
  direct  Mac -> droplet, outside tunnel  bad => ISP / route to the server
  tunnel  Mac -> 10.13.13.1, inside tunnel

tunnel bad while direct is fine  => WireGuard / server-side queueing
dns bad while all pings fine     => unbound recursion
ttfb bad while all of the above fine => the site itself, or the CF edge

A sample is flagged lag=true with a list of reasons when any threshold trips,
so the analyzer can find episodes without re-deriving the rules.
"""

import json
import os
import re
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

def env_file(key):
    """Read a value from the repo .env — no server addresses hardcoded here."""
    f = Path(__file__).resolve().parent.parent / ".env"
    if not f.exists():
        return None
    for line in f.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip()
    return None


def cfg(key, env_key=None, default=None):
    return os.environ.get(key) or env_file(env_key or key) or default


LOG_DIR = Path(
    os.environ.get("LOG_DIR", Path.home() / "Library/Logs/vpn-probe")
)
INTERVAL = int(os.environ.get("INTERVAL", "20"))
KEEP_DAYS = int(os.environ.get("KEEP_DAYS", "14"))
SERVER_IP = cfg("SERVER_IP", "SERVERURL")
DNS_ADDR = cfg("DNS_ADDR", "PEERDNS", "10.2.0.100")

# INTERNAL_SUBNET=10.13.13.0 -> peers live on 10.13.13.*, server holds .1
_subnet = cfg("TUNNEL_SUBNET", "INTERNAL_SUBNET", "10.13.13.0")
TUNNEL_NET = _subnet.rsplit(".", 1)[0] + "."
TUNNEL_GW = os.environ.get("TUNNEL_GW", TUNNEL_NET + "1")

if not SERVER_IP:
    sys.exit("SERVER_IP не задан и SERVERURL не найден в .env")

# Rotated one per sample so a single slow site cannot dominate the log.
HTTP_TARGETS = [
    ("vault", "https://vault.halobolan.cc/alive"),
    ("google", "https://www.google.com/generate_204"),
    ("youtube", "https://www.youtube.com/generate_204"),
    ("cloudflare", "https://www.cloudflare.com/cdn-cgi/trace"),
]

THRESHOLDS = {
    "lan_rtt": 30.0,
    "lan_loss": 5,
    "direct_rtt": 150.0,
    "direct_loss": 3,
    "tunnel_rtt": 200.0,
    "tunnel_loss": 3,
    "dns_ms": 400,
    "ttfb_ms": 1500,
}


def run(cmd, timeout=10):
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
        return p.stdout
    except Exception:
        return ""


PING_LOSS = re.compile(r"([\d.]+)% packet loss")
PING_RTT = re.compile(r"= [\d.]+/([\d.]+)/[\d.]+/([\d.]+) ms")


def ping(target, count=5):
    if not target:
        return None
    # macOS: -W is milliseconds, -t caps the whole run in seconds.
    cmd = ["ping", "-c", str(count), "-i", "0.2", "-W", "1500", "-t", "8", target]
    out = run(cmd, timeout=count + 8)
    loss = PING_LOSS.search(out)
    rtt = PING_RTT.search(out)
    if not loss:
        return {"loss": 100, "rtt_ms": None, "jitter_ms": None}
    return {
        "loss": float(loss.group(1)),
        "rtt_ms": float(rtt.group(1)) if rtt else None,
        "jitter_ms": float(rtt.group(2)) if rtt else None,
    }


def tunnel_ip():
    """Tunnel address if WireGuard is up, else None."""
    out = run(["ifconfig"])
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("inet ") and TUNNEL_NET in line:
            return line.split()[1]
    return None


def lan_router():
    """Home router address — must be read per-interface, the default route is the tunnel."""
    for iface in ("en0", "en1", "en5", "en6"):
        ip = run(["ipconfig", "getoption", iface, "router"], timeout=4).strip()
        if ip and ip != "0.0.0.0":
            return ip, iface
    return None, None


DIG_TIME = re.compile(r";; Query time: (\d+) msec")


def dig_ms(name, server, timeout=5):
    out = run(
        ["dig", "+tries=1", f"+time={timeout}", f"@{server}", name, "A"],
        timeout=timeout + 3,
    )
    m = DIG_TIME.search(out)
    return int(m.group(1)) if m else None


# Real names, not a random label: unbound's aggressive-nsec answers a made-up
# subdomain from cache in ~3 ms without touching the network, which measures nothing.
DOMAINS = [
    "github.com", "youtube.com", "instagram.com", "telegram.org", "wikipedia.org",
    "reddit.com", "netflix.com", "spotify.com", "twitch.tv", "vk.com",
    "apple.com", "icloud.com", "amazon.com", "aliexpress.com", "booking.com",
    "nytimes.com", "medium.com", "stackoverflow.com", "gitlab.com", "npmjs.com",
    "protonmail.com", "duckduckgo.com", "paypal.com", "discord.com", "zoom.us",
    "slack.com", "notion.so", "figma.com", "dropbox.com", "linkedin.com",
]


def dns_probe():
    return {
        "cache_ms": dig_ms("cloudflare.com", DNS_ADDR),
        "lookup_ms": dig_ms(random.choice(DOMAINS), DNS_ADDR),
    }


def http_probe(name, url):
    out = run(
        [
            "curl", "-s", "-o", "/dev/null", "--max-time", "10",
            "-w", "%{http_code} %{time_namelookup} %{time_connect} "
                  "%{time_appconnect} %{time_starttransfer}",
            url,
        ],
        timeout=13,
    )
    f = out.split()
    if len(f) != 5:
        return {"name": name, "code": 0}
    ms = lambda x: round(float(x) * 1000, 1)
    return {
        "name": name,
        "code": int(f[0]),
        "dns_ms": ms(f[1]),
        "connect_ms": ms(f[2]),
        "tls_ms": ms(f[3]),
        "ttfb_ms": ms(f[4]),
    }


TCP_RETRANS = re.compile(r"(\d+) data packets \((\d+) bytes\) retransmitted")
TCP_SENT = re.compile(r"(\d+) data packets \((\d+) bytes\)\n")


def tcp_retrans():
    out = run(["netstat", "-s", "-p", "tcp"], timeout=8)
    m = TCP_RETRANS.search(out)
    return int(m.group(1)) if m else None


def wifi_info():
    """RSSI/noise without sudo. Slow (~1-3s), so callers sample it rarely."""
    out = run(
        ["system_profiler", "SPAirPortDataType", "-detailLevel", "basic"], timeout=8
    )
    sig = re.search(r"Signal / Noise:\s*(-?\d+)\s*dBm\s*/\s*(-?\d+)\s*dBm", out)
    rate = re.search(r"Transmit Rate:\s*(\d+)", out)
    if not sig:
        return None
    return {
        "rssi": int(sig.group(1)),
        "noise": int(sig.group(2)),
        "tx_rate": int(rate.group(1)) if rate else None,
    }


def judge(rec):
    """Attach lag=true plus the reasons, so episodes are findable without re-deriving."""
    why = []
    t = THRESHOLDS

    def leg(key, rtt_lim, loss_lim):
        p = rec.get(key)
        if not p:
            return
        if p["loss"] >= loss_lim:
            why.append(f"{key}_loss")
        if p["rtt_ms"] is not None and p["rtt_ms"] >= rtt_lim:
            why.append(f"{key}_rtt")

    leg("lan", t["lan_rtt"], t["lan_loss"])
    leg("direct", t["direct_rtt"], t["direct_loss"])
    leg("tunnel", t["tunnel_rtt"], t["tunnel_loss"])

    dns = rec.get("dns") or {}
    for k in ("cache_ms", "lookup_ms"):
        v = dns.get(k)
        if v is None:
            why.append(f"dns_{k}_fail")
        elif v >= t["dns_ms"]:
            why.append(f"dns_{k}")

    h = rec.get("http") or {}
    if h.get("code") == 0:
        why.append("http_fail")
    elif h.get("ttfb_ms", 0) >= t["ttfb_ms"]:
        why.append("http_ttfb")

    rec["lag"] = bool(why)
    rec["why"] = why
    return rec


def rotate():
    cutoff = time.time() - KEEP_DAYS * 86400
    for f in LOG_DIR.glob("*.jsonl"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
        except Exception:
            pass


def write(rec):
    day = datetime.fromtimestamp(rec["ts"], timezone.utc).strftime("%Y-%m-%d")
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_DIR / f"{day}.jsonl", "a") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    i = 0
    prev_retrans = None
    prev_ts = None

    while True:
        started = time.time()
        now = int(started)
        tun = tunnel_ip()
        router, iface = lan_router()

        rec = {
            "t": datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="seconds"),
            "ts": now,
            "src": "mac",
            "kind": "sample",
            "tunnel_up": bool(tun),
            "iface": iface,
        }

        # A gap means the laptop slept; deltas across it are meaningless.
        if prev_ts and now - prev_ts > INTERVAL * 5:
            rec["gap_s"] = now - prev_ts
        prev_ts = now

        rec["lan"] = ping(router, count=5) if router else None
        rec["direct"] = ping(SERVER_IP, count=5)
        rec["tunnel"] = ping(TUNNEL_GW, count=5) if tun else None

        if tun:
            rec["dns"] = dns_probe()
            name, url = HTTP_TARGETS[i % len(HTTP_TARGETS)]
            rec["http"] = http_probe(name, url)

        rt = tcp_retrans()
        if rt is not None and prev_retrans is not None and rt >= prev_retrans:
            rec["tcp_retrans_d"] = rt - prev_retrans
        prev_retrans = rt

        if i % 6 == 0:
            w = wifi_info()
            if w:
                rec["wifi"] = w

        write(judge(rec))

        if i % 180 == 0:
            rotate()
        i += 1

        time.sleep(max(1, INTERVAL - (time.time() - started)))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
