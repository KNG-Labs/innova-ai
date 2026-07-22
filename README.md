# Innova AI

Innova AI — диалоговый сервис лидогенерации для автодилеров. Посетитель сайта может задать вопрос, получить ответ на основе базы знаний дилера, указать интересующий автомобиль и условия покупки, оставить контакт и создать лид, который будет асинхронно доставлен в CRM.

Текущая реализация рассчитана на установку для одного дилера и канал website. Backend хранит историю и бизнес-состояние диалога в PostgreSQL, использует AG2/OpenRouter или детерминированный stub для обработки сообщений, получает релевантный контекст через pgvector и передаёт готовые лиды отдельному Redis-worker.

## Возможности

- multi-turn диалог через `POST /message`;
- анонимные пользователи и активные диалоговые сессии;
- сохранение сообщений пользователя и ассистента;
- управляемая backend-кодом машина состояний;
- квалификация по `car_model`, `budget` и `purchase_type`;
- сбор контакта через `phone`, `email` или `telegram`;
- статусы лида `draft`, `ready`, `delivered` и `delivery_failed`;
- ручная загрузка базы знаний и семантический поиск;
- AG2 через OpenRouter с безопасным fallback;
- асинхронная доставка лидов через Redis и отдельный worker;
- режимы доставки AmoCRM, webhook, fake и disabled;
- API для чтения сессий, сообщений, лидов и базы знаний;
- встраиваемый JavaScript-виджет и демонстрационная страница.

## Технологии

- Python 3.13
- FastAPI и Pydantic
- SQLAlchemy asyncio и asyncpg
- PostgreSQL 17 с pgvector
- Alembic
- Redis
- AG2 (AutoGen) через OpenRouter
- httpx
- pytest, Ruff и mypy
- uv

## Обработка сообщения

```text
Виджет / прямой API-вызов
  -> POST /message
  -> AgentService
  -> поиск или создание анонимного пользователя и активной сессии
  -> загрузка истории сообщений и текущего лида
  -> поиск релевантных фрагментов базы знаний
  -> AG2 client или детерминированный stub
  -> объединение извлечённой квалификации и контакта
  -> проверка перехода backend-машиной состояний
  -> сохранение сообщений, сессии и лида
  -> commit транзакции PostgreSQL
  -> постановка готового лида в Redis
  -> ответ пользователю
```

Доставка выполняется независимо от HTTP-запроса:

```text
Redis queue
  -> app.worker.lead_delivery
  -> LeadDeliveryService
  -> AmoCRM / webhook / fake adapter
  -> lead.status = delivered | delivery_failed
```

PostgreSQL является источником истины для пользователей, сессий, сообщений, лидов и документов базы знаний. Redis используется только как очередь доставки лидов.

## Состояния диалога

Разрешённые переходы:

| Текущее состояние | Следующее состояние |
|---|---|
| `GREETING` | `FAQ`, `QUALIFICATION`, `CONTACT_CAPTURE` |
| `FAQ` | `FAQ`, `QUALIFICATION`, `CONTACT_CAPTURE` |
| `QUALIFICATION` | `QUALIFICATION`, `CONTACT_CAPTURE`, `CLOSED` |
| `CONTACT_CAPTURE` | `FAQ`, `CONTACT_CAPTURE`, `LEAD_READY`, `CLOSED` |
| `LEAD_READY` | `CLOSED` |
| `CLOSED` | нет переходов |

LLM предлагает переход, извлекает данные и формирует ответ. Backend проверяет допустимость перехода и самостоятельно вычисляет недостающие поля. Переход в `LEAD_READY` разрешён только при наличии всех квалификационных полей и хотя бы одного поддерживаемого способа связи.

Изменения квалификации LLM возвращает как patch во внутреннем поле
`qualification_patch`. Отсутствующий ключ не изменяет сохранённые данные, строковое
значение устанавливает или заменяет поле, а `null` удаляет ранее сохранённое
значение. Backend принимает только `car_model`, `budget` и `purchase_type`.

Сообщение без контакта само по себе не считается отказом. Backend учитывает только
явные отказы предоставить контакт, которые LLM возвращает во внутреннем поле
`contact_preference` со значением `refusal`. После второго отказа сессия остаётся
открытой, переходит в `FAQ` и больше не запрашивает контакт. Значение `resume`
возобновляет квалификацию по явному запросу пользователя. Публичный response
`POST /message` поле `contact_preference` не содержит.

`LEAD_READY` и `CLOSED` завершают текущую сессию. Следующее сообщение создаёт новую сессию, даже если клиент повторно передал ID завершённой.

## API

После запуска интерактивная OpenAPI-документация доступна по адресу `http://localhost:8000/docs`.

### POST /message

Создаёт или продолжает диалог.

```json
{
  "anonymous_id": "browser-user-1",
  "channel": "website",
  "session_id": null,
  "content": "Ищу Toyota Camry до 3 миллионов",
  "page_title": "Toyota Camry в наличии"
}
```

| Поле | Обязательное | Описание |
|---|---:|---|
| `anonymous_id` | да | Стабильный ID, созданный клиентом; от 3 до 128 символов |
| `channel` | нет | `website`, `telegram` или `avito`; по умолчанию `website` |
| `session_id` | нет | UUID существующей активной сессии |
| `content` | да | Сообщение пользователя; от 1 до 4000 символов |
| `page_title` | нет | Нормализованный заголовок страницы; не более 200 символов |

API-схема принимает значения каналов `telegram` и `avito`, но готовых коннекторов для них в репозитории нет. Реализованные точки входа — website-виджет и прямой API-вызов.

Пример ответа:

```json
{
  "user_id": "0c336b9b-6a7e-4494-8af1-e6302b87956f",
  "session_id": "c75f9b38-b169-4901-a3e1-9335d4d7ff6a",
  "user_message_id": "57c7b362-4b4d-4e5f-8a9b-1c2d3e4f5a6b",
  "assistant_message_id": "bb9ffb5f-d98c-4cc2-bf7e-c6e5dfde4b63",
  "answer": "Какой способ покупки вы рассматриваете?",
  "state": "QUALIFICATION",
  "intent": "lead_request",
  "next_step": "QUALIFICATION",
  "missing_fields": ["purchase_type", "contact"],
  "lead_id": "9f1c0c2a-3b4d-4e5f-8a9b-1c2d3e4f5a6b"
}
```

### Сессии и сообщения

```text
GET /sessions/{session_id}
GET /sessions/{session_id}/messages
```

Первый endpoint возвращает состояние и владельца сессии. Второй возвращает сохранённую историю сообщений в порядке создания.

### Лиды

```text
GET  /leads
GET  /leads?status=ready
GET  /leads/{lead_id}
POST /leads/{lead_id}/deliver
```

`GET /leads` возвращает облегчённые элементы списка. `GET /leads/{lead_id}` дополнительно содержит квалификацию, контакт, summary, статус доставки и последнюю ошибку.

`POST /leads/{lead_id}/deliver` синхронно повторяет доставку без Redis. Endpoint возвращает `404` для неизвестного лида и `409` для лида в недопустимом статусе, например `draft`.

### База знаний

```text
GET  /knowledge/documents
POST /knowledge/documents
POST /knowledge/reindex
```

Документы загружаются вручную JSON-массивом:

```json
[
  {
    "title": "Toyota Camry",
    "source": "manual",
    "content": "Toyota Camry доступна в комплектациях ..."
  }
]
```

Текст делится на пересекающиеся фрагменты, преобразуется в embeddings и сохраняется в PostgreSQL через pgvector. После смены embedding-модели необходимо вызвать `POST /knowledge/reindex`, чтобы пересоздать векторы всех документов.

## Конфигурация

Создайте локальный конфигурационный файл из шаблона:

```bash
cp .env.example .env
```

Не добавляйте `.env` и реальные API-токены в Git.

### LLM

```text
LLM_PROVIDER=stub|ag2
OPENROUTER_API_KEY
OPENROUTER_BASE_URL
AG2_MODEL
```

`stub` не требует внешнего ключа и используется для детерминированной разработки и автоматических тестов. `ag2` требует `OPENROUTER_API_KEY`; при отсутствии ключа приложение завершается на старте с ошибкой конфигурации.

### Embeddings

```text
EMBEDDING_PROVIDER=fake|openrouter
EMBEDDING_MODEL
```

`fake` создаёт детерминированные token-based векторы для локальной разработки и тестов. `openrouter` использует тот же ключ и base URL, что и AG2. Выбранная модель должна возвращать векторы размерности 1536.

### RAG

```text
RAG_TOP_K=3
RAG_MIN_SCORE=0.2
```

`RAG_TOP_K` задаёт максимальное число фрагментов контекста, `RAG_MIN_SCORE` —
минимальную cosine similarity. API и evaluation runner должны использовать
одинаковые значения.

### Доставка лидов

```text
REDIS_URL
LEAD_DELIVERY_PROVIDER=disabled|fake|amocrm|webhook
AMOCRM_BASE_URL
AMOCRM_ACCESS_TOKEN
LEAD_WEBHOOK_URL
```

`disabled` сохраняет готовые лиды без постановки в очередь. `fake` используется в тестах. `amocrm` создаёт сделку со встроенным контактом и добавляет примечание с квалификацией. `webhook` отправляет плоский JSON payload по адресу `LEAD_WEBHOOK_URL`.

### Доступ из браузера

`CORS_ALLOW_ORIGINS` содержит разрешённые origins виджета через запятую. Значение `*` удобно для локальной разработки; в развёрнутой установке следует перечислить только доверенные домены дилера.

## Запуск через Docker Compose

Compose запускает PostgreSQL с pgvector, Redis, миграции, API и worker доставки лидов.

```bash
cp .env.example .env
docker compose up --build
```

После запуска доступны:

```text
API:         http://localhost:8000
OpenAPI:     http://localhost:8000/docs
Widget demo: http://localhost:8000/static/widget-demo.html
PostgreSQL:  localhost:5433
Redis:       localhost:6379
```

Остановить сервисы:

```bash
docker compose down
```

Флаг `-v` следует добавлять только тогда, когда вместе с контейнерами нужно удалить данные PostgreSQL.

## Локальная разработка

Установите зависимости:

```bash
uv sync
```

Запустите инфраструктуру:

```bash
docker compose up -d db redis
```

Если приложение работает на хосте с PostgreSQL из Compose, используйте порт `5433`:

```text
DATABASE_URL=postgresql+asyncpg://innova:innova@localhost:5433/innova_ai
REDIS_URL=redis://localhost:6379/0
```

Примените миграции и запустите процессы:

```bash
uv run alembic upgrade head
uv run uvicorn main:app --reload
uv run python -m app.worker.lead_delivery
```

API и worker запускаются отдельными процессами и должны получать одинаковые настройки PostgreSQL, Redis и delivery provider.

## Веб-виджет

Виджет раздаётся через FastAPI:

```html
<script
  src="http://localhost:8000/static/widget.js"
  data-api-base="http://localhost:8000">
</script>
```

Демонстрационная страница:

```text
http://localhost:8000/static/widget-demo.html
```

Виджет хранит `anonymous_id` и ID активной сессии в `localStorage`, передаёт `document.title` в `page_title` и удаляет `session_id`, когда backend возвращает `LEAD_READY` или `CLOSED`.

## Тестирование

Адрес тестовой базы по умолчанию:

```text
postgresql+asyncpg://innova:innova@localhost:5432/innova_ai_test
```

Переопределите его через `TEST_DATABASE_URL`, если PostgreSQL работает на другом порту. Для базы из Compose:

```bash
docker compose exec db createdb -U innova innova_ai_test
TEST_DATABASE_URL=postgresql+asyncpg://innova:innova@localhost:5433/innova_ai_test \
  uv run pytest -q
```

Отдельные проверки:

```bash
uv run pytest tests/unit -q
uv run pytest -m integration -q
uv run pytest -m integration_crm_fake -q
uv run ruff check .
uv run mypy app/ --ignore-missing-imports
```

Автоматические тесты используют fake-адаптеры LLM, embeddings, очереди и CRM там, где внешние сервисы не являются предметом проверки. Полный сценарий widget -> real AG2 -> lead -> Redis worker -> AmoCRM также проверен вручную.

## Evaluation datasets

Версионируемые golden datasets находятся в `evals/datasets/` и содержат 100
retrieval, 48 generation и 12 сквозных business-кейсов. Наборы разделены на
`calibration`, закрытый `test` и критический `regression`. Проверить схему и
покрытие без запуска приложения:

```bash
uv run python -m evals.runners.evaluate --dataset evals/datasets
```

Evaluation нельзя запускать на рабочей БД. Можно использовать тот же экземпляр
PostgreSQL, но runner по умолчанию принимает только логическую БД с суффиксом
`_eval` или `_test`. Он сверяет SHA-256 полного 50-документного корпуса с manifest,
очищает knowledge-таблицы eval-БД и индексирует точную копию корпуса заново:

```bash
docker compose exec db createdb -U innova innova_ai_eval
DATABASE_URL=postgresql+asyncpg://innova:innova@localhost:5433/innova_ai_eval \
  uv run alembic upgrade head
```

Для generation/business запустите отдельный API-процесс с этой же eval-БД, затем
выполните минимум три повтора недетерминированной модели:

```bash
DATABASE_URL=postgresql+asyncpg://innova:innova@localhost:5433/innova_ai_eval \
  uv run uvicorn main:app --port 8001

EVAL_DATABASE_URL=postgresql+asyncpg://innova:innova@localhost:5433/innova_ai_eval \
INNOVA_EVAL_API_URL=http://localhost:8001 \
  uv run python -m evals.runners.run --repetitions 3 \
  --split test --split regression
```

Полностью изолированный запуск доступен через `docker-compose.eval.yml`:

```bash
EVAL_REPORT_NAME=before-rag \
  docker compose -f docker-compose.eval.yml up --build \
  --abort-on-container-exit --exit-code-from eval-runner eval-runner
docker compose -f docker-compose.eval.yml down
```

Runner пишет одноразовые отчёты в `evals/reports/runs/`. Для презентации baseline
нужно явно сохранить под версионированным именем в
`evals/reports/baselines/`; такие файлы не игнорируются Git. Отчёт включает
знаменатель `n`, срезы по типу/split/category, latency p50/p95, разброс между
повторами, модели, параметры retrieval и хэши данных. Git SHA и dirty-флаг
передаются в Docker-запуск через `EVAL_GIT_COMMIT` и `EVAL_GIT_DIRTY`.
Полный протокол и определения метрик описаны в `evals/README.md`.

## Известные ограничения

- Одна установка обслуживает одного дилера; tenant model и tenant isolation отсутствуют.
- Не реализованы authentication, roles и operator dashboard.
- Website/API — единственный готовый входной канал; коннекторы Telegram и Avito отсутствуют.
- Документы базы знаний загружаются вручную; crawler и file upload pipeline отсутствуют.
- Для контакта требуется непустой phone, email или Telegram, но формат значения не проверяется.
- Redis-worker не реализует retry, backoff, dead-letter queue и durable acknowledgement.
- При ошибке постановки в очередь лид остаётся в `ready`; доставку нужно повторить через `POST /leads/{lead_id}/deliver`.
- Доставка не имеет гарантии exactly-once; повтор неоднозначно завершившегося CRM-запроса может создать дубликат.
- Доступность LLM, embeddings, CRM и webhook зависит от внешних провайдеров.
- Не реализованы rate limiting, production monitoring, audit logs и формализованные меры соответствия требованиям к персональным данным.

## Структура репозитория

```text
app/
  client/       AG2, embeddings, Redis queue и CRM adapters
  db/           настройка SQLAlchemy engine и sessions
  models/       ORM-модели PostgreSQL
  repository/   операции с хранилищем
  router/       FastAPI routes
  schemas/      публичные и внутренние Pydantic contracts
  service/      логика диалога, базы знаний, лидов и доставки
  worker/       процесс доставки лидов из Redis
docs/           продуктовые документы, current/target диаграммы, RAG data
migrations/     Alembic environment и revisions
static/         виджет, demo page и изображения дилера
tests/          unit, integration и end-to-end tests
```

## Документация

- `docs/PRD.md` описывает расширенное продуктовое видение и будущие возможности.
- `docs/System_Design.md` описывает целевую архитектуру платформы, а не только уже реализованный код.
- `docs/diagrams/current/` содержит диаграммы реализованной архитектуры и сценариев.
- `docs/diagrams/target/` содержит диаграммы целевого состояния.
- `docs/RAG/` содержит исходные материалы для загрузки в базу знаний.

Источником истины по реализованному поведению, конфигурации и эксплуатационным ограничениям является этот README.
