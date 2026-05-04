# Innova AI

AI-ассистент для лидогенерации и клиентской коммуникации в digital-каналах. Автоматизирует первый контакт с клиентом, квалифицирует запрос, собирает контактные данные и передаёт структурированный лид в CRM или мессенджеры.

---

## Что это

Conversational AI слой между входящим трафиком и отделом продаж. Бот самостоятельно вступает в диалог, отвечает на вопросы по базе знаний клиента, квалифицирует потребность, собирает контакты и маршрутизирует лид дальше — в CRM, Telegram или через webhook.

Работает на сайте, в Avito и мессенджерных сценариях.

---

## Структура репозитория

```
INNOVA_AI/
├── .env.example              # Шаблон конфигурации
├── .gitignore
├── .python-version
├── pyproject.toml            # Зависимости (uv)
├── uv.lock
├── README.md
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app + lifespan
│   ├── di.py                # Dependency Injection контейнер
│   ├── client/              # Gateway слой (LLM провайдеры)
│   │   ├── __init__.py
│   │   ├── llm_client.py    # Protocol для LLM клиентов
│   │   └── openrouter_client.py  # OpenRouter реализация
│   ├── router/              # API endpoints
│   │   ├── __init__.py
│   │   └── message.py       # POST /v1/chat/completions
│   ├── service/             # Бизнес-логика
│   │   ├── __init__.py
│   │   └── message.py       # Оркестрация use case
│   └── schemas/             # Pydantic модели
│       ├── __init__.py
│       ├── message.py       # Схемы для будущих endpoints
│       └── openai.py        # OpenAI-совместимые схемы
├── docs/
│   ├── PRD.md
│   ├── System_Design.md
│   └── diagrams/
│       ├── Components.puml
│       └── Sequence.puml
└── tests/
    ├── __init__.py
    ├── integration/
    │   ├── __init__.py
    │   └── test_api.py
    └── unit/
        └── __init__.py
```

---

## Текущая реализация

На данный момент реализован **базовый OpenAI-совместимый endpoint** для интеграции с LLM провайдерами:

### Endpoint
```
POST /v1/chat/completions
```

### Архитектура слоёв

```
┌─────────────┐
│   Router    │  app/router/message.py
│ (endpoint)  │  • Принимает ChatCompletionRequest
└──────┬──────┘  • Возвращает ChatCompletionResponse
       │
       ▼
┌─────────────┐
│   Service   │  app/service/message.py
│  (use case) │  • Оркестрирует вызов LLM
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Client    │  app/client/openrouter_client.py
│  (gateway)  │  • Интеграция с OpenRouter API
└─────────────┘  • Обработка ошибок HTTP/timeout
       │         • Маппинг provider-specific полей
       ▼
  OpenRouter API
```

### Dependency Injection

**Файл:** `app/di.py`

- Создаёт `httpx.AsyncClient` при старте приложения
- Выбирает LLM провайдер на основе `LLM_PROVIDER` (stub | openrouter)
- Валидирует конфигурацию (проверяет `OPENROUTER_API_KEY`)
- Инжектирует зависимости в сервисы через `app.state`

### Схемы

**Файл:** `app/schemas/openai.py`

- `ChatCompletionRequest` — входной запрос (OpenAI-compatible)
- `ChatCompletionResponse` — ответ (OpenAI-compatible)
- `ChatMessage`, `ChatChoice`, `ChatUsage` — вспомогательные модели

**Особенность:** Поле `reasoning` в request маппится в `extra_body.reasoning` для провайдеров, поддерживающих reasoning chains.

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

Отредактируйте `.env`:

```bash
# Для разработки — используйте заглушку
LLM_PROVIDER=stub

# Для реального LLM — настройте OpenRouter
# LLM_PROVIDER=openrouter
# OPENROUTER_API_KEY=sk-or-v1-your-key-here
# OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

### 3. Запуск сервера

```bash
uv run uvicorn app.main:app --reload
```

### 4. Тестовый запрос

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemma-4-26b-a4b-it:free",
    "messages": [
      {"role": "user", "content": "Привет!"}
    ]
  }'
```

---

## Разработка

### Проверка кода

```bash
# Запустить все проверки
uv run ruff check .
uv run mypy app
uv run pytest

# Только unit-тесты
uv run pytest -m unit

# Только integration-тесты
uv run pytest -m integration
```

### Структура тестов

- `tests/unit/` — быстрые тесты без внешних зависимостей (моки, валидация схем)
- `tests/integration/` — тесты с реальным FastAPI TestClient

---

## Целевая архитектура

Система состоит из пяти слоёв:

|Слой|Назначение|Статус|
|---|---|---|
|**Каналы входа**|Сайт, Avito, Telegram — принимают сообщение пользователя|🔜 Планируется|
|**Движок диалога**|Машина состояний: GREETING → FAQ → QUALIFICATION → CONTACT_CAPTURE|🔜 Планируется|
|**AI-слой**|Intent detection, RAG по базе знаний клиента, генерация ответа|✅ Базовый LLM endpoint|
|**Очередь**|Асинхронная доставка лида во внешние системы|🔜 Планируется|
|**Внешние системы**|CRM (Bitrix24, AmoCRM, HubSpot), Telegram, webhook|🔜 Планируется|

Подробнее: `docs/System_Design.md`

---

## Документация

- `docs/PRD.md` — продуктовые требования, ICP, use cases, метрики
- `docs/System_Design.md` — архитектура, схема БД, очередь лидов, multi-tenancy
- `docs/diagrams/` — PlantUML диаграммы компонентов и последовательностей