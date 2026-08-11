#!/usr/bin/env bash
# Install the telemetry collectors.
#
#   scripts/vpn-telemetry-install.sh server   # on the droplet: cron every minute
#   scripts/vpn-telemetry-install.sh client   # on the Mac: launchd agent + vpn-lag
#   scripts/vpn-telemetry-install.sh status   # what is running where
#   scripts/vpn-telemetry-install.sh stop     # unload the Mac agent
#
# Idempotent: re-running replaces the cron line / reloads the agent.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSH_HOST="${SSH_HOST:-vpn}"
SERVER_DIR="${SERVER_DIR:-/root/vpn-server}"
LABEL="cc.halobolan.vpn-probe"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
CLIENT_LOG_DIR="$HOME/Library/Logs/vpn-probe"
SUPPORT_DIR="$HOME/Library/Application Support/vpn-probe"

install_server() {
  echo "==> устанавливаю сборщик на $SSH_HOST"
  scp -q "$HERE/vpn-telemetry.py" "$SSH_HOST:$SERVER_DIR/scripts/vpn-telemetry.py"
  ssh "$SSH_HOST" bash -s <<EOF
set -euo pipefail
chmod +x $SERVER_DIR/scripts/vpn-telemetry.py
mkdir -p /var/log/vpn-telemetry

# Peer labels: tunnel IP -> device name. Derived once, edit by hand afterwards.
if [ ! -f $SERVER_DIR/peer-labels.conf ]; then
  cat > $SERVER_DIR/peer-labels.conf <<'LBL'
# tunnel IP = имя устройства (правится руками)
10.13.13.2=mac
10.13.13.3=phone
LBL
fi

# Replace any previous line, keep the rest of the crontab intact.
( crontab -l 2>/dev/null | grep -v vpn-telemetry.py ; \
  echo "* * * * * /usr/bin/python3 $SERVER_DIR/scripts/vpn-telemetry.py >/dev/null 2>&1" ) \
  | crontab -

echo "cron:"; crontab -l | grep vpn-telemetry.py
EOF
  echo "==> первый прогон вручную (60 с, 6 замеров)"
  ssh "$SSH_HOST" "/usr/bin/python3 $SERVER_DIR/scripts/vpn-telemetry.py"
  ssh "$SSH_HOST" "tail -1 /var/log/vpn-telemetry/\$(date -u +%F).jsonl | head -c 400; echo"
}

env_val() {
  # Read one key from the repo .env; empty if absent.
  sed -n "s/^$1=//p" "$HERE/../.env" 2>/dev/null | head -1 | tr -d ' \r'
}

install_client() {
  echo "==> устанавливаю пробник на Mac"
  mkdir -p "$CLIENT_LOG_DIR" "$HOME/Library/LaunchAgents" "$HOME/bin" "$SUPPORT_DIR"

  # The repo lives under ~/Documents, which macOS TCC hides from launchd agents
  # ("Operation not permitted" on every exec). Run from a copy outside it.
  # rm first: an older install may have left a symlink pointing back into the repo.
  rm -f "$SUPPORT_DIR/vpn-probe.py" "$HOME/bin/vpn-lag"
  install -m 755 "$HERE/vpn-probe.py" "$SUPPORT_DIR/vpn-probe.py"
  install -m 755 "$HERE/vpn-lag" "$HOME/bin/vpn-lag"

  local server_ip dns_addr subnet
  server_ip="$(env_val SERVERURL)"
  dns_addr="$(env_val PEERDNS)"
  subnet="$(env_val INTERNAL_SUBNET)"
  : "${dns_addr:=10.2.0.100}"
  : "${subnet:=10.13.13.0}"
  if [ -z "$server_ip" ]; then
    echo "!! SERVERURL не найден в .env — пробник не сможет мерить прямое плечо" >&2
    exit 1
  fi

  sed -e "s|__SCRIPT__|$SUPPORT_DIR/vpn-probe.py|g" \
      -e "s|__LOGDIR__|$CLIENT_LOG_DIR|g" \
      -e "s|__SERVER_IP__|$server_ip|g" \
      -e "s|__DNS_ADDR__|$dns_addr|g" \
      -e "s|__TUNNEL_SUBNET__|$subnet|g" \
      "$HERE/$LABEL.plist" > "$PLIST"

  launchctl bootout "gui/$UID/$LABEL" 2>/dev/null || true
  launchctl bootstrap "gui/$UID" "$PLIST"
  launchctl kickstart -k "gui/$UID/$LABEL"
  echo "агент загружен, первый замер через ~20 с"
  echo "отметить тупняк:  ~/bin/vpn-lag youtube буферит"
}

status() {
  echo "== Mac =="
  launchctl print "gui/$UID/$LABEL" 2>/dev/null | grep -E '^\s+(state|pid|last exit)' || echo "агент не загружен"
  local f="$CLIENT_LOG_DIR/$(date -u +%F).jsonl"
  [ -f "$f" ] && echo "замеров сегодня: $(wc -l < "$f" | tr -d ' ')" || echo "лога за сегодня нет"
  [ -s "$CLIENT_LOG_DIR/probe.err" ] && { echo "stderr:"; tail -5 "$CLIENT_LOG_DIR/probe.err"; }

  echo "== сервер =="
  ssh "$SSH_HOST" 'crontab -l | grep vpn-telemetry.py || echo "cron не стоит"; \
    f=/var/log/vpn-telemetry/$(date -u +%F).jsonl; \
    [ -f "$f" ] && echo "замеров сегодня: $(wc -l < $f)" || echo "лога за сегодня нет"'
}

stop_client() {
  launchctl bootout "gui/$UID/$LABEL" 2>/dev/null && echo "агент выгружен" || echo "агент и так не работал"
}

case "${1:-}" in
  server) install_server ;;
  client) install_client ;;
  all)    install_server; install_client ;;
  status) status ;;
  stop)   stop_client ;;
  *) sed -n '2,9p' "$0"; exit 1 ;;
esac
