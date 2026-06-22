# Innova AI

AI-ассистент для лидогенерации и клиентской коммуникации в digital-каналах. Проект развивается из простого LLM endpoint в backend агентного диалога с памятью, сессиями, историей сообщений, lead-flow и асинхронной доставкой лида в CRM.

> Scope и план реализации: [docs/MVP_ROADMAP.md](docs/MVP_ROADMAP.md)

---

## Что это

Innova AI — backend-слой conversational AI продукта. Сервис принимает сообщение пользователя, определяет намерение, создаёт или продолжает диалоговую сессию, сохраняет историю сообщений в PostgreSQL и возвращает ответ агента.

Сейчас проект реализует полный lead conversion loop:

- анонимный пользователь;
- диалоговая сессия;
- история сообщений;
- детерминированная state machine (переходы решает код, не LLM);
- квалификация по обязательным полям (`car_model` / `budget` / `purchase_type`);
- сборка карточки лида: `draft → ready`;
- генерация ответа через AG2/LLM-клиент или stub-клиент;
- асинхронная доставка `ready`-лида в CRM через Redis-очередь и worker;
- read-routes для проверки памяти агента и просмотра лидов.

Доставка лида в AmoCRM (создание сделки + контакта) реализована. Telegram/webhook остаются как backup/debug destination.

---

## Стек

- Python 3.13
- FastAPI
- Pydantic
- SQLAlchemy asyncio
- PostgreSQL
- Alembic
- Redis (очередь доставки)
- httpx
- AG2 (AutoGen) через OpenRouter
- pytest / pytest-asyncio
- uv

---

## Структура репозитория

```text
INNOVA_AI/
├── app
│   ├── client
│   │   ├── __init__.py
│   │   ├── ag2_agent_client.py
│   │   ├── crm_client.py
│   │   ├── delivery_factory.py
│   │   ├── queue_client.py
│   │   └── vector_client.py
│   ├── db
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── session.py
│   ├── models
│   │   ├── __init__.py
│   │   ├── dialog_session_model.py
│   │   ├── lead_model.py
│   │   ├── message_model.py
│   │   └── user_model.py
│   ├── repository
│   │   ├── __init__.py
│   │   ├── dialog_session_repository.py
│   │   ├── lead_repository.py
│   │   ├── message_repository.py
│   │   └── user_repository.py
│   ├── router
│   │   ├── __init__.py
│   │   ├── lead_router.py
│   │   ├── message_router.py
│   │   └── session_router.py
│   ├── schemas
│   │   ├── __init__.py
│   │   ├── agent_schema.py
│   │   ├── lead_delivery_schema.py
│   │   ├── lead_schema.py
│   │   └── session_schema.py
│   ├── service
│   │   ├── __init__.py
│   │   ├── agent_service.py
│   │   ├── business_service.py
│   │   ├── lead_delivery_service.py
│   │   ├── lead_service.py
│   │   ├── session_service.py
│   │   └── state_machine.py
│   ├── worker
│   │   ├── __init__.py
│   │   └── lead_delivery.py
│   ├── __init__.py
│   ├── di.py
│   ├── domain.py
│   └── exceptions.py
├── docs
│   ├── diagrams
│   │   ├── Components.puml
│   │   ├── DataBase.puml
│   │   └── Sequence.puml
│   ├── MVP_ROADMAP.md
│   ├── PRD.md
│   └── System_Design.md
├── migrations
│   ├── versions
│   │   ├── 8cd1e0d95b7a_create_tables.py
│   │   ├── 21a80ea32600_fk_ondelete_restrict.py
│   │   ├── 412db7507c59_add_contact_attempts_to_dialog_sessions.py
│   │   ├── a8ffd1220905_add_last_delivery_error_to_leads.py
│   │   └── ee6e74045934_soft_delete_deleted_at_partial_unique_.py
│   ├── README
│   ├── env.py
│   └── script.py.mako
├── tests
│   ├── e2e
│   │   ├── __init__.py
│   │   └── test_agent_message.py
│   ├── integration
│   │   ├── __init__.py
│   │   ├── test_agent_message.py
│   │   ├── test_lead_delivery_fake.py
│   │   ├── test_leads.py
│   │   ├── test_message_enqueue.py
│   │   └── test_sessions_session_id.py
│   ├── unit
│   │   ├── __init__.py
│   │   ├── test_ag2_flow.py
│   │   └── test_crm_payload_mapping.py
│   ├── __init__.py
│   └── conftest.py
├── README.md
├── alembic.ini
├── main.py
└── pyproject.toml
```




## Текущая реализация

Реализован полный agent-flow с памятью в PostgreSQL и доставкой лида.

`POST /message` принимает одно сообщение пользователя, находит или создаёт анонимного пользователя, создаёт или продолжает активную сессию, сохраняет входящее сообщение, строит LLM-запрос на основе истории, мёржит извлечённые qualification-поля и контакт (None из LLM не затирает собранное), вычисляет на backend недостающие поля, детерминированно выбирает следующее состояние, сохраняет ответ ассистента, апсертит draft-лида и — когда обязательные поля собраны — переводит лид в `ready` и ставит задачу доставки в Redis-очередь.

### Основной flow

```text
HTTP request
  → AgentService
  → Ag2AgentClient.decide()        ← AG2 ConversableAgent здесь
  → AgentDecision (Pydantic)       ← structured output + валидация
  → merge_qualification / contact  ← None не затирает собранное
  → compute_missing_fields         ← backend считает, не LLM
  → state_machine.resolve()        ← переходы состояний кодом, не LLM
  → DialogSessionRepository.update_state()
  → LeadRepository.upsert_draft()
  → (ready) LeadRepository.update(status="ready")
  → QueueClient.enqueue_lead_delivery()   ← async-доставка, после commit
  → AgentMessageResponse
```

### Доставка лида (асинхронная)

```text
Redis queue
  → worker (app/worker/lead_delivery.py)
  → LeadDeliveryService.deliver()
  → CrmClient.deliver_lead()       ← AmoCRM / webhook / fake
  → lead.status = delivered | delivery_failed (+ last_delivery_error)
```

### Read-flow для проверки памяти

```text
GET /sessions/{session_id}
  -> session_router.py
  -> SessionService
  -> DialogSessionRepository
  -> SessionResponse

GET /sessions/{session_id}/messages
  -> session_router.py
  -> SessionService
  -> MessageRepository
  -> list[StoredMessageResponse]
```

---

## API routes

```text
POST /message
GET  /sessions/{session_id}
GET  /sessions/{session_id}/messages
GET  /leads
GET  /leads/{lead_id}
POST /leads/{lead_id}/deliver
```

---

## POST /message

Основной write-route агентного контура.

### Request

```json
{
  "anonymous_id": "demo-user-1",
  "channel": "website",
  "session_id": null,
  "content": "Сколько стоит внедрение?"
}
```

Поля:

| Поле | Тип | Обязательное | Описание |
|---|---|---:|---|
| `anonymous_id` | `string` | Да | Стабильный идентификатор анонимного пользователя |
| `channel` | `website` / `telegram` / `avito` | Нет | Канал входа. По умолчанию `website` |
| `session_id` | `UUID` / `null` | Нет | ID существующей сессии. Если не передан, backend найдёт активную или создаст новую |
| `content` | `string` | Да | Текст сообщения пользователя |

### Response

```json
{
  "user_id": "0c336b9b-6a7e-4494-8af1-e6302b87956f",
  "session_id": "c75f9b38-b169-4901-a3e1-9335d4d7ff6a",
  "user_message_id": "57c7b362-4b4c-4ebf-a6f5-a6c9bfc19f1a",
  "assistant_message_id": "bb9ffb5f-d98c-4cc2-bf7e-c6e5dfde4b63",
  "answer": "Здравствуйте! Чем могу помочь?",
  "state": "FAQ",
  "intent": "pricing",
  "next_step": "FAQ",
  "missing_fields": ["car_model", "budget", "purchase_type", "contact"],
  "lead_id": "9f1c0c2a-3b4d-4e5f-8a9b-1c2d3e4f5a6b"
}
```

`missing_fields` и `lead_id` считает backend. `missing_fields` — какие обязательные поля ещё не собраны; `lead_id` появляется, как только создан draft.

---

## Read-routes

### GET /sessions/{session_id}

Возвращает данные сессии.

```bash
curl http://localhost:8000/sessions/SESSION_ID
```

Пример ответа:

```json
{
  "id": "c75f9b38-b169-4901-a3e1-9335d4d7ff6a",
  "user_id": "0c336b9b-6a7e-4494-8af1-e6302b87956f",
  "state": "GREETING",
  "channel": "website",
  "created_at": "2026-05-18T21:00:00Z",
  "updated_at": "2026-05-18T21:00:00Z"
}
```

### GET /sessions/{session_id}/messages

Возвращает историю сообщений сессии.

```bash
curl http://localhost:8000/sessions/SESSION_ID/messages
```

Пример ответа:

```json
[
  {
    "id": "57c7b362-4b4c-4ebf-a6f5-a6c9bfc19f1a",
    "session_id": "c75f9b38-b169-4901-a3e1-9335d4d7ff6a",
    "role": "user",
    "content": "Сколько стоит внедрение?",
    "created_at": "2026-05-18T21:00:00Z"
  },
  {
    "id": "bb9ffb5f-d98c-4cc2-bf7e-c6e5dfde4b63",
    "session_id": "c75f9b38-b169-4901-a3e1-9335d4d7ff6a",
    "role": "assistant",
    "content": "Здравствуйте! Чем могу помочь?",
    "created_at": "2026-05-18T21:00:01Z"
  }
]
```

---

## Lead routes

### GET /leads

Список лидов, сортировка по `created_at desc`. Опциональный фильтр `?status=`.

```bash
curl http://localhost:8000/leads
curl "http://localhost:8000/leads?status=ready"
```

Возвращает лёгкие элементы списка (`id`, `session_id`, `user_id`, `status`, `summary`, `created_at`).

### GET /leads/{lead_id}

Полная карточка лида: `qualification`, `contact`, `summary`, `status`, `last_delivery_error`.

```bash
curl http://localhost:8000/leads/LEAD_ID
```

Невалидный `lead_id` → `404`.

### POST /leads/{lead_id}/deliver

Ручной debug-endpoint: синхронно доставляет лид в CRM (минуя очередь). Основной flow доставляет лид автоматически через очередь после перехода в `ready`.

```bash
curl -X POST http://localhost:8000/leads/LEAD_ID/deliver
```

- `404` — лид не найден.
- `409` — лид в недопустимом для доставки статусе (например `draft`).
- `200` — вернёт карточку лида со статусом `delivered` или `delivery_failed`.

---

## Идентификация анонимного пользователя

Для незарегистрированного пользователя используется `anonymous_id`.

Клиентская часть должна один раз сгенерировать стабильный идентификатор и отправлять его в каждом запросе. Для сайта его можно хранить в cookie или `localStorage`.

Пользователь считается уникальным по паре:

```text
channel + anonymous_id
```

Пример:

```text
website + demo-user-1
telegram + demo-user-1
```

Это разные пользователи, потому что они пришли из разных каналов.

---

## Состояние диалога

Машина состояний реализована в `app/service/state_machine.py`. Переходы между состояниями детерминированы кодом, не LLM. `LEAD_READY` разрешается только после backend-проверки всех обязательных полей и валидного контакта — даже если LLM прислал `lead_ready=true` раньше.

Значения:

```text
GREETING
FAQ
QUALIFICATION
CONTACT_CAPTURE
LEAD_READY
CLOSED
```

Обязательные qualification-поля вынесены в `app/domain.py` (`car_model` / `budget` / `purchase_type`) — меняются в одном месте.

---

## База данных

История диалогов и лиды хранятся в PostgreSQL.

Основные таблицы:

| Таблица | Назначение |
|---|---|
| `users` | Анонимные пользователи. Уникальность по `channel + anonymous_id` |
| `dialog_sessions` | Сессии диалога пользователя с агентом |
| `messages` | История сообщений `user` / `assistant` |
| `leads` | Карточка лида: `draft → ready → delivered \| delivery_failed`. Ошибка доставки пишется в `last_delivery_error` |

### Удаление записей

Удаление мягкое (soft delete): строки помечаются `deleted_at`, физически не стираются. Все читающие запросы фильтруют `deleted_at IS NULL`. Уникальность `users` по `channel + anonymous_id` — частичная, только среди не-удалённых строк. Внешние ключи стоят на `ON DELETE RESTRICT` — случайный физический каскад невозможен.

В MVP пользовательского удаления нет: это только механизм на уровне БД и репозиториев.

### Упрощённая схема

```text
users 1 -> many dialog_sessions
dialog_sessions 1 -> many messages
users 1 -> many leads
dialog_sessions 1 -> 0..1 leads
```

PlantUML-диаграмма текущей БД находится здесь:

```text
docs/diagrams/DataBase.puml
```

---

## Миграции

Миграции управляются через Alembic.

Применить миграции:

```bash
uv run alembic upgrade head
```

Создать новую миграцию после изменения ORM-моделей:

```bash
uv run alembic revision --autogenerate -m "describe changes"
```

Проверить текущую ревизию:

```bash
uv run alembic current
```

---

## API схемы

Внешний API продукта использует:

```text
app/schemas/agent_schema.py
app/schemas/session_schema.py
app/schemas/lead_schema.py
app/schemas/lead_delivery_schema.py
```

То есть внешний клиент отправляет не `model + messages`, а product-level payload:

```json
{
  "anonymous_id": "demo-user-1",
  "channel": "website",
  "content": "Привет"
}
```

---

## Быстрый старт

### 1. Установка зависимостей

```bash
uv sync
```

### 2. Настройка окружения

```bash
cp .env.example .env
```

Минимальная конфигурация для локальной разработки:

```env
LLM_PROVIDER=stub
DATABASE_URL=postgresql+asyncpg://innova:innova@localhost:5432/innova_ai
```

Для работы с реальным LLM (AG2 через OpenRouter):

```env
LLM_PROVIDER=ag2
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
AG2_MODEL=openai/gpt-oss-120b:free
DATABASE_URL=postgresql+asyncpg://innova:innova@localhost:5432/innova_ai
```

При `LLM_PROVIDER=ag2` без `OPENROUTER_API_KEY` приложение падает на старте с понятной ошибкой (fail-fast). `AG2_MODEL` — ставь модель, к которой реально есть доступ на OpenRouter.

Для доставки лида в CRM (Phase 5):

```env
REDIS_URL=redis://localhost:6379/0
LEAD_DELIVERY_PROVIDER=amocrm
AMOCRM_BASE_URL=https://ваш-поддомен.amocrm.ru
AMOCRM_ACCESS_TOKEN=ваш-долгосрочный-токен
```

`LEAD_DELIVERY_PROVIDER` принимает `disabled | fake | amocrm | webhook`. Токен — только в `.env`, не в git.

### 3. PostgreSQL

Проект ожидает доступную PostgreSQL-базу.

Пример локальной базы:

```text
database: innova_ai
user:     innova
password: innova
host:     localhost
port:     5432
```

Проверить подключение можно так:

```bash
psql "postgresql://innova:innova@localhost:5432/innova_ai"
```

### 4. Применение миграций

```bash
uv run alembic upgrade head
```

### 5. Запуск сервера

```bash
uv run uvicorn main:app --reload
```

---

## Доставка лида в CRM

Доставка асинхронная: `ready`-лид попадает в Redis-очередь, отдельный worker забирает задачу и создаёт сделку в CRM.

### 1. Redis

```bash
docker run -d -p 6379:6379 --name innova_redis redis:7-alpine
```

### 2. Worker

В отдельном терминале (env из `.env`):

```bash
uv run python -m app.worker.lead_delivery
```

### 3. Поведение

- `ready`-лид автоматически ставится в очередь после перехода (внутри `/message`, после commit).
- Worker доставляет лид в CRM: успех → `delivered`, ошибка → `delivery_failed` + `last_delivery_error`.
- Если Redis недоступен, лид остаётся в `ready` (не теряется) и доставляется вручную через `POST /leads/{id}/deliver`.

> Опционально: если в репозитории есть `Makefile` + `Procfile`, всё поднимается одной командой `make dev` (Redis + миграции + сервер + worker через honcho).

---

## Manual AG2 smoke (Phase 6)

Проверка работы на реальном провайдере. Env держать в `.env` (`LLM_PROVIDER=ag2`, `OPENROUTER_API_KEY=...`, `AG2_MODEL=...`).

```bash
uv run uvicorn main:app

# 1) первый контакт
curl -sX POST localhost:8000/message -H 'Content-Type: application/json' \
  -d '{"anonymous_id":"smoke-ag2","channel":"website","content":"Привет, ищу машину"}'

# 2) квалификация
curl -sX POST localhost:8000/message -H 'Content-Type: application/json' \
  -d '{"anonymous_id":"smoke-ag2","channel":"website","content":"Хочу Toyota Camry, до 3 млн, в кредит"}'

# 3) контакт
curl -sX POST localhost:8000/message -H 'Content-Type: application/json' \
  -d '{"anonymous_id":"smoke-ag2","channel":"website","content":"Иван, +79991234567"}'

# 4) лид
curl -s localhost:8000/leads
```

Free-модели иногда отдают невалидный JSON — тогда сработает безопасный fallback (`_parse_reply` → `_FALLBACK_DECISION`), ответ пользователю не ломается, состояние и собранные данные сохраняются. Timeout и исключения провайдера тоже уходят в fallback, а не в 500.

---

## Demo-сценарий

### 1. Первое сообщение

```bash
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -d '{
    "anonymous_id": "demo-user-1",
    "channel": "website",
    "content": "Здравствуйте, хочу узнать стоимость внедрения"
  }'
```

Из ответа нужно скопировать `session_id`.

### 2. Продолжение диалога

```bash
curl -X POST http://localhost:8000/message \
  -H "Content-Type: application/json" \
  -d '{
    "anonymous_id": "demo-user-1",
    "channel": "website",
    "session_id": "SESSION_ID_FROM_FIRST_RESPONSE",
    "content": "А можно подробнее?"
  }'
```

### 3. Проверка сессии

```bash
curl http://localhost:8000/sessions/SESSION_ID_FROM_FIRST_RESPONSE
```

### 4. Проверка истории сообщений

```bash
curl http://localhost:8000/sessions/SESSION_ID_FROM_FIRST_RESPONSE/messages
```

После двух `POST /message` ожидается 4 сообщения:

```text
user
assistant
user
assistant
```

### 5. Просмотр лидов

```bash
curl http://localhost:8000/leads
```

---

## Тесты

Запуск всех тестов:

```bash
uv run pytest
```

Подробный вывод:

```bash
uv run pytest -v
```

Отдельно unit-тесты:

```bash
uv run pytest -m unit
```

Отдельно integration-тесты:

```bash
uv run pytest -m integration
```

Тестовая база по умолчанию:

```text
postgresql+asyncpg://innova:innova@localhost:5432/innova_ai_test
```

Её можно переопределить через переменную окружения:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/db_name uv run pytest
```
Требование: роль тест-БД должна иметь право CREATE EXTENSION

### Создание тестовой базы

```bash
createdb -U innova innova_ai_test
# или через psql:
psql -U innova -c "CREATE DATABASE innova_ai_test;"
```

### Команды по типам тестов

```bash
# Без БД — всегда зелёные:
uv run pytest tests/unit -q

# Integration — нужна test DB:
uv run pytest -m integration -q

# Redis-зависимые:
uv run pytest -m integration_redis -q

# CRM fake adapter:
uv run pytest -m integration_crm_fake -q

# Smoke с реальным LLM:
LLM_PROVIDER=ag2 OPENROUTER_API_KEY=sk-... uv run pytest -m manual_smoke -q
```

### mypy

mypy не является обязательным CI gate в текущей фазе. Запуск:

```bash
uv run mypy app/ --ignore-missing-imports
```

---

## Текущий статус

| Слой | Статус |
|---|---|
| Product-level `POST /message` | Реализовано |
| Анонимный пользователь | Реализовано |
| Сессии диалога | Реализовано |
| История сообщений | Реализовано |
| Read-routes для памяти | Реализовано |
| Lead read API (`GET /leads`) | Реализовано |
| PostgreSQL ORM-модели | Реализовано |
| Alembic-миграции | Реализовано |
| Stub LLM client | Реализовано |
| AG2AgentClient + FakeAg2 | Реализовано |
| AG2 fallback + startup validation | Реализовано |
| Полноценная state machine | Реализовано |
| Lead table (`draft → ready → delivered`) | Реализовано |
| Redis очередь доставки | Реализовано |
| CRM delivery (AmoCRM) | Реализовано |
| RAG / база знаний | Планируется (Phase 7) |
| Web widget | Планируется (Phase 8) |

---

## Архитектурные слои

### Router layer

Принимает HTTP-запросы и делегирует работу сервисам.

```text
app/router/message_router.py
app/router/session_router.py
app/router/lead_router.py
```

### Service layer

Содержит use case логику.

```text
app/service/agent_service.py
app/service/session_service.py
app/service/business_service.py
app/service/state_machine.py
app/service/lead_service.py
app/service/lead_delivery_service.py
```

### Repository layer

Инкапсулирует работу с PostgreSQL.

```text
app/repository/user_repository.py
app/repository/dialog_session_repository.py
app/repository/message_repository.py
app/repository/lead_repository.py
```

### Model layer

SQLAlchemy ORM-модели.

```text
app/models/user_model.py
app/models/dialog_session_model.py
app/models/message_model.py
app/models/lead_model.py
```

### Client layer

Изолирует работу с внешними системами: LLM-провайдер, CRM, очередь.

```text
app/client/ag2_agent_client.py
app/client/crm_client.py
app/client/queue_client.py
app/client/delivery_factory.py
```

### Worker layer

Фоновая обработка очереди доставки.

```text
app/worker/lead_delivery.py
```

---

## Документация

- `docs/MVP_ROADMAP.md` — Scope и план реализации (сейчас это главный ориентир)
- `docs/PRD.md` — продуктовые требования, ICP, use cases, метрики.
- `docs/System_Design.md` — целевая архитектура, state machine, RAG, очередь лидов, multi-tenancy.
- `docs/diagrams/Components.puml` — компонентная диаграмма.
- `docs/diagrams/Sequence.puml` — happy path от сообщения до лида.
- `docs/diagrams/DataBase.puml` — текущая схема PostgreSQL.