# Innova AI

AI-ассистент для лидогенерации и клиентской коммуникации в digital-каналах. Автоматизирует первый контакт с клиентом, квалифицирует запрос, собирает контактные данные и передаёт структурированный лид в CRM или мессенджеры.

---

## Что это

Conversational AI слой между входящим трафиком и отделом продаж. Бот самостоятельно вступает в диалог, отвечает на вопросы по базе знаний клиента, квалифицирует потребность, собирает контакты и маршрутизирует лид дальше — в CRM, Telegram или через webhook.

Работает на сайте, в Avito и мессенджерных сценариях.

---

## Структура репозитория

```text
INNOVA_AI/
├── .env.example              # Шаблон конфигурации
├── pyproject.toml            # Зависимости и настройки dev-инструментов
├── uv.lock
├── README.md
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app + lifespan
│   ├── di.py                # Dependency Injection и app.state
│   ├── client/              # Gateway слой для LLM-провайдеров
│   │   ├── __init__.py
│   │   ├── llm_client.py    # Protocol, StubLLMClient, LLMProviderError
│   │   └── openrouter_client.py  # OpenRouter через официальный OpenAI SDK
│   ├── router/
│   │   ├── __init__.py
│   │   └── message.py       # POST /message-to-model
│   ├── service/
│   │   ├── __init__.py
│   │   ├── business.py      # Нормализация, intent detection, next_step
│   │   └── message.py       # Оркестрация use case и fallback
│   └── schemas/
│       ├── __init__.py
│       └── message.py       # OpenAI-compatible request/response схемы
├── docs/
│   ├── PRD.md
│   ├── System_Design.md
│   └── diagrams/
│       ├── Components.puml
│       └── Sequence.puml
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── integration/
    │   ├── __init__.py
    │   └── test_chat_completions.py
    └── unit/
        ├── __init__.py
        ├── test_message_service.py
        ├── test_openrouter_client.py
        └── test_schemas_openai.py
```

---

## Текущая реализация

Реализован OpenAI-compatible endpoint с минимальной прикладной бизнес-логикой перед вызовом LLM-провайдера.

### Endpoint

```text
POST /message-to-model
```

Endpoint принимает `ChatCompletionRequest` с историей сообщений в формате `messages` и возвращает `ChatCompletionResponse`.

### Архитектура слоёв

```text
HTTP request
  -> router/message.py
  -> MessageService
  -> DialogBusinessProcessor
  -> LLMClient
  -> OpenRouter API или StubLLMClient
  -> ChatCompletionResponse
```

Назначение слоёв:

- `router` принимает HTTP-запрос, валидирует payload через Pydantic и получает сервис через `Depends`.
- `MessageService` оркестрирует use case: запускает бизнес-обработку, вызывает LLM-клиент и возвращает fallback при ошибке провайдера.
- `DialogBusinessProcessor` нормализует последнее `user`-сообщение, определяет intent и формирует `next_step`.
- `LLMClient` задаёт общий интерфейс для LLM-провайдеров.
- `OpenRouterClient` изолирует работу с OpenRouter через официальный OpenAI SDK и приводит ошибки SDK к внутреннему `LLMProviderError`.

### Бизнес-сценарий

Перед отправкой запроса в LLM сервис выполняет обработку последнего пользовательского сообщения:

- нормализует пробелы и проверяет, что сообщение не пустое;
- определяет первичный `intent`: `pricing`, `lead_request`, `support` или `general`;
- формирует `next_step` для следующего шага диалога;
- добавляет результат обработки в extra-поле ответа `innova_ai`.

Пример входа:

```json
{
  "model": "test-model",
  "messages": [
    {"role": "user", "content": "  Сколько   стоит внедрение?  "}
  ]
}
```

Фрагмент ответа:

```json
{
  "innova_ai": {
    "normalized_message": "Сколько стоит внедрение?",
    "intent": "pricing",
    "next_step": "send_pricing_summary"
  }
}
```

Если LLM-провайдер возвращает timeout, rate limit или server error, сервис возвращает безопасный fallback-ответ и добавляет `innova_ai_error` с технической информацией для backend-слоя.

### Dependency Injection

**Файл:** `app/di.py`

- Создаёт `httpx.AsyncClient` при старте приложения.
- Выбирает LLM-провайдер на основе `LLM_PROVIDER`: `stub` или `openrouter`.
- Валидирует конфигурацию для реального провайдера.
- Создаёт `MessageNormalizer`, `IntentDetector`, `DialogBusinessProcessor`.
- Создаёт `MessageService` и кладёт зависимости в `app.state`.
- Отдаёт сервис в router через `Depends(get_message_service)`.

### Схемы

**Файл:** `app/schemas/message.py`

- `ChatCompletionRequest` — входной OpenAI-compatible запрос.
- `UserMessage`, `AssistantMessage`, `ChatMessage` — модели истории сообщений.
- `ChatCompletionResponse`, `ChatChoice`, `ChatUsage` — типы ответа из OpenAI SDK.

Особенность: поле `reasoning` в request маппится в `extra_body.reasoning` для провайдеров, поддерживающих reasoning chains.

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

Для разработки можно использовать заглушку:

```bash
LLM_PROVIDER=stub
```

Для реального LLM-провайдера:

```bash
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

### 3. Запуск сервера

```bash
uv run uvicorn app.main:app --reload
```

### 4. Тестовый запрос

```bash
curl -X POST http://localhost:8000/message-to-model \
  -H "Content-Type: application/json" \
  -d '{
    "model": "google/gemma-4-26b-a4b-it:free",
    "messages": [
      {"role": "user", "content": "  Сколько   стоит внедрение?  "}
    ]
  }'
```

При `LLM_PROVIDER=stub` ответ будет сформирован без обращения к внешнему API, но бизнес-метаданные `innova_ai` всё равно будут добавлены.

---

## Разработка

### Проверка кода

```bash
uv run ruff check .
uv run mypy app
uv run pytest
```

Отдельные группы тестов:

```bash
uv run pytest -m unit
uv run pytest -m integration
```

### Структура тестов

- `tests/unit/` — быстрые тесты без внешних зависимостей: сервис, клиент провайдера, схемы.
- `tests/integration/` — тесты реального FastAPI endpoint через `httpx.ASGITransport`.
- `tests/conftest.py` — общая fixture `client`, которая запускает приложение с `LLM_PROVIDER=stub`.

В тестах используются несколько способов подмены зависимостей:

- `monkeypatch.setenv("LLM_PROVIDER", "stub")` подменяет реальный LLM-провайдер на `StubLLMClient`.
- `AsyncMock` подменяет LLM-клиент в unit-тестах сервиса.
- `app.dependency_overrides[get_message_service]` показывает подмену FastAPI dependency через `Depends`.

---

## Целевая архитектура

Система состоит из пяти слоёв:

|Слой|Назначение|Статус|
|---|---|---|
|**Каналы входа**|Сайт, Avito, Telegram — принимают сообщение пользователя|Планируется|
|**Движок диалога**|Машина состояний: GREETING → FAQ → QUALIFICATION → CONTACT_CAPTURE|Планируется|
|**AI-слой**|Intent detection, RAG по базе знаний клиента, генерация ответа|Базовый LLM endpoint + первичный intent detection|
|**Очередь**|Асинхронная доставка лида во внешние системы|Планируется|
|**Внешние системы**|CRM, Telegram, webhook|Планируется|

Подробнее: `docs/System_Design.md`

---

## Документация

- `docs/PRD.md` — продуктовые требования, ICP, use cases, метрики.
- `docs/System_Design.md` — архитектура, схема БД, очередь лидов, multi-tenancy.
- `docs/diagrams/` — PlantUML диаграммы компонентов и последовательностей.
