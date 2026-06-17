# Innova AI — Roadmap быстрого MVP

Дата: 2026-06-17

## Цель MVP

Быстрый MVP должен доказать одну бизнес-гипотезу:

> Пользователь с сайта может написать в чат, получить полезный ответ, пройти короткую квалификацию, оставить контакт, а менеджер получает структурированный лид с историей и summary.

MVP не должен доказывать всю платформу из PRD. Его задача — закрыть один полный вертикальный сценарий от входящего сообщения до переданного лида, но уже в форме пилотной версии, близкой к реальному клиентскому внедрению: с RAG по базе знаний, веб-виджетом, Redis-backed очередью и доставкой лида в 1-2 CRM.

## MVP в одном предложении

Одноклиентский пилотный сервис с веб-виджетом, `POST /message`, AG2/LLM-orchestrator, RAG по базе знаний клиента, детерминированной state machine, хранением истории и lead в PostgreSQL, Redis-backed очередью доставки, простым просмотром лидов/диалогов и доставкой готового лида в AmoCRM и/или Битрикс24.

## Текущая точка старта

На ветке `AG2integration` уже есть:

- FastAPI backend.
- `POST /message`.
- `users`, `dialog_sessions`, `messages`, `leads`.
- SQLAlchemy async + PostgreSQL.
- Alembic.
- `AgentService`.
- `Ag2AgentClient`.
- `FakeAg2AgentClient` для тестов.
- базовая state machine.
- сохранение истории сообщений.
- draft lead через `LeadRepository.upsert_draft`.
- read routes для сессии и сообщений.
- unit-тесты для AG2 parser/fallback/state machine.
- integration-тесты для `/message`, сессий и изоляции anonymous users.

Критичные незакрытые места:

- state machine не доказывает готовность лида по всем обязательным полям;
- нет полноценного end-to-end теста `first message -> qualification -> contact -> LEAD_READY -> lead saved`;
- lead нельзя удобно прочитать через API;
- нет доставки лида менеджеру или в CRM;
- нет Redis-backed очереди доставки;
- нет RAG/knowledge retrieval;
- нет веб-виджета;
- README/env частично расходятся с кодом;
- полный `pytest` зависит от локальной PostgreSQL-конфигурации;
- quality gates не зелёные: `ruff` и `mypy` сейчас не проходят;
- нет ясного smoke-сценария с реальным `LLM_PROVIDER=ag2`.

## Главный принцип скоупа

MVP строится не как "маленькая версия всей платформы", а как "один законченный lead conversion loop" с минимальной production-like обвязкой вокруг него: сайт-виджет, RAG, очередь и CRM-доставка. Это расширенный MVP, поэтому его нельзя оценивать как 2-3 дня backend-доработок.

### Обязательно для MVP

- Один канал: website/API.
- Один tenant/client, можно без полноценной multi-tenancy.
- Минимальный веб-виджет, который можно встроить на тестовую HTML-страницу.
- Один endpoint для диалога: `POST /message`.
- Хранение anonymous user, session, messages, lead.
- Детерминированная state machine.
- LLM/AG2 только как помощник для ответа, извлечения данных и summary.
- RAG по заранее загруженной базе знаний клиента.
- Код, а не LLM, решает, готов ли лид.
- Минимальная квалификация: `service`, `deadline`, `budget`, `contact`, желательно `name`.
- Список лидов и просмотр конкретного лида через API.
- Redis для очереди задач и, при необходимости, короткоживущего runtime state.
- Очередь задач для асинхронной доставки лида.
- Доставка лида в 1-2 CRM: AmoCRM и/или Битрикс24.
- Fallback delivery в webhook или Telegram допустим только как debug/backup, не как основной MVP-result.
- Тесты, которые доказывают полный flow без реального LLM key.
- Один ручной smoke-run с реальным LLM provider.
- README с командами запуска и демо-сценарием.

### Необязательно для MVP

- Avito.
- автоматический сканер сайта.
- личный кабинет с UI.
- multi-tenancy.
- тарифы и лимиты.
- полноценный retry delivery engine с backoff и dead-letter queue.
- аналитический dashboard.
- auth/roles для кабинета.
- billing.
- web widget как production-ready npm/package/embed с кастомизацией внешнего вида.
- A/B тесты промптов.
- booking через Calendar/YClients.
- lead scoring.
- deduplication.
- SLA triggers.

### Можно полностью урезать из первой версии

- `Enterprise` контур.
- несколько LLM-провайдеров.
- сложную CRM-модель за пределами базового создания сделки/лида.
- кастомные поля для разных клиентов.
- автоматический crawler и сложный knowledge ingestion.
- page context beyond explicit widget payload.
- feed/catalog ingestion.
- advanced analytics.
- operator handoff.
- review queue.

## MVP Scope

### Пользовательский happy path

1. Пользователь отправляет первое сообщение.
2. Веб-виджет передаёт сообщение, anonymous id, channel и page context в backend.
3. Backend создаёт anonymous user и active session.
4. Backend ищет релевантные knowledge chunks через RAG.
5. AG2/LLM получает историю, состояние, qualification data и retrieved context.
6. AG2/LLM возвращает structured decision.
7. Backend сохраняет user/assistant messages.
8. Backend обновляет `qualification_data`.
9. Backend выбирает следующее состояние через deterministic state machine.
10. Если данных не хватает, бот задаёт следующий уточняющий вопрос.
11. Когда собраны `service`, `deadline`, `budget`, бот просит контакт.
12. Когда contact валиден, backend формирует lead draft/final lead.
13. Backend генерирует или принимает summary.
14. Backend сохраняет lead.
15. Backend кладёт задачу доставки в Redis queue.
16. Worker доставляет lead в AmoCRM/Битрикс24.
17. Backend переводит lead в `delivered` или `delivery_failed`.
18. Mentor/client может открыть API и увидеть lead + message history + delivery status.

### Минимальные состояния

```text
GREETING
FAQ
QUALIFICATION
CONTACT_CAPTURE
LEAD_READY
CLOSED
```

### Минимальная модель lead

```json
{
  "id": "uuid",
  "user_id": "uuid",
  "session_id": "uuid",
  "status": "draft|ready|delivered|delivery_failed",
  "contact": {
    "name": "Иван",
    "phone": "+79991234567",
    "email": null,
    "telegram": null
  },
  "qualification": {
    "service": "внедрение AI-ассистента",
    "deadline": "в течение месяца",
    "budget": "до 300000",
    "source_channel": "website"
  },
  "summary": "Клиент хочет внедрить AI-ассистента на сайт...",
  "created_at": "timestamp",
  "updated_at": "timestamp"
}
```

### Минимальные API endpoints

```text
POST /message
GET /sessions/{session_id}
GET /sessions/{session_id}/messages
GET /leads
GET /leads/{lead_id}
POST /leads/{lead_id}/deliver
POST /knowledge/documents
GET /knowledge/documents
POST /knowledge/reindex
GET /delivery/jobs/{job_id}
```

`POST /leads/{lead_id}/deliver` остаётся ручным debug endpoint-ом. Основной MVP-flow должен автоматически ставить задачу доставки после перехода lead в `ready`.

## Roadmap

## Phase 0 — Зафиксировать MVP baseline

Цель: убрать неопределённость и сделать MVP проверяемым.

### Задачи

- Зафиксировать этот roadmap как главный scope-документ для MVP.
- В README добавить ссылку на `docs/MVP_ROADMAP.md`.
- Обновить README так, чтобы он не обещал функционал, который ещё не работает.
- Исправить env-документацию: поддерживаемые значения `LLM_PROVIDER=stub|ag2`.
- Добавить env-документацию для Redis, RAG и CRM:
  - `REDIS_URL`;
  - `VECTOR_STORE=pgvector|qdrant`;
  - `AMOCRM_BASE_URL`;
  - `AMOCRM_ACCESS_TOKEN`;
  - `BITRIX24_WEBHOOK_URL`.
- Зафиксировать одну команду для unit tests.
- Зафиксировать одну команду для integration tests.
- Зафиксировать требования к локальной тестовой PostgreSQL.
- Зафиксировать, какая CRM обязательна первой, а какая допускается как second adapter.

### Acceptance criteria

- Новый разработчик понимает, что такое MVP и что не входит.
- README не противоречит `app/di.py`.
- В документации есть один официальный demo-flow.
- Нет claims вроде "полная state machine не реализована", если файл state machine уже есть.
- Документация явно говорит, что MVP включает RAG, Redis queue, web widget и минимум одну CRM-интеграцию.

### Проверочные вопросы

- Что именно доказывает MVP?
- Почему Avito и multi-tenancy не входят в первый релиз, а RAG/CRM/Redis/widget входят?
- Какой один сценарий должен работать без ручной магии?
- Какая команда доказывает, что текущий backend не сломан?

## Phase 1 — Стабилизировать quality gates

Цель: сделать ветку воспроизводимо проверяемой.

### Задачи

- Починить `ruff check .`.
- Починить или осознанно сузить `mypy`.
- Разделить обязательные проверки на:
  - `unit`: всегда запускаются локально и в CI;
  - `integration`: требуют PostgreSQL;
  - `integration-redis`: требуют Redis;
  - `integration-crm-fake`: используют fake CRM adapter;
  - `manual-smoke`: требует real LLM key.
- Добавить `TEST_DATABASE_URL` в README.
- Добавить короткий script/section для создания `innova_ai_test`.
- Убрать из активного кода неиспользуемые legacy helpers, если они больше не вызываются.
- Проверить, что `pytest tests/unit -q` и `ruff check .` проходят без БД.
- Добавить fake/stub adapters для Redis queue, vector search и CRM delivery, чтобы core tests не зависели от внешних сервисов.

### Acceptance criteria

- `uv run pytest tests/unit -q` зелёный.
- `uv run ruff check .` зелёный.
- `uv run pytest -m integration -q` зелёный при доступной test DB.
- Redis-dependent tests запускаются отдельной командой и документированы.
- CRM delivery tests проходят на fake adapter без реальных токенов.
- README объясняет, как поднять test DB.
- Если `mypy` не делается обязательным gate, это явно написано.

### Что можно урезать

- Не обязательно чинить весь старый OpenAI-compatible слой до идеала, если он не участвует в MVP.
- Можно удалить или оставить legacy OpenRouter client как out-of-scope, но нельзя держать его в README как основной путь.
- Не нужно подключать реальные CRM sandbox credentials в CI.

### Проверочные вопросы

- Какие проверки обязательны перед merge?
- Почему integration tests требуют отдельной БД?
- Что должно проходить без внешних сервисов?
- Какие ошибки `mypy` относятся к текущему AG2 flow, а какие к legacy-коду?
- Какие тесты требуют Redis, а какие должны работать без Redis?

## Phase 2 — Довести state machine до продуктового уровня MVP

Цель: код, а не LLM, контролирует переходы и готовность лида.

### Задачи

- Сделать единую функцию `merge_qualification_data(existing, extracted)`.
- Сделать единую функцию `is_lead_ready(qualification_data, contact)`.
- Проверять все обязательные поля: `service`, `deadline`, `budget`, `contact`.
- Решение `LEAD_READY` принимать только после проверки merged data.
- Добавить контактную валидацию:
  - телефон;
  - email;
  - telegram username;
  - fallback для свободного контакта, если строгая валидация пока мешает.
- Добавить попытки contact capture:
  - first ask;
  - second ask;
  - после отказа или двух неудач переводить в `CLOSED` или оставлять draft.
- Сохранить `missing_fields` как вычисляемое backend-поле, а не слепо доверять LLM.
- Вынести правила переходов в читаемый модуль.

### Acceptance criteria

- Нельзя попасть в `LEAD_READY`, если нет `service`.
- Нельзя попасть в `LEAD_READY`, если нет `deadline`.
- Нельзя попасть в `LEAD_READY`, если нет `budget`.
- Нельзя попасть в `LEAD_READY`, если нет валидного контакта.
- Если LLM прислал `lead_ready=true`, но данные неполные, backend остаётся в `QUALIFICATION` или `CONTACT_CAPTURE`.
- Тесты явно покрывают ложный `lead_ready=true`.

### Что можно урезать

- Не делать сложный lead scoring.
- Не делать кастомный список qualification fields в UI.
- Не делать разные схемы для разных tenants.
- Не делать спам-классификатор, достаточно `CLOSED` вручную/простым правилом.

### Проверочные вопросы

- Какие переходы контролирует код?
- Какие поля обязательны для lead readiness?
- Что будет, если LLM ошибся и сказал `LEAD_READY` слишком рано?
- Почему `missing_fields` лучше считать на backend?
- Где тест, который ломает неправильный переход?

## Phase 3 — Закрыть полный `/message` lead flow

Цель: один endpoint реально ведёт пользователя до лида.

### Задачи

- Уточнить контракт `AgentDecision`.
- Разделить поля:
  - `answer`;
  - `intent`;
  - `suggested_state`;
  - `extracted_qualification`;
  - `extracted_contact`;
  - `summary`;
  - `confidence` или `reason`, если нужно для debug.
- В `AgentService` изменить порядок:
  - загрузить session + lead draft;
  - загрузить recent history;
  - сохранить user message;
  - вызвать AG2/fake client;
  - распарсить extracted fields;
  - смерджить data;
  - вычислить backend missing fields;
  - принять backend state transition;
  - сохранить assistant message;
  - upsert lead draft;
  - если ready, перевести lead в `ready`;
  - commit.
- Добавить `status` lead:
  - `draft`;
  - `ready`;
  - `delivered`;
  - `delivery_failed`.
- Добавить в response хотя бы минимальные debug-friendly поля для MVP:
  - `state`;
  - `intent`;
  - `missing_fields`;
  - `lead_id`, если draft уже создан.
- Не отдавать внутренние LLM/raw fields наружу.

### Acceptance criteria

- Первый запрос создаёт user/session/messages.
- Второй/третий запрос обновляет same session.
- Qualification data накапливается, а не перезаписывается `None`.
- Lead draft появляется после первого meaningful signal или сразу после первого message, если так проще.
- Lead становится `ready` только после обязательных полей.
- Response позволяет понять текущее состояние диалога без чтения БД руками.

### Что можно урезать

- Не делать отдельный frontend.
- Не делать streaming.
- Не делать multi-agent.
- Не делать tools/function calling, если structured JSON через AG2 стабильно хватает.

### Проверочные вопросы

- В каком порядке выполняется `handle_message`?
- Почему user message сохраняется до вызова агента?
- Что случится, если AG2 упадёт после сохранения user message?
- Как ты предотвращаешь потерю уже собранных полей?
- Где гарантия, что `None` не затирает старое значение?

## Phase 4 — Добавить lead read API

Цель: MVP можно проверять без прямого доступа к БД.

### Задачи

- Создать `LeadResponse`.
- Создать `LeadListItem`.
- Добавить `LeadService`.
- Добавить `lead_router`.
- Реализовать `GET /leads`.
- Реализовать `GET /leads/{lead_id}`.
- Добавить фильтр по `status`, если это быстро.
- Добавить сортировку по `created_at desc`.
- Добавить в response:
  - lead fields;
  - session_id;
  - user_id;
  - status;
  - qualification;
  - contact;
  - summary.

### Acceptance criteria

- После прохождения диалога можно открыть `GET /leads` и увидеть новый lead.
- `GET /leads/{lead_id}` показывает qualification и contact.
- Невалидный lead id возвращает `404`.
- API не требует UI.

### Что можно урезать

- Не делать pagination, если лидов мало.
- Не делать auth, если MVP запускается локально/в закрытом demo.
- Не делать редактирование lead.
- Не делать удаление lead.

### Проверочные вопросы

- Почему MVP нужен read API для lead?
- Чем lead отличается от session?
- Почему `messages` не заменяют `lead`?
- Как менеджер поймёт, что лид готов?

## Phase 5 — Redis queue и доставка лида в CRM

Цель: MVP отдаёт результат за пределы backend через асинхронную очередь и создаёт лид/сделку в CRM.

### Рекомендуемый вариант для расширенного MVP

Начать с одного основного CRM adapter и одного optional adapter:

```text
Required: AmoCRM или Битрикс24
Optional: второй adapter после стабилизации первого
```

Рекомендация: если у Георгия есть доступный тестовый портал Битрикс24 с incoming webhook, начать с Битрикс24. Если проще получить API-доступ AmoCRM, начать с AmoCRM. Не делать обе CRM параллельно до прохождения fake-adapter tests.

CRM payload MVP:

```json
{
  "lead_id": "uuid",
  "source": "website",
  "contact_name": "Иван",
  "contact_phone": "+79991234567",
  "contact_email": null,
  "service": "AI chatbot",
  "deadline": "в течение месяца",
  "budget": "300000",
  "summary": "Клиент хочет внедрить AI-ассистента...",
  "session_id": "uuid",
  "conversation_url": "/sessions/{session_id}/messages"
}
```

Webhook/Telegram можно оставить как backup/debug destination, но не считать заменой CRM-интеграции.

### Задачи

- Добавить env:
  - `REDIS_URL`;
  - `LEAD_DELIVERY_PROVIDER=disabled|fake|amocrm|bitrix24|webhook`;
  - `AMOCRM_BASE_URL`;
  - `AMOCRM_ACCESS_TOKEN`;
  - `BITRIX24_WEBHOOK_URL`;
  - `LEAD_WEBHOOK_URL` для backup/debug;
  - `TELEGRAM_BOT_TOKEN`;
  - `TELEGRAM_CHAT_ID`.
- Добавить Redis client lifecycle в DI.
- Добавить `LeadDeliveryJob` schema.
- Добавить queue abstraction:
  - `enqueue_lead_delivery(lead_id, destination)`;
  - `dequeue_lead_delivery()`;
  - `ack`;
  - `fail`.
- Добавить `LeadDeliveryClient` interface/protocol.
- Добавить `AmoCrmLeadDeliveryClient` или `Bitrix24LeadDeliveryClient`.
- Добавить второй CRM client только после готовности первого.
- Добавить `WebhookLeadDeliveryClient`.
- Добавить `FakeLeadDeliveryClient` для тестов.
- Добавить `LeadDeliveryService`.
- Добавить worker command, например `uv run python -m app.worker.lead_delivery`.
- Добавить ручной endpoint `POST /leads/{lead_id}/deliver`.
- При переходе lead в `ready` автоматически класть delivery job в Redis queue.
- После успешной доставки менять `lead.status` на `delivered`.
- После ошибки менять `lead.status` на `delivery_failed` и сохранять `last_delivery_error`.
- Добавить минимальный `delivery_jobs` или `delivery_attempts` storage в PostgreSQL, если статуса в `leads` недостаточно для debug.
- Зафиксировать mapping полей lead -> CRM.

### Acceptance criteria

- Ready lead автоматически попадает в Redis queue.
- Worker забирает job из Redis queue.
- Worker вызывает fake CRM adapter в тестах.
- Worker вызывает одну реальную CRM в manual smoke.
- Delivery не вызывается для draft lead.
- Успешная доставка меняет статус на `delivered`.
- Ошибка доставки не удаляет lead.
- Ошибка доставки оставляет диагностируемый статус/ошибку.
- Есть fake CRM delivery test.
- Есть manual CRM smoke.
- Есть manual curl demo.

### Что можно урезать

- Не делать полноценный retry/backoff engine.
- Не делать dead-letter queue.
- Не делать email.
- Не делать несколько destinations.
- Не делать двустороннюю синхронизацию CRM.
- Не читать сделки обратно из CRM.
- Не делать OAuth flow, если webhook/token достаточно для пилота.

### Проверочные вопросы

- Почему delivery должен идти через очередь, а не внутри `/message` request?
- Что произойдёт, если Redis недоступен?
- Что произойдёт, если CRM вернула ошибку?
- Почему лид должен сначала сохраниться в БД, потом попасть в очередь, и только потом доставляться?
- Чем `ready` отличается от `delivered`?
- Где mapping полей Innova AI lead -> CRM lead/deal/contact?

## Phase 6 — Реальный AG2 mode и fallback

Цель: доказать, что система работает не только на fake client.

### Задачи

- Проверить, что `LLM_PROVIDER=ag2` реально создаёт `Ag2AgentClient`.
- Проверить, что env names совпадают с README.
- Добавить startup validation:
  - если `LLM_PROVIDER=ag2`, нужен `OPENROUTER_API_KEY`;
  - если ключа нет, приложение падает с понятной ошибкой или явно переключается нельзя.
- Добавить manual smoke script в README:
  - export env;
  - run server;
  - curl message 1;
  - curl message 2;
  - curl message 3;
  - get lead.
- Добавить fallback:
  - invalid JSON;
  - empty response;
  - provider timeout;
  - provider exception.
- Fallback должен отвечать пользователю безопасно и сохранять диалог.

### Acceptance criteria

- Есть один записанный manual сценарий с реальным AG2 provider.
- Invalid JSON от LLM не ломает request.
- Timeout/exception не приводит к 500, если это можно обработать.
- Fake client остаётся для CI.
- Реальный AG2 не нужен для unit/integration tests.

### Что можно урезать

- Не делать provider fallback на второй LLM.
- Не делать streaming.
- Не делать prompt versioning.
- Не делать multi-provider routing.

### Проверочные вопросы

- Как ты запускал real AG2 mode?
- Чем `FakeAg2AgentClient` доказывает бизнес-логику, а чем не доказывает?
- Что происходит при timeout?
- Где граница между fallback answer и loss of state?

## Phase 7 — RAG и база знаний клиента

Цель: дать боту проверяемую базу знаний, чтобы FAQ-ответы опирались на данные клиента, а не на общие догадки LLM.

### Рекомендуемый MVP-подход

Делать RAG, но без автоматического crawler. Для MVP knowledge ingestion должен быть ручным: markdown/текстовые документы загружаются через API или лежат в `docs/knowledge_seed`. Это даёт настоящий retrieval flow, но не распыляет задачу на парсинг сайтов.

Минимальный ingestion input:

```json
{
  "title": "Services and pricing",
  "source": "manual",
  "content": "Базовый пилот Innova AI начинается от 150000 рублей..."
}
```

Минимальный retrieval output:

```json
{
  "query": "Сколько стоит внедрение?",
  "chunks": [
    {
      "document_id": "uuid",
      "chunk_id": "uuid",
      "score": 0.82,
      "content": "Базовый пилот Innova AI начинается от 150000 рублей..."
    }
  ]
}
```

### Задачи

- Выбрать MVP vector store:
  - `pgvector`, если хочется меньше инфраструктуры;
  - `Qdrant`, если хочется явно показать отдельное vector storage.
- Рекомендация для быстрого MVP: `pgvector`, потому что PostgreSQL уже используется.
- Добавить таблицы/модели:
  - `knowledge_documents`;
  - `knowledge_chunks`;
  - embedding/vector field.
- Добавить `KnowledgeIngestionService`.
- Добавить chunking по простому правилу: 500-1000 символов с overlap 100-150 символов.
- Добавить embedding client interface.
- Добавить fake embedding client для тестов.
- Добавить real embedding mode для manual smoke.
- Добавить `KnowledgeRetrievalService`.
- Добавить `POST /knowledge/documents`.
- Добавить `GET /knowledge/documents`.
- Добавить `POST /knowledge/reindex`.
- Передавать top-k retrieved chunks в AG2 prompt.
- Добавить guardrail: если ответа нет в knowledge base, бот предлагает оставить контакт.
- Добавить тест, что relevant FAQ достаётся retrieval service.
- Добавить тест, что unknown question не приводит к выдуманной цене.

### Acceptance criteria

- Можно загрузить 3-5 документов/FAQ.
- Документы разбиваются на chunks.
- Chunks получают embeddings.
- Retrieval возвращает top-k chunks.
- AG2 получает retrieved context.
- Бот отвечает на 3-5 FAQ на основе retrieved context.
- Бот не обязан автоматически сканировать сайт.
- Бот не выдумывает цену, если её нет в config.
- Tests проходят с fake embeddings без внешнего API.
- Manual smoke показывает real retrieval.

### Что можно урезать

- Не делать crawler.
- Не делать tenant-specific spaces.
- Не делать reranking.
- Не делать advanced evaluation.
- Не делать загрузку PDF/Word, достаточно plain text/markdown.

### Проверочные вопросы

- Почему manual ingestion лучше crawler для MVP?
- Что бот должен делать, если ответа нет?
- Как ты запрещаешь LLM придумывать факты?
- Где хранятся документы, chunks и embeddings?
- Какой chunk попал в prompt и почему?

## Phase 8 — Веб-виджет для сайта

Цель: MVP можно показать не только через curl, но и через простой сайтовый чат.

### Рекомендуемый MVP-подход

Сделать минимальный vanilla JS widget без сборки npm-пакета:

```html
<script src="http://localhost:8000/static/widget.js" data-api-base="http://localhost:8000"></script>
```

Виджет должен быть достаточно простым:

- кнопка открытия чата;
- окно сообщений;
- поле ввода;
- сохранение `anonymous_id` в `localStorage`;
- отправка сообщений в `POST /message`;
- отображение ответа;
- обработка loading/error states.

### Задачи

- Добавить static route для `widget.js` или отдельную папку `widget/`.
- Реализовать `widget.js` на vanilla JS.
- Добавить минимальный `widget.css` или inline styles.
- Добавить `demo/widget-demo.html`.
- Передавать:
  - `anonymous_id`;
  - `channel=website`;
  - `content`;
  - `session_id`;
  - `page_url`;
  - `page_title`, если нужно для context.
- Обновить `AgentMessageRequest`, если page context входит в MVP.
- Добавить CORS settings для demo origin.
- Добавить e2e/manual checklist для widget.

### Acceptance criteria

- Demo HTML открывается в браузере.
- Пользователь может отправить первое сообщение из виджета.
- Виджет сохраняет session id между сообщениями.
- Виджет показывает assistant answers.
- Ошибка backend отображается в UI без падения.
- Один полный lead flow можно пройти через widget.

### Что можно урезать

- Не делать React/Vue.
- Не делать npm package.
- Не делать visual customization panel.
- Не делать proactive popups.
- Не делать file upload.
- Не делать operator handoff UI.

### Проверочные вопросы

- Где хранится `anonymous_id`?
- Где хранится `session_id`?
- Что произойдёт после refresh страницы?
- Как widget узнаёт backend URL?
- Какие CORS настройки нужны и почему?

## Phase 9 — Demo readiness

Цель: приложение можно показать как работающий MVP.

### Задачи

- Собрать `docs/DEMO_SCRIPT.md`.
- Включить в demo:
  - запуск backend;
  - первый message;
  - qualification;
  - contact capture;
  - lead ready;
  - get lead;
  - queued delivery;
  - CRM delivery;
  - RAG answer from uploaded knowledge;
  - widget flow.
- Добавить пример curl-команд.
- Добавить expected responses.
- Добавить troubleshooting:
  - DB auth failed;
  - missing API key;
  - webhook unavailable;
  - Redis unavailable;
  - CRM auth failed;
  - RAG has no relevant chunks;
  - invalid LLM JSON.
- Добавить `docs/MVP_LIMITATIONS.md` или section в README.

### Acceptance criteria

- Ментор может пройти demo по инструкции.
- Ученик может объяснить каждый шаг.
- Все MVP limitations названы явно.
- Нет впечатления, что MVP уже является полной платформой.
- Demo показывает виджет, RAG retrieval и CRM delivery, а не только backend curl.

### Что можно урезать

- Не делать красивый frontend за пределами минимального widget.
- Не делать деплой, если цель только локальный demo.
- Не делать dashboard.

### Проверочные вопросы

- Какой самый короткий путь доказать MVP?
- Какие команды нужно выполнить с нуля?
- Где видно, что лид реально создан?
- Что в demo является fake/stub, а что real?

## Рекомендуемый порядок работ по дням

### День 1 — Scope и стабильность

- Обновить README/env.
- Починить `ruff`.
- Зафиксировать команды тестов.
- Убедиться, что unit tests зелёные.
- Подготовить test DB или описать её создание.

Результат дня: проект можно проверять базовыми командами.

### День 2 — State machine

- Переписать readiness rules.
- Проверять all required fields.
- Добавить тесты на premature `LEAD_READY`.
- Добавить tests на merge qualification.
- Добавить tests на contact validation.

Результат дня: LLM не может преждевременно закрыть лид.

### День 3 — End-to-end lead flow

- Обновить `AgentService`.
- Добавить full multi-turn test.
- Проверить накопление qualification.
- Проверить lead status.
- Проверить fallback.

Результат дня: fake-client сценарий полностью доводит пользователя до ready lead.

### День 4 — Lead API

- Добавить `GET /leads`.
- Добавить `GET /leads/{lead_id}`.
- Добавить tests.
- Обновить README.

Результат дня: лид можно увидеть через API.

### День 5 — Redis queue

- Подключить Redis.
- Добавить queue abstraction.
- Добавить enqueue job при `lead.status=ready`.
- Добавить worker command.
- Добавить fake/in-memory queue для тестов.

Результат дня: ready lead попадает в очередь, worker может забрать job.

### День 6 — CRM delivery

- Реализовать первый CRM adapter: AmoCRM или Битрикс24.
- Добавить fake CRM adapter.
- Добавить mapping lead fields -> CRM fields.
- Добавить worker delivery flow.
- Добавить manual CRM smoke.

Результат дня: ready lead доставляется в одну CRM через worker.

### День 7 — RAG foundation

- Выбрать `pgvector` или Qdrant.
- Добавить knowledge document/chunk модели.
- Добавить ingestion endpoint.
- Добавить fake embeddings.
- Добавить retrieval service.

Результат дня: knowledge documents загружаются и ищутся через retrieval service.

### День 8 — RAG в AG2 flow

- Передавать retrieved chunks в AG2 prompt.
- Добавить guardrail на отсутствие контекста.
- Добавить тесты на known/unknown FAQ.
- Провести manual RAG smoke.

Результат дня: бот отвечает на FAQ из базы знаний и не выдумывает неизвестные факты.

### День 9 — Real AG2 smoke

- Проверить real provider config.
- Запустить ручной сценарий с `LLM_PROVIDER=ag2`.
- Зафиксировать known limitations.
- Починить prompt/schema mismatch.

Результат дня: есть доказательство, что AG2 mode работает.

### День 10 — Web widget

- Сделать `widget.js`.
- Сделать demo HTML.
- Добавить CORS config.
- Пройти полный lead flow через browser widget.
- Зафиксировать widget limitations.

Результат дня: MVP можно показать через простой сайтовый чат.

### День 11 — Demo polish

- Написать `docs/DEMO_SCRIPT.md`.
- Пройти demo с чистой БД.
- Исправить README.
- Зафиксировать MVP limitations.

Результат дня: проект готов к показу как расширенный быстрый MVP.

## Definition of Done для MVP

MVP готов, если выполнены все пункты:

- `POST /message` ведёт multi-turn диалог.
- Backend собирает `service`, `deadline`, `budget`, `contact`.
- Backend сам решает, когда лид готов.
- Lead сохраняется в PostgreSQL.
- Lead доступен через `GET /leads/{lead_id}`.
- Lead автоматически ставится в Redis queue.
- Worker доставляет lead минимум в одну CRM: AmoCRM или Битрикс24.
- Второй CRM adapter реализован или явно отмечен как optional stretch внутри MVP.
- Delivery status доступен через API или lead response.
- RAG knowledge documents можно загрузить вручную.
- Retrieval возвращает релевантные chunks.
- AG2 получает retrieved context.
- Unknown FAQ не приводит к выдуманному ответу.
- Минимальный web widget позволяет пройти диалог с сайта/demo HTML.
- История сообщений доступна через API.
- Unit tests зелёные.
- Integration tests зелёные на test DB.
- Redis/worker tests зелёные или документированы отдельной командой.
- CRM delivery tests зелёные на fake adapter.
- Есть full flow test без real LLM key.
- Есть manual smoke с real AG2 provider.
- Есть manual smoke с real CRM или тестовым CRM webhook.
- Есть manual smoke через widget.
- README не противоречит коду.
- Есть demo script.
- Известные ограничения явно перечислены.

## Не-MVP backlog

### После MVP: Production hardening

- retries;
- delivery log;
- Docker Compose;
- CI;
- structured logging;
- health checks;
- basic metrics;
- rate limiting.

### После MVP: Product surface

- lead dashboard UI;
- tenant settings UI;
- prompt/knowledge settings;
- simple analytics.

### После MVP: Platform

- multi-tenancy;
- auth;
- roles;
- tariff limits;
- tenant-specific configs;
- audit logs.

### После MVP: AI quality

- website crawler;
- advanced vector search / reranking;
- prompt versioning;
- answer evaluation;
- hallucination review.

### После MVP: Integrations

- Telegram full bot/channel;
- CRM adapter not selected for MVP;
- HubSpot;
- Avito;
- YClients/Calendar;
- analytics connectors.

## Главные риски

### Риск 1 — MVP расползётся в платформу

Признак: ученик начинает делать Avito, multi-tenancy, billing, dashboard или второстепенные CRM-фичи до закрытия lead flow.

Контрмера: любой новый функционал должен отвечать на вопрос: "помогает ли он провести сайт-пользователя до ready lead, найти ответ в knowledge base и доставить лид в выбранную CRM?"

### Риск 2 — LLM управляет бизнес-логикой

Признак: `lead_ready`, `state`, `missing_fields` принимаются без backend-проверки.

Контрмера: LLM извлекает и предлагает, backend решает.

### Риск 3 — Нет проверяемости

Признак: ученик показывает код, но не может показать test, curl и запись в БД/API.

Контрмера: каждый phase закрывается acceptance criteria и demo.

### Риск 4 — Fake flow выдаётся за real flow

Признак: всё работает только с `FakeAg2AgentClient`.

Контрмера: fake нужен для CI, но перед MVP нужен manual smoke с `LLM_PROVIDER=ag2`.

### Риск 5 — Документация продаёт больше, чем код умеет

Признак: README говорит про платформу, CRM, state machine, но demo показывает только stub.

Контрмера: README делится на `Implemented`, `MVP next`, `Post-MVP`.

### Риск 6 — Инфраструктура съедает MVP

Признак: ученик тратит основное время на Redis, vector DB, CRM auth и widget polish, а lead flow остаётся нестабильным.

Контрмера: каждую инфраструктурную часть закрывать через fake adapter + один manual smoke, без попытки сделать production-grade реализацию.

### Риск 7 — RAG выдаётся за обычный prompt stuffing

Признак: в prompt просто кладётся весь markdown-файл, retrieval и chunk scoring отсутствуют.

Контрмера: требовать явные chunks, top-k retrieval, score и тест на релевантный/нерелевантный вопрос.

### Риск 8 — CRM-интеграция не проверяема

Признак: код adapter есть, но нет fake adapter tests, нет mapping документа и нет manual smoke с test account/webhook.

Контрмера: закрывать CRM только после демонстрации created lead/deal/contact в выбранной CRM или тестовом webhook-аналоге.

## Менторский gate

Перед переходом дальше Георгий должен показать:

1. Полный multi-turn сценарий через `POST /message`.
2. Переходы state machine на каждом шаге.
3. Накопление `qualification_data`.
4. Невозможность преждевременного `LEAD_READY`.
5. Созданный lead через `GET /leads/{lead_id}`.
6. Постановку delivery job в Redis queue.
7. Worker, который доставляет lead в AmoCRM или Битрикс24.
8. RAG: ingestion, chunks, retrieval и prompt context.
9. Полный сценарий через веб-виджет.
10. Unit + integration tests.
11. Один real AG2 smoke.
12. Один real/fake CRM delivery smoke с понятным результатом.
13. Объяснение, что урезано из полного PRD и почему.

Если хотя бы пункты 1-9 не показаны, это ещё не расширенный MVP, а backend prototype с отдельными интеграционными заготовками.
