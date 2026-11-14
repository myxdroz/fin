#!/usr/bin/env bash
# Fin Strategy — установка одной командой (Debian/Ubuntu, в т.ч. LXC на Proxmox)
#
#   curl -fsSL -o /tmp/deploy.sh https://raw.githubusercontent.com/myxdroz/fin/main/deploy.sh \
#     && bash /tmp/deploy.sh
#
set -euo pipefail

REPO="https://github.com/myxdroz/fin.git"
INSTALL_DIR="${INSTALL_DIR:-/opt/fin}"
BRANCH="main"

c_ok()   { printf '\033[32m%s\033[0m\n' "$*"; }
c_info() { printf '\033[36m%s\033[0m\n' "$*"; }
c_warn() { printf '\033[33m%s\033[0m\n' "$*"; }
c_err()  { printf '\033[31m%s\033[0m\n' "$*"; }
step()   { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { c_err "Запустите от root: sudo bash deploy.sh"; exit 1; }

# ---------------------------------------------------------------- 1. Docker
step "Проверка Docker"
if ! command -v docker >/dev/null 2>&1; then
  c_info "Docker не найден — устанавливаю..."
  curl -fsSL https://get.docker.com | sh
else
  c_ok "Docker уже установлен ($(docker --version))"
fi
if ! docker compose version >/dev/null 2>&1; then
  c_info "Устанавливаю docker compose plugin..."
  apt-get update -qq && apt-get install -y -qq docker-compose-plugin
fi

# ---------------------------------------------------------------- 2. Код
step "Получение кода"
if [ -d "$INSTALL_DIR/.git" ]; then
  c_info "Каталог $INSTALL_DIR существует — обновляю (git pull)"
  git -C "$INSTALL_DIR" pull
else
  if [ -e "$INSTALL_DIR" ] && [ -n "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
    c_err "Каталог $INSTALL_DIR занят, но это не git-репозиторий. Удалите его или задайте INSTALL_DIR=/другой/путь"
    exit 1
  fi
  git clone --depth 1 --branch "$BRANCH" "$REPO" "$INSTALL_DIR"
  c_ok "Склонировано в $INSTALL_DIR"
fi
APP_VERSION="$(git -C "$INSTALL_DIR" rev-parse --short HEAD)"
c_info "Версия: $APP_VERSION"

# ---------------------------------------------------------------- 3. Провайдер данных
step "Настройка источника данных"
c_info "Котировки облигаций и акций всегда берутся с MOEX ISS API (бесплатно, без ключей)."
c_info "Дополнительно нужен источник истории дивидендов:"
printf '  1) T-Invest API — официально от Т-Банка (нужен токен, scope «только чтение»)\n'
printf '  2) Без токена — дивиденды парсятся со Smart-Lab (неофициально, менее надёжно)\n'
printf 'Выбор [1/2] (по умолчанию 2): '
read -r PROVIDER_CHOICE
PROVIDER_CHOICE="${PROVIDER_CHOICE:-2}"

TINVEST_TOKEN=""
if [ "$PROVIDER_CHOICE" = "1" ]; then
  printf 'Вставьте токен T-Invest API (ввод скрыт; создать: https://www.tbank.ru/invest/settings/api, scope «только чтение»):\n> '
  read -r -s TINVEST_TOKEN
  printf '\n'
  [ -n "$TINVEST_TOKEN" ] || { c_err "Токен пуст — отмена"; exit 1; }
  c_ok "Токен принят: ${TINVEST_TOKEN:0:8}...${TINVEST_TOKEN: -6}"
else
  c_warn "Работаем без токена T-Invest: раздел «Мой портфель» и лоты будут недоступны (нужен токен)."
fi

# ---------------------------------------------------------------- 4. .env и доступ
step "Защита доступа (basic auth)"
printf 'Логин для входа на сайт [fin]: '
read -r AUTH_LOGIN
AUTH_LOGIN="${AUTH_LOGIN:-fin}"
printf 'Пароль (ввод скрыт; Enter = без защиты, не рекомендуется для доступа извне): '
read -r -s AUTH_PASSWORD
printf '\n'
if [ -z "$AUTH_PASSWORD" ]; then
  c_warn "Без пароля: сервис открыт всем в вашей сети. Можно задать позже в $INSTALL_DIR/.env (FIN_AUTH_LOGIN/FIN_AUTH_PASSWORD)."
fi

step "Запись конфигурации (.env)"
# при повторном запуске сохраняем уже настроенные секреты
if [ -z "$TINVEST_TOKEN" ] && [ -f "$INSTALL_DIR/.env" ]; then
  TINVEST_TOKEN="$(grep '^FIN_TINVEST_TOKEN=' "$INSTALL_DIR/.env" | cut -d= -f2- || true)"
fi
if [ -z "$AUTH_PASSWORD" ] && [ -f "$INSTALL_DIR/.env" ]; then
  AUTH_PASSWORD="$(grep '^FIN_AUTH_PASSWORD=' "$INSTALL_DIR/.env" | cut -d= -f2- || true)"
fi
{
  echo "# сгенерировано deploy.sh $(date -Iseconds)"
  [ -n "$TINVEST_TOKEN" ] && echo "FIN_TINVEST_TOKEN=$TINVEST_TOKEN"
  echo "FIN_AUTH_LOGIN=$AUTH_LOGIN"
  [ -n "$AUTH_PASSWORD" ] && echo "FIN_AUTH_PASSWORD=$AUTH_PASSWORD"
} > "$INSTALL_DIR/.env"
chmod 600 "$INSTALL_DIR/.env"
c_ok ".env готов"

# ---------------------------------------------------------------- 5. Запуск
step "Сборка и запуск (3–5 минут при первом запуске)"
cd "$INSTALL_DIR"
export APP_VERSION
docker compose build --quiet
docker compose up -d

step "Ожидание готовности сервиса"
HEALTH_OK=""
for i in $(seq 1 30); do
  if curl -fsS "http://localhost:8000/api/health" >/dev/null 2>&1; then
    HEALTH_OK=1; break
  fi
  sleep 2
done

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
if [ -n "$HEALTH_OK" ]; then
  c_ok ""
  c_ok "Готово! Сервис работает:"
  c_ok "  LAN:      http://${IP:-<IP_сервера>}:8000"
  c_ok "  Локально: http://localhost:8000"
  c_info ""
  c_info "Версия: $(curl -fsS http://localhost:8000/api/health | grep -o '"version":"[^"]*"' | cut -d'"' -f4)"
  c_info "Данные с биржи подтягиваются в фоне 3–4 минуты (кнопка «Обновить данные» в шапке)."
  [ -z "$TINVEST_TOKEN" ] && c_info "Чтобы включить «Мой портфель»: добавьте FIN_TINVEST_TOKEN в $INSTALL_DIR/.env и выполните: cd $INSTALL_DIR && docker compose up -d"
  c_info "Обновление в будущем: cd $INSTALL_DIR && git pull && export APP_VERSION=\$(git rev-parse --short HEAD) && docker compose build && docker compose up -d"
else
  c_err "Сервис не ответил за 60 секунд. Логи: cd $INSTALL_DIR && docker compose logs -f"
  exit 1
fi
