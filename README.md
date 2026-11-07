# Fin Strategy

Персональный сервис подбора стратегии вложений в облигации и акции МосБиржи (MOEX ISS API).
Скринеры бумаг + подбор портфеля под профиль риска.

## Возможности

- **Скринер облигаций** — фильтры по доходности, дюрации, ликвидности, уровню листинга, цене; без флоатеров/оферт, только ОФЗ.
- **Скринер акций** — дивидендная доходность за 12 мес, ликвидность, эшелон.
- **Подбор портфеля** — консервативный / умеренный / агрессивный / голубые фишки, сумма портфеля,
  лестница облигаций, расчёт ожидаемой доходности. Количество позиций подгоняется под сумму,
  чтобы на каждую хватало хотя бы на один лот.
- Автосинхронизация с MOEX ежедневно в 00:00 МСК (21:00 UTC), плюс кнопка ручного обновления в интерфейсе.

## Запуск локально

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Открыть http://localhost:8000 (при первом старте данные подтягиваются ~1–2 минуты).

## Развёртывание в LXC на Proxmox

### 1. Создать контейнер

В веб-интерфейсе Proxmox: **Create CT** → шаблон Debian 12 или Ubuntu 22.04, 1 CPU / 1–2 GB RAM / 8+ GB диска.
Включить nesting для Docker (Options → Features → Nesting), либо использовать ** privileged контейнер**.

Либо через CLI:

```bash
pct create 200 local:vztmpl/ubuntu-22.04-standard_22.04-2_amd64.tar.zst \
  --hostname fin --cores 1 --memory 2048 --rootfs local-lvm:8 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp --features nesting=1
pct start 200
pct enter 200
```

### 2. Установить Docker в контейнере

```bash
curl -fsSL https://get.docker.com | sh
apt install -y docker-compose-plugin
```

### 3. Загрузить проект и запустить

```bash
git clone <repo-url> /opt/fin && cd /opt/fin
docker compose up -d --build
```

Сервис будет доступен на `http://<IP_контейнера>:8000`.

### 4. (Опционально) Reverse proxy с HTTPS

```bash
apt install -y nginx certbot python3-certbot-nginx
```

Конфиг nginx (`/etc/nginx/sites-available/fin`):

```nginx
server {
    listen 80;
    server_name fin.example.com;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
ln -s /etc/nginx/sites-available/fin /etc/nginx/sites-enabled/
certbot --nginx -d fin.example.com
```

Для доступа извне лучше добавить простейшую авторизацию (например, `htpasswd` + `auth_basic` в nginx), т.к. сервис публичный по умолчанию.

## API

| Метод | Путь | Описание |
|---|---|---|
| GET | `/api/health` | Статус + ключевая ставка |
| POST | `/api/sync` | Принудительная синхронизация с MOEX |
| GET | `/api/profiles` | Описания профилей риска |
| POST | `/api/bonds` | Скринер облигаций (тело — фильтры) |
| POST | `/api/shares` | Скринер акций |
| POST | `/api/portfolio` | Подбор портфеля: `{"profile": "moderate", "amount": 1000000}` |

Документация FastAPI: `/docs`.

## Конфигурация (переменные окружения, префикс `FIN_`)

| Переменная | По умолчанию | Описание |
|---|---|---|
| `FIN_DATABASE_URL` | `sqlite:////data/fin.db` | БД |
| `FIN_SYNC_ON_STARTUP` | `true` | Синхронизация при старте |
| `FIN_SCHEDULER_ENABLED` | `true` | Ежедневная авто-синхронизация |
| `FIN_KEY_RATE` | `15.0` | Запасная ключевая ставка (авто из MOEX) |
| `FIN_TINVEST_TOKEN` | — | Токен T-Invest API (read-only). Задан — дивиденды официально от Т-Банка; не задан — парсинг Smart-Lab |

## Дисклеймер

Сервис не является источником индивидуальной инвестиционной рекомендации (ИИР).
Данные MOEX могут быть с задержкой, расчёты — упрощённые. Инвестиции сопряжены с риском потери капитала.
