# Руководство для агентов Innova AI

## Область действия

Эти инструкции применяются ко всему репозиторию.

## Контекст проекта

- Python 3.13, FastAPI, SQLAlchemy, Alembic, PostgreSQL 17 с pgvector.
- Воркер доставки лидов использует Redis; Telegram-коннектор работает через long polling.
- OpenRouter предоставляет LLM и embeddings; производственные лиды передаются в AmoCRM.
- Целевая среда развёртывания — VPS одного дилера на Ubuntu 26.04.

## Обязательные правила безопасности

- Никогда не читать, не выводить, не копировать и не изменять `.env` или
  `.env.production`, если пользователь явно не запросил требующую этого операцию.
- Оба env-файла содержат реальные секреты и намеренно не отслеживаются Git.
- Локальный `.env` указывает на существующую производственную базу данных.
- Никогда не запускать Alembic без явно заданного безопасного `DATABASE_URL`.
- Тесты и оценки можно запускать только с временными базами данных, имена которых
  оканчиваются на `_test` или `_eval`.
- Никогда не запускать `docker compose down -v` в производственной среде.
- Никогда не выполнять реальное развёртывание, не подключаться к VPS, не публиковать
  образ и не менять настройки GitHub без отдельного подтверждения пользователя.
- Никогда не коммитить env-файлы, учётные данные, SSH-ключи, токены доступа и
  сгенерированные секреты.
- Не изменять ignore-файлы ради добавления `AGENTS.md`, `.agents`, `.codex` или
  других файлов Codex. Владелец репозитория сам определяет, что следует коммитить.
- Не отменять и не перезаписывать несвязанные изменения пользователя в грязном
  рабочем дереве.
- Сохранять изменения пользователя в `.dockerignore`.

## Проверка

Статические проверки:

```bash
uv sync --frozen
uv run ruff format --check app tests main.py
uv run ruff check app tests main.py
uv run mypy app/ --ignore-missing-imports
```

Запускать миграции и pytest только после явного назначения обоих URL одной и той же
временной базе PostgreSQL:

```bash
export DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:PORT/innova_ai_test
export TEST_DATABASE_URL="$DATABASE_URL"
uv run alembic upgrade head
uv run alembic check
uv run pytest -q
```

Не подключать ни один локальный env-файл для запуска проверок. Проверять
производственный Compose только с фиктивными значениями и явно заданным пустым
env-файлом, например `/dev/null`.

## Поведение CI/CD

Единственный workflow находится в `.github/workflows/pipeline.yml`:

- pull request в `main` запускает проверки, миграции, тесты, сборку и инспекцию
  Docker-образа без публикации и развёртывания;
- push в `main` публикует проверенный образ
  `ghcr.io/kng-labs/innova-ai:<полный-git-sha>` и развёртывает его;
- остальные ветки не запускают этот workflow;
- CI и CD остаются отдельными jobs, а разрешение `packages: write` есть только у CD;
- проверенный образ передаётся между jobs как артефакт со сроком хранения один день;
- развёртывание начинается только после публикации образа с SHA-тегом.

Не разделять CI и CD на отдельные workflow-файлы, пока веткой GitHub по умолчанию
остаётся `main`.

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
его отдельно, а не копировать локальный `.env`.

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

## Известные эксплуатационные ограничения

- Доставка воркером не имеет устойчивого подтверждения или гарантии exactly-once.
- Воркер и Telegram-сервис не завершают работу корректно при `SIGTERM`.
- Проверки работоспособности не проверяют внешних провайдеров.
- Базовые Docker-образы не закреплены за digest.
- Никогда не называть откат приложения откатом базы данных.
