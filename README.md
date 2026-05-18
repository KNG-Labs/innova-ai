# Innova AI

AI-ассистент для лидогенерации и клиентской коммуникации в digital-каналах. Проект развивается из простого LLM endpoint в backend агентного диалога с памятью, сессиями, историей сообщений и будущим lead-flow.

---

## Что это

Innova AI — backend-слой conversational AI продукта. Сервис принимает сообщение пользователя, определяет намерение, создаёт или продолжает диалоговую сессию, сохраняет историю сообщений в PostgreSQL и возвращает ответ агента.

Сейчас проект реализует базовый агентный контур:

- анонимный пользователь;
- диалоговая сессия;
- история сообщений;
- первичное определение intent;
- генерация ответа через LLM-клиент или stub-клиент;
- read-routes для проверки памяти агента.

Целевая продуктовая логика шире: бот должен отвечать на вопросы, квалифицировать потребность, собирать контакты и передавать структурированный лид в CRM, Telegram или webhook.

---

## Стек

- Python 3.13
- FastAPI
- Pydantic
- SQLAlchemy asyncio
- PostgreSQL
- Alembic
- httpx
- OpenAI SDK / OpenRouter
- pytest / pytest-asyncio
- uv

---

## Структура репозитория

```text
INNOVA_AI/
├── .env.example
├── .gitignore
├── .python-version
├── alembic.ini
├── main.py
├── pyproject.toml
├── uv.lock
├── README.md
├── app/
│   ├── __init__.py
│   ├── di.py
│   ├── client/
│   │   ├── __init__.py
│   │   ├── llm_client.py
│   │   └── openrouter_client.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── session.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user_model.py
│   │   ├── dialog_session_model.py
│   │   ├── message_model.py
│   │   └── lead_model.py
│   ├── repository/
│   │   ├── __init__.py
│   │   ├── user_repository.py
│   │   ├── dialog_session_repository.py
│   │   ├── message_repository.py
│   │   └── lead_repository.py
│   ├── router/
│   │   ├── __init__.py
│   │   ├── message_router.py
│   │   └── session_router.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── agent_schema.py
│   │   ├── session_schema.py
│   │   └── openai_schema.py
│   └── service/
│       ├── __init__.py
│       ├── agent_service.py
│       ├── session_service.py
│       ├── business_service.py
│       ├── message_service.py
│       └── intent_detector/
│           ├── __init__.py
│           ├── base_intent_detector.py
│           ├── keyword_intent_detector.py
│           └── llm_intent_detector.py
├── docs/
│   ├── PRD.md
│   ├── System_Design.md
│   └── diagrams/
│       ├── Components.puml
│       ├── DataBase.puml
│       └── Sequence.puml
├── migrations/
│   ├── env.py
│   ├── README
│   ├── script.py.mako
│   └── versions/
│       └── 8cd1e0d95b7a_create_tables.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── integration/
    │   ├── __init__.py
    │   ├── test_agent_message.py
    │   └── test_sessions_session_id.py
    └── unit/
        ├── __init__.py
        ├── test_message_service.py
        ├── test_openrouter_client.py
        └── test_schemas_openai.py
```

---

## Текущая реализация

Сейчас реализован минимальный agent-flow с памятью в PostgreSQL.

`POST /message` принимает одно сообщение пользователя, находит или создаёт анонимного пользователя, создаёт или продолжает активную сессию диалога, сохраняет входящее сообщение, строит LLM-запрос на основе истории сообщений, сохраняет ответ ассистента и возвращает agent response.

### Основной flow

```text
HTTP request
  -> message_router.py
  -> AgentService
  -> UserRepository
  -> DialogSessionRepository
  -> MessageRepository
  -> LLMClient
  -> PostgreSQL
  -> AgentMessageResponse
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
GET /sessions/{session_id}
GET /sessions/{session_id}/messages
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
  "state": "GREETING",
  "intent": "pricing",
  "next_step": "send_pricing_summary"
}
```

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

В `dialog_sessions` уже есть поле `state`. Пока это заготовка под будущую state machine.

Возможные значения:

```text
GREETING
FAQ
QUALIFICATION
CONTACT_CAPTURE
LEAD_READY
CLOSED
```

На текущем этапе полноценная машина состояний ещё не реализована, но модель БД и API уже подготовлены под неё.

---

## База данных

История диалогов хранится в PostgreSQL.

Основные таблицы:

| Таблица | Назначение |
|---|---|
| `users` | Анонимные пользователи. Уникальность по `channel + anonymous_id` |
| `dialog_sessions` | Сессии диалога пользователя с агентом |
| `messages` | История сообщений `user` / `assistant` |
| `leads` | Черновая заготовка будущей карточки лида |

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

## OpenAI-compatible схемы

Публичный API продукта больше не является OpenAI-compatible endpoint.

Файл:

```text
app/schemas/openai_schema.py
```

используется как внутренний контракт для общения с LLM-провайдером через `LLMClient`.

Внешний API продукта использует:

```text
app/schemas/agent_schema.py
app/schemas/session_schema.py
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

Для OpenRouter:

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
DATABASE_URL=postgresql+asyncpg://innova:innova@localhost:5432/innova_ai
```

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

Интеграционные тесты проверяют:

- создание анонимного пользователя;
- создание сессии;
- продолжение существующей сессии;
- продолжение активной сессии без явного `session_id`;
- сохранение истории сообщений;
- чтение сессии через `GET /sessions/{session_id}`;
- чтение сообщений через `GET /sessions/{session_id}/messages`;
- изоляцию разных anonymous users;
- различие пользователей с одинаковым `anonymous_id` в разных каналах;
- валидацию некорректного `anonymous_id`;
- валидацию невалидного payload.

Тестовая база по умолчанию:

```text
postgresql+asyncpg://innova:innova@localhost:5432/innova_ai_test
```

Её можно переопределить через переменную окружения:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/db_name uv run pytest
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
| PostgreSQL ORM-модели | Реализовано |
| Alembic-миграции | Реализовано |
| Keyword intent detection | Реализовано |
| OpenRouter client | Реализовано |
| Stub LLM client | Реализовано |
| Lead table | Заготовка |
| Полноценная state machine | Планируется |
| RAG / база знаний | Планируется |
| CRM / Telegram / webhook delivery | Планируется |
| Очередь фоновых задач | Планируется |
| Multi-tenancy | Планируется |

---

## Архитектурные слои

### Router layer

Принимает HTTP-запросы и делегирует работу сервисам.

Файлы:

```text
app/router/message_router.py
app/router/session_router.py
```

### Service layer

Содержит use case логику.

Файлы:

```text
app/service/agent_service.py
app/service/session_service.py
app/service/business_service.py
```

### Repository layer

Инкапсулирует работу с PostgreSQL.

Файлы:

```text
app/repository/user_repository.py
app/repository/dialog_session_repository.py
app/repository/message_repository.py
app/repository/lead_repository.py
```

### Model layer

SQLAlchemy ORM-модели.

Файлы:

```text
app/models/user_model.py
app/models/dialog_session_model.py
app/models/message_model.py
app/models/lead_model.py
```

### LLM client layer

Изолирует работу с LLM-провайдерами.

Файлы:

```text
app/client/llm_client.py
app/client/openrouter_client.py
```

---

## Документация

- `docs/PRD.md` — продуктовые требования, ICP, use cases, метрики.
- `docs/System_Design.md` — целевая архитектура, state machine, RAG, очередь лидов, multi-tenancy.
- `docs/diagrams/Components.puml` — компонентная диаграмма.
- `docs/diagrams/Sequence.puml` — happy path от сообщения до лида.
- `docs/diagrams/DataBase.puml` — текущая схема PostgreSQL.

---

## Что дальше

Ближайшие логичные шаги:

1. Реализовать полноценную state machine.
2. Начать lead capture flow.
3. Использовать таблицу `leads` в реальном сценарии.
4. Добавить RAG-слой и базу знаний.
5. Добавить очередь доставки лида в CRM / Telegram / webhook.
6. Подготовить multi-tenancy через `tenant_id`.
