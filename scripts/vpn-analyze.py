#!/usr/bin/env python3
"""Correlate client and server VPN telemetry and name the culprit.

    scripts/vpn-analyze.py                 # today, pulls the server log over ssh
    scripts/vpn-analyze.py --date 2026-08-11
    scripts/vpn-analyze.py --no-fetch      # use whatever is already cached

Output, in order:
  1. who was connected, when, and how much each device moved
  2. lag episodes — consecutive flagged samples merged, with the reasons
  3. manual `vpn-lag` marks, each joined to the nearest samples on both sides
  4. a verdict per episode: home Wi-Fi / ISP / server / DNS / site
"""

import argparse
import json
import os
import statistics
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

CLIENT_LOG_DIR = Path(
    os.environ.get("CLIENT_LOG_DIR", Path.home() / "Library/Logs/vpn-probe")
)
CACHE_DIR = Path(
    os.environ.get("CACHE_DIR", Path.home() / "Library/Logs/vpn-probe/server")
)
SSH_HOST = os.environ.get("SSH_HOST", "vpn")
SERVER_LOG_DIR = os.environ.get("SERVER_LOG_DIR", "/var/log/vpn-telemetry")

# An episode ends after this long without a flagged sample.
EPISODE_GAP_S = 120
# A mark is matched to samples within this window.
MARK_WINDOW_S = 90


def load(path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def fetch_server_log(date):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dst = CACHE_DIR / f"{date}.jsonl"
    r = subprocess.run(
        ["scp", "-q", f"{SSH_HOST}:{SERVER_LOG_DIR}/{date}.jsonl", str(dst)],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print(f"! не смог забрать серверный лог: {r.stderr.strip()[:200]}", file=sys.stderr)
    return dst


def hhmm(ts):
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def hms(ts):
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def fmt(v, unit="", nd=0):
    if v is None:
        return "—"
    return f"{v:.{nd}f}{unit}"


def mb(bits_kbps_seconds):
    return bits_kbps_seconds / 8 / 1000


# ---------------------------------------------------------------- who was on

def presence(server):
    """Per-device online windows and traffic totals."""
    windows = defaultdict(list)  # id -> [[start, end], ...]
    traffic = defaultdict(lambda: {"down_mb": 0.0, "up_mb": 0.0, "peak_down": 0.0})
    roams = defaultdict(int)
    last_ts = {}

    samples = [r for r in server if r.get("kind") == "sample"]
    for r in samples:
        ts = r["ts"]
        for p in r.get("peers", []):
            pid = p["id"]
            if p.get("ep_changed"):
                roams[pid] += 1
            if not p.get("online"):
                continue
            prev = last_ts.get(pid)
            if prev is None or ts - prev > 180:
                windows[pid].append([ts, ts])
            else:
                windows[pid][-1][1] = ts
            last_ts[pid] = ts
            # kbps over the ~10s sampling interval
            span = 10
            traffic[pid]["down_mb"] += mb(p.get("down_kbps", 0) * span)
            traffic[pid]["up_mb"] += mb(p.get("up_kbps", 0) * span)
            traffic[pid]["peak_down"] = max(
                traffic[pid]["peak_down"], p.get("down_kbps", 0)
            )
    return windows, traffic, roams


# ------------------------------------------------------------------ episodes

def episodes(client):
    """Merge consecutive lag-flagged client samples into episodes."""
    eps = []
    cur = None
    for r in client:
        if r.get("kind") != "sample":
            continue
        if r.get("lag"):
            if cur and r["ts"] - cur["end"] <= EPISODE_GAP_S:
                cur["end"] = r["ts"]
                cur["samples"].append(r)
            else:
                if cur:
                    eps.append(cur)
                cur = {"start": r["ts"], "end": r["ts"], "samples": [r]}
        elif cur and r["ts"] - cur["end"] > EPISODE_GAP_S:
            eps.append(cur)
            cur = None
    if cur:
        eps.append(cur)
    return eps


def med(vals):
    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def verdict(ep, server_by_ts):
    """Name the leg that broke, using the client legs first and the server as backup."""
    ss = ep["samples"]
    reasons = defaultdict(int)
    for s in ss:
        for w in s.get("why", []):
            reasons[w] += 1
    n = len(ss)

    lan_bad = reasons["lan_rtt"] + reasons["lan_loss"] > n * 0.4
    direct_bad = reasons["direct_rtt"] + reasons["direct_loss"] > n * 0.4
    tunnel_bad = reasons["tunnel_rtt"] + reasons["tunnel_loss"] > n * 0.4
    dns_bad = sum(v for k, v in reasons.items() if k.startswith("dns")) > n * 0.4
    http_bad = reasons["http_ttfb"] + reasons["http_fail"] > n * 0.4

    # Server-side context for the same window.
    srv = [
        r
        for ts, r in server_by_ts.items()
        if ep["start"] - 30 <= ts <= ep["end"] + 30 and r.get("kind") == "sample"
    ]
    srv_load = med([r["host"].get("load1") for r in srv]) if srv else None
    srv_steal = med([r["host"].get("steal") for r in srv]) if srv else None
    srv_dns = med([(r.get("dns") or {}).get("lookup_ms") for r in srv]) if srv else None
    srv_loss = med([(r.get("net") or {}).get("loss") for r in srv]) if srv else None
    other_load = 0.0
    for r in srv:
        for p in r.get("peers", []):
            other_load = max(other_load, p.get("down_kbps", 0) + p.get("up_kbps", 0))

    if lan_bad:
        who = "домашний Wi-Fi / роутер"
    elif direct_bad and tunnel_bad:
        who = "канал провайдера до сервера"
    elif tunnel_bad and not direct_bad:
        if srv_load and srv_load > 1.5:
            who = "сервер перегружен"
        elif other_load > 20000:
            who = "канал забит вторым устройством"
        else:
            who = "WireGuard / очередь на сервере"
    elif dns_bad:
        who = "DNS (unbound)" if (srv_dns or 0) > 300 else "DNS до сервера"
    elif http_bad:
        who = "сам сайт / Cloudflare edge"
    else:
        who = "неоднозначно"

    return {
        "who": who,
        "reasons": dict(sorted(reasons.items(), key=lambda x: -x[1])),
        "lan_rtt": med([(s.get("lan") or {}).get("rtt_ms") for s in ss]),
        "direct_rtt": med([(s.get("direct") or {}).get("rtt_ms") for s in ss]),
        "tunnel_rtt": med([(s.get("tunnel") or {}).get("rtt_ms") for s in ss]),
        "dns_ms": med([(s.get("dns") or {}).get("lookup_ms") for s in ss]),
        "ttfb_ms": med([(s.get("http") or {}).get("ttfb_ms") for s in ss]),
        "srv_load": srv_load,
        "srv_steal": srv_steal,
        "srv_dns": srv_dns,
        "srv_loss": srv_loss,
        "peer_peak_kbps": other_load,
    }


# -------------------------------------------------------------------- report

def report(date, client, server):
    server_by_ts = {r["ts"]: r for r in server if "ts" in r}
    cs = [r for r in client if r.get("kind") == "sample"]
    marks = [r for r in client if r.get("kind") == "mark"]

    print(f"\n=== VPN телеметрия за {date} ===")
    print(f"клиентских замеров: {len(cs)}   серверных: {len([r for r in server if r.get('kind')=='sample'])}")

    if not cs and not server:
        print("\nданных нет — сборщики ещё не отработали")
        return

    # 1. Кто подключался
    print("\n-- Кто был в сети --")
    windows, traffic, roams = presence(server)
    if not windows:
        print("  (серверного лога нет или пиров не было)")
    for pid, wins in sorted(windows.items()):
        total = sum(e - s for s, e in wins)
        spans = ", ".join(f"{hhmm(s)}–{hhmm(e)}" for s, e in wins[:8])
        if len(wins) > 8:
            spans += f" … (+{len(wins)-8})"
        t = traffic[pid]
        print(f"  {pid:8} {total//60:4d} мин  ↓{t['down_mb']:7.1f} МБ ↑{t['up_mb']:6.1f} МБ"
              f"  пик ↓{t['peak_down']/1000:5.1f} Мбит/с"
              f"{'  смен сети: %d' % roams[pid] if roams[pid] else ''}")
        print(f"           {spans}")

    # 2. Базовая линия — чтобы «тупняк» было с чем сравнивать
    print("\n-- Базовая линия (медиана по всем замерам) --")
    print(f"  Mac → роутер      {fmt(med([(s.get('lan') or {}).get('rtt_ms') for s in cs]), ' мс', 1)}")
    print(f"  Mac → сервер (вне туннеля) {fmt(med([(s.get('direct') or {}).get('rtt_ms') for s in cs]), ' мс', 1)}")
    print(f"  Mac → сервер (в туннеле)   {fmt(med([(s.get('tunnel') or {}).get('rtt_ms') for s in cs]), ' мс', 1)}")
    print(f"  DNS живой запрос  {fmt(med([(s.get('dns') or {}).get('lookup_ms') for s in cs]), ' мс')}")
    print(f"  DNS из кэша       {fmt(med([(s.get('dns') or {}).get('cache_ms') for s in cs]), ' мс')}")
    print(f"  TTFB              {fmt(med([(s.get('http') or {}).get('ttfb_ms') for s in cs]), ' мс')}")
    srv_s = [r for r in server if r.get("kind") == "sample"]
    if srv_s:
        print(f"  сервер: load {fmt(med([r['host'].get('load1') for r in srv_s]), '', 2)}"
              f"  steal {fmt(med([r['host'].get('steal') for r in srv_s]), '%', 1)}"
              f"  DNS {fmt(med([(r.get('dns') or {}).get('lookup_ms') for r in srv_s]), ' мс')}"
              f"  потери {fmt(med([(r.get('net') or {}).get('loss') for r in srv_s]), '%')}")

    # 3. Эпизоды
    eps = episodes(client)
    bad = len([s for s in cs if s.get("lag")])
    print(f"\n-- Тупняки: {len(eps)} эпизодов, {bad} из {len(cs)} замеров плохие "
          f"({100*bad/len(cs):.0f}%) --" if cs else "\n-- Тупняки --")
    for e in eps:
        v = verdict(e, server_by_ts)
        dur = e["end"] - e["start"] + 20
        print(f"\n  {hms(e['start'])}–{hms(e['end'])} ({dur//60}м{dur%60:02d}с, {len(e['samples'])} замеров)")
        print(f"    ВЕРДИКТ: {v['who']}")
        print(f"    признаки: {', '.join(f'{k}×{n}' for k, n in list(v['reasons'].items())[:6])}")
        print(f"    RTT роутер/вне/в туннеле: {fmt(v['lan_rtt'],'',1)} / "
              f"{fmt(v['direct_rtt'],'',1)} / {fmt(v['tunnel_rtt'],'',1)} мс"
              f"   DNS {fmt(v['dns_ms'],' мс')}   TTFB {fmt(v['ttfb_ms'],' мс')}")
        print(f"    сервер: load {fmt(v['srv_load'],'',2)}  steal {fmt(v['srv_steal'],'%',1)}"
              f"  DNS {fmt(v['srv_dns'],' мс')}  потери {fmt(v['srv_loss'],'%')}"
              f"  пик пира {v['peer_peak_kbps']/1000:.1f} Мбит/с")

    # 4. Ручные отметки
    if marks:
        print("\n-- Отметки вручную (vpn-lag) --")
        for m in marks:
            near = [s for s in cs if abs(s["ts"] - m["ts"]) <= MARK_WINDOW_S]
            print(f"\n  {hms(m['ts'])}  «{m.get('note','')}»")
            if not near:
                print("    рядом нет замеров (пробник не работал?)")
                continue
            flagged = [s for s in near if s.get("lag")]
            print(f"    замеров рядом: {len(near)}, из них плохих: {len(flagged)}")
            print(f"    RTT роутер/вне/в туннеле: "
                  f"{fmt(med([(s.get('lan') or {}).get('rtt_ms') for s in near]),'',1)} / "
                  f"{fmt(med([(s.get('direct') or {}).get('rtt_ms') for s in near]),'',1)} / "
                  f"{fmt(med([(s.get('tunnel') or {}).get('rtt_ms') for s in near]),'',1)} мс"
                  f"   DNS {fmt(med([(s.get('dns') or {}).get('lookup_ms') for s in near]),' мс')}"
                  f"   TTFB {fmt(med([(s.get('http') or {}).get('ttfb_ms') for s in near]),' мс')}")
            reasons = defaultdict(int)
            for s in flagged:
                for w in s.get("why", []):
                    reasons[w] += 1
            if reasons:
                print(f"    признаки: {', '.join(f'{k}×{n}' for k, n in sorted(reasons.items(), key=lambda x:-x[1]))}")
            else:
                print("    измерения в норме — тупняк не в сети (браузер/сайт/устройство)")
            srv_near = [r for r in srv_s if abs(r["ts"] - m["ts"]) <= MARK_WINDOW_S]
            if srv_near:
                busiest = []
                for r in srv_near:
                    for p in r.get("peers", []):
                        if p.get("online"):
                            busiest.append((p["down_kbps"] + p["up_kbps"], p["id"]))
                busiest.sort(reverse=True)
                who = f", больше всех качал {busiest[0][1]} ({busiest[0][0]/1000:.1f} Мбит/с)" if busiest else ""
                print(f"    на сервере: load {fmt(med([r['host'].get('load1') for r in srv_near]),'',2)}"
                      f", DNS {fmt(med([(r.get('dns') or {}).get('lookup_ms') for r in srv_near]),' мс')}{who}")

    # 5. Итог
    print("\n-- Итог --")
    if eps:
        tally = defaultdict(int)
        for e in eps:
            tally[verdict(e, server_by_ts)["who"]] += 1
        for who, n in sorted(tally.items(), key=lambda x: -x[1]):
            print(f"  {n:3d} эпизодов — {who}")
    else:
        print("  плохих замеров не зафиксировано")
    print()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    ap.add_argument("--no-fetch", action="store_true")
    a = ap.parse_args()

    client = load(CLIENT_LOG_DIR / f"{a.date}.jsonl")
    srv_path = CACHE_DIR / f"{a.date}.jsonl"
    if not a.no_fetch:
        srv_path = fetch_server_log(a.date)
    server = load(srv_path)

    report(a.date, client, server)


if __name__ == "__main__":
    main()
