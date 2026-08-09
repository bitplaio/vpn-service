#!/usr/bin/env bash
# Генерация секретов для Hysteria2 + VLESS-REALITY.
#
# ЗАПУСКАТЬ ТОЛЬКО НА СЕРВЕРЕ. Скрипт намеренно НЕ печатает ни одного секрета в
# stdout: пароли, приватные ключи и UUID попадают только в файлы с правами 600.
# Причина — вывод команды, запущенной через SSH, оседает в истории, в логах
# и в контексте ассистента.
#
#   Использование:  ./scripts/gen-proxy-secrets.sh [--force]
#     --force   пересоздать всё, включая уже существующие секреты
#
# Идемпотентен: без --force существующие файлы не перезаписываются, поэтому
# повторный запуск не разорвёт уже настроенные клиенты.

set -euo pipefail

# Все создаваемые файлы сразу недоступны никому кроме владельца. Без этого
# между созданием файла и chmod 600 есть окно, в котором секрет читаем всеми.
umask 077

cd "$(dirname "$0")/.."

XRAY_IMAGE="ghcr.io/xtls/xray-core:26.7.28"
DEVICES=(macbook iphone android)

usage() {
  sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

FORCE=0
case "${1:-}" in
  "")        ;;
  --force)   FORCE=1 ;;
  -h|--help) usage 0 ;;
  *)         echo "ОШИБКА: неизвестный аргумент: $1" >&2; usage 1 ;;
esac

die() { echo "ОШИБКА: $*" >&2; exit 1; }
have() { [ -s "$1" ]; }

for t in docker openssl python3; do
  command -v "$t" >/dev/null || die "$t не найден — скрипт рассчитан на сервер"
done

mkdir -p hysteria/certs xray clients secrets
chmod 700 secrets hysteria/certs xray clients

# ---------------------------------------------------------------------------
# 1. Имя в сертификате (SNI)
# ---------------------------------------------------------------------------
# СОЗНАТЕЛЬНО не связано с halobolan.cc. Ревью показало дыру в первой версии:
# CN=hy2.halobolan.cc читается любым активным сканером прямо из TLS-handshake
# (в TLS 1.3 сообщение Certificate защищено только от ПАССИВНОГО наблюдателя).
# Censys и Shodan постоянно сканируют интернет, поэтому имя оказалось бы
# проиндексировано рядом с 157.230.98.224 — и, через общий домен, связано с
# vault.halobolan.cc. То есть ровно та связка, ради разрыва которой мы вообще
# отказались от ACME. Случайное имя в зоне .invalid (RFC 2606, гарантированно
# нерегистрируемая) не ведёт никуда.
# Сертификат самоподписанный и проверяется пиннингом, поэтому имя может быть
# любым — резолвиться ему не нужно.
if [ $FORCE -eq 1 ] || ! have secrets/hy2_sni.txt; then
  echo "$(openssl rand -hex 8).invalid" > secrets/hy2_sni.txt
fi
SNI="$(cat secrets/hy2_sni.txt)"

# ---------------------------------------------------------------------------
# 2. Самоподписанный сертификат для Hysteria2 (ECDSA P-256, 10 лет)
# ---------------------------------------------------------------------------
# ECDSA, а не RSA: короче handshake, меньше CPU на 2 vCPU.
if [ $FORCE -eq 1 ] || ! have hysteria/certs/hy2.crt; then
  err=$(openssl req -x509 -nodes -newkey ec:<(openssl ecparam -name prime256v1) \
    -keyout hysteria/certs/hy2.key -out hysteria/certs/hy2.crt \
    -days 3650 -subj "/CN=${SNI}" \
    -addext "subjectAltName=DNS:${SNI}" 2>&1) \
    || die "openssl не смог создать сертификат: $err"
  chmod 600 hysteria/certs/hy2.key
  chmod 644 hysteria/certs/hy2.crt
  echo "  создан: сертификат Hysteria2 (ECDSA P-256, 10 лет, имя в secrets/hy2_sni.txt)"
else
  echo "  пропущен: сертификат уже существует"
fi

# ---------------------------------------------------------------------------
# 3. Пароль Hysteria2
# ---------------------------------------------------------------------------
if [ $FORCE -eq 1 ] || ! have secrets/hy2_password.txt; then
  openssl rand -base64 32 > secrets/hy2_password.txt
  echo "  создан: пароль Hysteria2 (32 байта)"
else
  echo "  пропущен: пароль Hysteria2 уже существует"
fi

# ---------------------------------------------------------------------------
# 4. Ключевая пара REALITY (x25519)
# ---------------------------------------------------------------------------
# --log-driver none: иначе stdout контейнера с ключом успевает лечь на диск
# через json-file, пусть и до удаления контейнера.
# Формат вывода менялся между версиями: раньше "Public key:", теперь "Password:".
if [ $FORCE -eq 1 ] || ! have secrets/reality_private.txt; then
  out=$(docker run --rm --log-driver none "$XRAY_IMAGE" x25519)
  printf '%s\n' "$out" | awk -F': *' '/[Pp]rivate[ _]?[Kk]ey/{print $2}' > secrets/reality_private.txt
  printf '%s\n' "$out" | awk -F': *' '/[Pp]assword|[Pp]ublic[ _]?[Kk]ey/{print $2}' > secrets/reality_public.txt
  unset out
  have secrets/reality_private.txt || die "не удалось разобрать приватный ключ REALITY"
  have secrets/reality_public.txt  || die "не удалось разобрать публичный ключ REALITY"
  echo "  создана: ключевая пара REALITY x25519"
else
  echo "  пропущена: ключевая пара REALITY уже существует"
fi

# shortId: чётное число hex-символов, максимум 16
if [ $FORCE -eq 1 ] || ! have secrets/reality_shortid.txt; then
  openssl rand -hex 8 > secrets/reality_shortid.txt
  echo "  создан: shortId REALITY"
fi

# ---------------------------------------------------------------------------
# 5. UUID — свой на каждое устройство
# ---------------------------------------------------------------------------
# Отдельный UUID на устройство даёт отзыв доступа поштучно: потеря телефона
# означает удаление одной строки, а не смену секрета на всех устройствах.
for dev in "${DEVICES[@]}"; do
  f="secrets/uuid_${dev}.txt"
  if [ $FORCE -eq 1 ] || ! have "$f"; then
    docker run --rm --log-driver none "$XRAY_IMAGE" uuid > "$f"
    echo "  создан: UUID для ${dev}"
  fi
done

# ---------------------------------------------------------------------------
# 6. Подстановка в рабочие конфиги
# ---------------------------------------------------------------------------
# Значения подставляются через файлы, а не через аргументы командной строки —
# иначе секрет был бы виден в выводе `ps`.
render() {
  local src="$1" dst="$2"
  [ -f "$src" ] || die "нет шаблона $src"

  # Промежуточный файл уже содержит настоящие секреты. Если python3 упадёт
  # посередине, ловушка не даст ему остаться на диске — тем более что
  # *.tmp не покрыт .gitignore.
  local tmp="$dst.tmp"
  trap 'rm -f "$tmp"' RETURN
  cp "$src" "$tmp"

  python3 - "$tmp" <<'PY'
import sys, pathlib, re
p = pathlib.Path(sys.argv[1])
s = p.read_text()
sec = pathlib.Path('secrets')
repl = {
    'REPLACE_ME_openssl_rand_base64_32': 'hy2_password.txt',
    'REPLACE_REALITY_PRIVATE_KEY':       'reality_private.txt',
    'REPLACE_16_HEX_CHARS':              'reality_shortid.txt',
    'REPLACE_UUID_MACBOOK':              'uuid_macbook.txt',
    'REPLACE_UUID_IPHONE':               'uuid_iphone.txt',
    'REPLACE_UUID_ANDROID':              'uuid_android.txt',
}
for token, name in repl.items():
    if token in s:
        f = sec / name
        if not f.exists():
            sys.exit(f'ОШИБКА: нет файла секрета {f} для токена {token}')
        s = s.replace(token, f.read_text().strip())
if 'REPLACE_' in s:
    left = sorted(set(re.findall(r'REPLACE_[A-Z0-9_]+', s)))
    sys.exit('ОШИБКА: остались незаполненные плейсхолдеры: ' + ', '.join(left))
p.write_text(s)
PY

  mv "$tmp" "$dst"
  chmod 600 "$dst"
  echo "  собран: $dst"
}

if [ $FORCE -eq 1 ] || ! have hysteria/config.yaml; then
  render hysteria/config.yaml.example hysteria/config.yaml
  # Проверка настоящим бинарником: Hysteria валидирует и YAML, и синтаксис ACL
  # (проверено — заведомо мусорное правило отвергается с «invalid syntax»).
  # Сертификаты монтируем, иначе сервер упадёт на их отсутствии, а не на конфиге.
  # Вывод сначала полностью собираем в переменную и только потом ищем в нём.
  # Через конвейер нельзя: `grep -q` выходит по первому совпадению, docker
  # получает SIGPIPE, и `set -o pipefail` объявляет весь конвейер упавшим —
  # успешная проверка выглядела бы как провал.
  hy_out=$(timeout 10 docker run --rm --log-driver none \
       -v "$(pwd)/hysteria/config.yaml:/etc/hysteria/config.yaml:ro" \
       -v "$(pwd)/hysteria/certs:/certs:ro" \
       tobyxdd/hysteria:v2.12.1 server -c /etc/hysteria/config.yaml 2>&1 || true)
  if printf '%s' "$hy_out" | grep -q "server up and running"; then
    echo "  проверен: hysteria/config.yaml — конфиг и ACL валидны"
  else
    printf '%s\n' "$hy_out" | head -5 >&2
    die "hysteria/config.yaml не прошёл проверку запуском"
  fi
else
  echo "  пропущен: hysteria/config.yaml уже существует (--force чтобы пересобрать)"
fi

if [ $FORCE -eq 1 ] || ! have xray/config.json; then
  render xray/config.json.example xray/config.json
  # Образ Xray distroless и работает под UID 65532. Файл, принадлежащий root
  # с правами 600, он прочитать НЕ может — проверено, -test падает с
  # «permission denied», а в compose это выглядело бы как падающий контейнер.
  # Отдаём файл этому UID, режим 600 сохраняем: мир его по-прежнему не читает.
  chown 65532:65532 xray/config.json \
    || die "не удалось сменить владельца xray/config.json на 65532 (нужен root)"
  # -test разбирает конфиг по настоящей схеме Xray, а не только проверяет,
  # что это валидный JSON.
  if docker run --rm --log-driver none \
       -v "$(pwd)/xray/config.json:/etc/xray/config.json:ro" \
       "$XRAY_IMAGE" -test -config /etc/xray/config.json >/dev/null 2>&1; then
    echo "  проверен: xray/config.json — схема валидна"
  else
    die "xray/config.json не прошёл проверку схемой Xray"
  fi
else
  echo "  пропущен: xray/config.json уже существует (--force чтобы пересобрать)"
fi

echo
echo "Готово. Секреты в ./secrets (chmod 600), в git не попадают."
echo "Ни одно значение намеренно не выведено на экран."
echo "Дальше: ./scripts/gen-client-configs.sh — соберёт конфиги клиентов."
echo
echo "ВАЖНО при пересборке конфигов (--force):"
echo "  docker compose restart НЕ подхватит новый файл. Bind-mount одиночного"
echo "  файла привязан к inode, а перезапись создаёт новый — контейнер продолжит"
echo "  читать старую версию. Наступали на это при откате DNS."
echo "  Нужно именно пересоздание:"
echo "     docker compose up -d --no-deps --force-recreate hysteria xray"
echo "  Флаг --no-deps обязателен: без него compose может тронуть wireguard,"
echo "  а SSH на этот сервер ходит только через его туннель."
