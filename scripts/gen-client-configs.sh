#!/usr/bin/env bash
# Сборка клиентских конфигов sing-box из шаблона и секретов.
#
# ЗАПУСКАТЬ ТОЛЬКО НА СЕРВЕРЕ, после scripts/gen-proxy-secrets.sh.
# Секреты не попадают ни в stdout, ни в stderr. Готовые конфиги забирать по scp:
#     scp vpn:~/vpn-server/clients/macbook-singbox.json ~/Downloads/
#
# Каждый конфиг проверяется настоящим `sing-box check` — без этого ошибки
# схемы всплыли бы только на устройстве, без внятного сообщения.
#
#   Использование:  ./scripts/gen-client-configs.sh

set -euo pipefail
umask 077

cd "$(dirname "$0")/.."

SINGBOX_IMAGE="ghcr.io/sagernet/sing-box:v1.13.18"
DEVICES=(macbook iphone android)

die() { echo "ОШИБКА: $*" >&2; exit 1; }

for t in docker python3; do
  command -v "$t" >/dev/null || die "$t не найден — скрипт рассчитан на сервер"
done

[ -d secrets ] || die "нет каталога secrets — сначала ./scripts/gen-proxy-secrets.sh"
[ -f hysteria/certs/hy2.crt ] || die "нет сертификата Hysteria2"
[ -f secrets/hy2_sni.txt ] || die "нет secrets/hy2_sni.txt"
[ -f clients/singbox-client.example.json ] || die "нет шаблона clients/singbox-client.example.json"

mkdir -p clients
chmod 700 clients

for dev in "${DEVICES[@]}"; do
  [ -f "secrets/uuid_${dev}.txt" ] || die "нет secrets/uuid_${dev}.txt"

  python3 - "$dev" <<'PY'
import json, sys, pathlib

dev = sys.argv[1]
sec = pathlib.Path('secrets')
read = lambda n: (sec / n).read_text().strip()

cfg = json.loads(pathlib.Path('clients/singbox-client.example.json').read_text())

def strip_comments(node):
    """sing-box использует строгий разбор и падает на неизвестных полях.
    Ключи-комментарии ("//", "//_что-то") обязаны быть удалены, иначе конфиг
    не запустится на устройстве. Проверено на v1.13.18: конфиг с ключом "//"
    внутри dns отвергается с `unknown field "//"`."""
    if isinstance(node, dict):
        return {k: strip_comments(v) for k, v in node.items() if not k.startswith('//')}
    if isinstance(node, list):
        return [strip_comments(v) for v in node]
    return node

cfg = strip_comments(cfg)

pem = pathlib.Path('hysteria/certs/hy2.crt').read_text().strip().split('\n')

for out in cfg['outbounds']:
    if out.get('tag') == 'hy2-fra':
        out['password'] = read('hy2_password.txt')
        out['tls']['server_name'] = read('hy2_sni.txt')
        out['tls']['certificate'] = pem
    elif out.get('tag') == 'reality-fra':
        out['uuid'] = read(f'uuid_{dev}.txt')
        out['tls']['reality']['public_key'] = read('reality_public.txt')
        out['tls']['reality']['short_id'] = read('reality_shortid.txt')

blob = json.dumps(cfg, indent=2)
if 'REPLACE_' in blob:
    sys.exit('ОШИБКА: остались незаполненные плейсхолдеры в конфиге ' + dev)

dst = pathlib.Path(f'clients/{dev}-singbox.json')
dst.write_text(blob + '\n')
dst.chmod(0o600)
print(f'  собран: {dst}')
PY

  # Реальная проверка схемы, а не «на глаз».
  abs_path="$(pwd)/clients/${dev}-singbox.json"
  if docker run --rm --log-driver none -v "${abs_path}:/c.json:ro" \
       "$SINGBOX_IMAGE" check -c /c.json >/dev/null 2>&1; then
    echo "  проверен: clients/${dev}-singbox.json — схема валидна"
  else
    # Вывод валидатора НЕ печатаем: сообщения об ошибках схемы обычно
    # цитируют значение проблемного поля, а в этом файле лежат пароль,
    # UUID и ключ REALITY. Кладём в файл с правами 600.
    logf="secrets/singbox-check-${dev}.err"
    docker run --rm --log-driver none -v "${abs_path}:/c.json:ro" \
      "$SINGBOX_IMAGE" check -c /c.json > "$logf" 2>&1 || true
    chmod 600 "$logf"
    die "конфиг ${dev} невалиден — на устройство не отдавать. Подробности: ${logf}"
  fi
done

echo
echo "Готово. Конфиги в ./clients (chmod 600), в git не попадают."
echo "Забрать на машину:  scp vpn:~/vpn-server/clients/macbook-singbox.json ~/Downloads/"
