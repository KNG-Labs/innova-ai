# Разработка и конфигурация

Все команды выполняются из корня репозитория. Для запуска через Compose нужны
Docker Engine и Docker Compose; для запуска на хосте — Python 3.13 и uv.

## Конфигурация

Шаблон настроек — [`.env.example`](../.env.example).
Для новой локальной установки создайте из него `.env`, если такого файла ещё нет.
Не перезаписывайте существующий файл с реальными секретами.

### LLM

```text
LLM_PROVIDER=stub|ag2
OPENROUTER_API_KEY
OPENROUTER_BASE_URL
AG2_MODEL
```

`stub` не требует внешнего ключа и используется для детерминированной разработки и автоматических тестов. `ag2` требует `OPENROUTER_API_KEY`; при отсутствии ключа приложение завершается на старте с ошибкой конфигурации.

Основной агент и retrieval planner используют одну модель AG2 и общий timeout.
Отдельные переменные окружения для planner не нужны. В режиме `stub` используется
управляемая заглушка planner.

### Векторные представления

```text
EMBEDDING_PROVIDER=fake|openrouter
EMBEDDING_MODEL
```

`fake` создаёт детерминированные векторы на основе токенов для локальной
разработки и тестов. `openrouter` использует тот же ключ и базовый адрес, что и
AG2. Выбранная модель должна возвращать векторы размерности **1536**.

### RAG

```text
RAG_TOP_K=5
RAG_MIN_SCORE=0.2
```

`RAG_TOP_K` задаёт размер пула семантических кандидатов для единственного
запроса, выбранного planner, а `RAG_MIN_SCORE` — минимальное косинусное сходство.
В итоговый контекст попадают один или два чанка только выбранного документа. API
и программа оценки качества (evaluation runner) должны использовать одинаковые
значения.

### Доставка лидов

```text
REDIS_URL
LEAD_DELIVERY_PROVIDER=disabled|fake|amocrm|webhook
AMOCRM_BASE_URL
AMOCRM_ACCESS_TOKEN
LEAD_WEBHOOK_URL
```

`disabled` сохраняет готовые лиды без постановки в очередь. `fake` используется
в тестах. `amocrm` создаёт сделку со встроенным контактом и добавляет примечание
с квалификацией. `webhook` отправляет плоский объект JSON по адресу
`LEAD_WEBHOOK_URL`.

### Доступ из браузера

`CORS_ALLOW_ORIGINS` содержит разрешённые источники запросов виджета через
запятую. Значение `*` удобно для локальной разработки; в развёрнутой установке
следует перечислить только доверенные домены дилера.

## Запуск через Docker Compose

Compose запускает PostgreSQL с pgvector, Redis, миграции, API и фоновый
обработчик доставки лидов.

Если `.env` ещё нет, скопируйте шаблон:

```bash
cp .env.example .env
```

Запустите API и worker вместе с их зависимостями:

```bash
docker compose up --build api worker
```

Для запуска Telegram-бота задайте `TELEGRAM_BOT_TOKEN` в локальном `.env`
и запустите все сервисы командой `docker compose up --build`.

API читает каталог проекта через bind mount в режиме read-only в `/workspace`;
зависимости Python остаются в `/app/.venv` из образа.
При сохранении Python-кода `uvicorn --reload` перезапускает процесс API внутри
того же контейнера. Для изменений статики достаточно обновить страницу.

Worker Celery и Telegram-бот используют код из собранного образа. Бот обращается
к текущему API по HTTP, а worker выполняет код доставки самостоятельно и работает
с общей БД. После изменения задач Celery, доставки, общих моделей БД или контракта
бота повторите запуск с `--build`, чтобы сервисы использовали согласованный код.

После изменения зависимостей обновите `uv.lock` командой `uv lock` и повторите
запуск с `--build`. После изменения `.env`, `docker-compose.yml` или `Dockerfile`
также повторите запуск. В конфигурации Docker Compose в PyCharm выберите
`Build → Always` и `Recreate containers → Changed configuration`.

Для применения изменений `migrations/` или `alembic.ini` выполните
`docker compose run --build --rm migrate`, затем повторите запуск сервисов.

После запуска доступны:

```text
API:         http://localhost:8000
OpenAPI:     http://localhost:8000/docs
Демо виджета: http://localhost:8000/static/widget-demo.html
PostgreSQL:  localhost:5433
Redis:       localhost:6379
```

Остановить сервисы:

```bash
docker compose down
```

Флаг `-v` удаляет данные PostgreSQL; используйте его только для ненужных
локальных данных. В производственной среде `docker compose down -v` запрещён.

## Локальная разработка

Установите зависимости:

```bash
uv sync --frozen
```

Для локального обучения используйте временную базу и заглушки. Рабочие `.env`
и `.env.production` содержат реальные секреты и не должны загружаться для проверок.

```bash
export APP_ENV_FILE=/dev/null
export PYTHON_DOTENV_DISABLED=1
docker compose --env-file /dev/null up -d --wait db redis
docker compose --env-file /dev/null exec -T db createdb -U innova innova_ai_test
```

В каждом терминале API/worker задайте одинаковое окружение:

```bash
export PYTHON_DOTENV_DISABLED=1
export DATABASE_URL=postgresql+asyncpg://innova:innova@127.0.0.1:5433/innova_ai_test
export TEST_DATABASE_URL="$DATABASE_URL"
export REDIS_URL=redis://127.0.0.1:6379/0
export LLM_PROVIDER=stub
export EMBEDDING_PROVIDER=fake
export LEAD_DELIVERY_PROVIDER=fake
```

Примените миграции и запустите процессы:

```bash
.venv/bin/alembic upgrade head
.venv/bin/uvicorn main:app --reload
# В другом терминале с тем же окружением:
.venv/bin/celery -A app.worker.lead_delivery:celery_app worker \
  --loglevel=INFO --concurrency=1 --queues=innova.lead_delivery
```

API и фоновый обработчик запускаются отдельными процессами и должны получать
одинаковые настройки PostgreSQL, Redis и способа доставки.
Повторы, состояние `needs_review` и ручная проверка описаны в
[инструкции Celery](operations/CELERY.md).

## Тестирование

Адрес тестовой базы по умолчанию:

```text
postgresql+asyncpg://innova:innova@localhost:5432/innova_ai_test
```

Для другого порта явно задайте `DATABASE_URL` и `TEST_DATABASE_URL` одной и той же
временной PostgreSQL-базе с именем, оканчивающимся на `_test` или `_eval`.
Пример для базы из Compose:

Интеграционные фикстуры пересоздают таблицы: данные выбранной тестовой базы
будут удалены. Используйте только временную базу с ненужными данными.

```bash
export APP_ENV_FILE=/dev/null
export PYTHON_DOTENV_DISABLED=1
export DATABASE_URL=postgresql+asyncpg://innova:innova@127.0.0.1:5433/innova_ai_test
export TEST_DATABASE_URL="$DATABASE_URL"
.venv/bin/alembic upgrade head
.venv/bin/alembic check
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export DEEPEVAL_DISABLE_DOTENV=1
export DEEPEVAL_TELEMETRY_OPT_OUT=YES
.venv/bin/python -m pytest -p pytest_asyncio.plugin -q
```

Отдельные проверки:

```bash
.venv/bin/python -m pytest -p pytest_asyncio.plugin tests/unit -q
.venv/bin/python -m pytest -p pytest_asyncio.plugin -m integration -q
.venv/bin/python -m pytest -p pytest_asyncio.plugin -m integration_crm_fake -q
uv run ruff format --check app tests main.py
uv run ruff check app tests main.py
uv run mypy app/ --ignore-missing-imports
```

Автоматические тесты используют заглушки LLM, векторизации, очереди и CRM там,
где внешние сервисы не являются предметом проверки. В этой ветке проверена цепочка
«API → Redis → Celery → локальный webhook» с заглушкой LLM, включая повторную
выдачу после `SIGKILL` дочернего worker без повторного создания сделки.
Настоящие amoCRM и LLM в эти проверки не входят.
