Инструкция по первичной настройке сервера

## Подготовка VPS

VPS нужен статический публичный адрес, доступный по SSH. Домен и reverse proxy сейчас
не требуются. PostgreSQL и Redis не должны публиковать порты хоста; API привязывается
только к `127.0.0.1:8000`.

Установить Docker Engine и Compose plugin с поддержкой `docker compose up --wait` из
официального APT-репозитория Docker:

```bash
docker compose up --help | grep -- --wait
```

Создать учётную запись для развёртывания и каталоги:

```bash
sudo adduser --disabled-password --gecos "" deploy
sudo usermod -aG docker deploy
sudo install -d -m 755 -o deploy -g deploy /opt/innova
sudo install -d -m 700 -o deploy -g deploy \
  /opt/innova/shared /opt/innova/releases /opt/innova/backups
```

Использовать отдельный SSH-ключ для развёртывания в
`/home/deploy/.ssh/authorized_keys`. Членство в группе `docker` фактически даёт
административный доступ к хосту, поэтому ключ должен использоваться только для
развёртывания.

Для приватного пакета GHCR один раз аутентифицировать Docker на VPS с токеном, у
которого есть только разрешение `read:packages`. Никогда не хранить этот токен в
репозитории.

## Производственное окружение

Файл среды выполнения на VPS — `/opt/innova/shared/.env` с правами `600`. Создать
его отдельно, а не копировать локальный `../../.env`.

Обязательные имена переменных:

```text
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD
DATABASE_URL
REDIS_URL
OPENROUTER_API_KEY
LLM_PROVIDER
EMBEDDING_PROVIDER
LEAD_DELIVERY_PROVIDER
AMOCRM_BASE_URL
AMOCRM_ACCESS_TOKEN
TELEGRAM_BOT_TOKEN
INNOVA_API_URL
```

Инварианты производственной среды:

- `DATABASE_URL` использует Compose-хост `db`;
- `REDIS_URL` использует Compose-хост `redis`;
- `INNOVA_API_URL` использует внутренний сервис `api` на порту `8000`;
- `LLM_PROVIDER` равен `ag2`;
- `EMBEDDING_PROVIDER` равен `openrouter`;
- `LEAD_DELIVERY_PROVIDER` равен `amocrm`.

Секреты среды выполнения остаются на VPS и не загружаются из GitHub Actions при
каждом выпуске.

## Настройки GitHub

Создать GitHub Environment с именем `production` без обязательных проверяющих и
правил защиты развёртывания. Настроить следующие секреты репозитория или Environment:

```text
VPS_HOST
VPS_PORT
VPS_USER
VPS_SSH_PRIVATE_KEY
VPS_SSH_KNOWN_HOSTS
```

Перед добавлением ключа хоста VPS в `VPS_SSH_KNOWN_HOSTS` проверить его fingerprint
через консоль провайдера. Никогда не принимать неизвестный ключ хоста внутри workflow.

## Операции развёртывания

Первое успешное развёртывание создаёт тома PostgreSQL и Redis, применяет миграции
Alembic и запускает API, воркер и Telegram-сервис. Каждое развёртывание:

1. захватывает `/opt/innova/shared/deploy.lock`;
2. загружает образ с запрошенным SHA-тегом;
3. ожидает готовности PostgreSQL и Redis;
4. создаёт сжатую резервную копию через `pg_dump`;
5. применяет `alembic upgrade head`;
6. запускает API, воркер и Telegram-сервис;
7. ожидает готовности и записывает состояние текущего и предыдущего выпуска.

Резервные копии хранятся в `/opt/innova/backups` 14 дней. Скрипты развёртывания
никогда не удаляют производственные тома.

Проверка текущего выпуска на VPS:

```bash
export APP_IMAGE="$(cat /opt/innova/shared/current-image)"
export APP_ENV_FILE=/opt/innova/shared/.env
docker compose --env-file "$APP_ENV_FILE" \
  -f /opt/innova/current/docker-compose.prod.yml ps
docker compose --env-file "$APP_ENV_FILE" \
  -f /opt/innova/current/docker-compose.prod.yml \
  logs --tail=200 api worker telegram-bot
curl --fail http://127.0.0.1:8000/health
```

`GET /health` сообщает об успехе, только если FastAPI может выполнить запрос к
PostgreSQL. Он не проверяет Redis, Telegram, AmoCRM, OpenRouter и сквозную доставку
лида.

Перед первым переходом на Celery остановить старый Redis worker и дождаться
завершения активных доставок. Его сообщения несовместимы с Celery: оставшиеся
`ready`/`delivery_failed`-лиды проверяются по CRM и публикуются явно после миграций.
Проверка статуса, повтор задания и ручное разрешение `needs_review` описаны
в [инструкции Celery](CELERY.md).

## RAG через SSH

Никогда не публиковать административные endpoints базы знаний. Открыть туннель с
локальной машины:

```bash
ssh -L 18000:127.0.0.1:8000 deploy@VPS_IP
```

После этого Swagger доступен локально по адресу `http://127.0.0.1:18000/docs`.
Загрузить массив JSON-документов через туннель:

```bash
curl --fail-with-body \
  -H 'Content-Type: application/json' \
  --data-binary @knowledge.json \
  http://127.0.0.1:18000/knowledge/documents
```

## Откат

Если проверка работоспособности API завершается ошибкой и существует предыдущий
успешный выпуск, выполняется автоматический откат. Ручной откат:

```bash
bash /opt/innova/current/scripts/rollback.sh \
  "$(cat /opt/innova/shared/previous-image)" \
  "$(cat /opt/innova/shared/previous-release)"
```

Откат меняет код приложения и конфигурацию Compose, но никогда не запускает
`alembic downgrade`. Миграции должны оставаться совместимыми с предыдущим образом:
сначала добавить схему, затем перевести код и только в одном из последующих выпусков
удалить старую схему.
