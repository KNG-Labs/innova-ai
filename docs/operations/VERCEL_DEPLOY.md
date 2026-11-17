# Публичное демо на Vercel

Схема: страница и FastAPI на Vercel Hobby, PostgreSQL с pgvector на Neon Free,
отдельный ключ OpenRouter с лимитом $1 без сброса. Redis, Celery worker, CRM
и Telegram для демо не запускаются. Старые данные с VPS не переносятся.

## 1. Проект Vercel

Создать проект `innova` с framework `FastAPI` в личном Hobby workspace.
Корень проекта — корень репозитория. Python 3.13 закреплён в `.python-version`,
регион `fra1` — в `vercel.json`. Независимые Git-деплои выключены конфигурацией;
подключение GitHub-репозитория для CLI-выпуска необязательно.

В production environment проекта задать:

| Переменная | Значение |
| --- | --- |
| `PUBLIC_DEMO` | `1` |
| `PYTHON_DOTENV_DISABLED` | `1` |
| `LLM_PROVIDER` | `ag2` |
| `EMBEDDING_PROVIDER` | `openrouter` |
| `EMBEDDING_MODEL` | `openai/text-embedding-3-small` (1536 измерений) |
| `LEAD_DELIVERY_PROVIDER` | `disabled` |
| `LANGFUSE_TRACING_ENABLED` | `false` для первого запуска |
| `AG2_MODEL` | Та же модель, что у рабочего локального чата |
| `CORS_ALLOW_ORIGINS` | Публичный origin этого проекта, без завершающего `/` |
| `DATABASE_URL` | Прямой asyncpg URL Neon с `ssl=verify-full` |
| `OPENROUTER_API_KEY` | Отдельный ключ демо с лимитом $1 |

Секреты вводить непосредственно в настройки сервисов, не в чат, Git или
`.env.example`. Рабочие `.env` и `.env.production` не копировать. `.vercel/`
с выгруженными настройками игнорируется Git; его содержимое не публикуется
как CI artifact. `.vercelignore` и excludeFiles убирают рабочие env-файлы,
тесты, evals и документацию из функции.

`PUBLIC_DEMO=1` исключает маршруты `/knowledge`, `/leads`, `/sessions`, но сохраняет
контракт `POST /message`, состояние диалога и локальную очистку ПД. В этом режиме
приложение откажется стартовать, если включена отправка лидов. Готовые заявки
сохраняются только в БД. `/` перенаправляет на `/static/widget-demo.html`.

## 2. Neon Free

Подключить Neon через Marketplace к проекту Vercel, выбрать именно Free,
использовать проект `aged-tree-60017005` (PostgreSQL 18, AWS Frankfurt),
ветку `production` и отдельную БД `innova`.
Использовать новый выделенный проект; рабочую БД с VPS не подключать.
Расширение `vector` создаётся существующей миграцией.

Взять **прямой**, не `-pooler`, endpoint. Для текущего asyncpg-клиента преобразовать
строку подключения: схема `postgresql+asyncpg://`, имя БД `innova`,
параметр `ssl=verify-full`. Удалить параметры `sslmode` и `channel_binding`:
они относятся к другому драйверу. Пароль должен оставаться URL-encoded.
Этот один URL сохранить как `DATABASE_URL` в Vercel и `DEMO_DATABASE_URL`
в GitHub Environment `production`.

На Vercel приложение использует `NullPool` и требует TLS. После простоя Neon
может просыпаться с задержкой; CI повторяет безопасные GET-проверки.

## 3. Ключ OpenRouter и защита от расходов

Создать отдельный API key `innova`, установить **Limit = $1**,
**Limit reset = none**. Используется существующий баланс; не включать
автопополнение. Один ключ оплачивает и ответы, и embeddings начального корпуса.
Сохранить его только в production-переменной `OPENROUTER_API_KEY` Vercel.
После исчерпания лимита модель станет недоступной; ключ основного приложения
при этом не затрагивается.

В Vercel Firewall создать и включить одно правило:

- условия: `Request Path` равен `/message`, метод равен `POST`;
- действие: rate limit, fixed window, **25 requests / 60 seconds**, ключ **IP**;
- превышение лимита блокируется с HTTP 429.

Правило действует до запуска функции и не требует Redis. Сначала подтвердить
его наличие в активной конфигурации, затем публиковать демо. CORS не заменяет
это правило и не ограничивает расходы API.

## 4. GitHub Actions

В `KNG-Labs/innova-ai` → Settings → Environments → `production`:

| Тип | Имя | Назначение |
| --- | --- | --- |
| Secret | `VERCEL_TOKEN` | Токен для выпуска в выбранный workspace |
| Secret | `DEMO_DATABASE_URL` | Тот же прямой asyncpg URL, что у Vercel |
| Secret | `OPENROUTER_API_KEY` | Тот же ограниченный ключ; для загрузки embeddings |
| Variable | `VERCEL_ORG_ID` | ID workspace Vercel |
| Variable | `VERCEL_PROJECT_ID` | ID проекта `innova` |

Ограничить environment веткой `main`; требуемая проверка слияния — `Checks`.
Токен должен иметь минимально необходимый доступ к выбранному workspace.
Его значения не передаются аргументом `--token`, не выводятся в логи.
PR не получает перечисленных секретов.

После настройки внести изменения через PR в `main`. Workflow сам проверит код,
соберёт функцию, применит миграции, загрузит знания в пустую БД и переключит
публичный адрес после проверки. Защищённые (Sensitive) переменные Vercel не выгружаются через `vercel pull`: вместо
них приходят заглушки. Поэтому загрузка знаний берёт ключ из секрета GitHub,
а приложение получает настоящий ключ непосредственно в Vercel.

Для первого выпуска загрузка embeddings расходует
часть бюджета $1. Для следующих выпусков заполненный корпус пропускается.

Сценарий выпуска и отката: [CI/CD](CI_CD.md).

## Проверка перед первым выпуском

Все pytest и полные прогоны чата запускать только на отдельной временной БД
с суффиксом `_test`, явно задав одинаковые `DATABASE_URL` и `TEST_DATABASE_URL`
по инструкции AGENTS.md. Временная база не должна быть публичной `innova`.
Проверить диалог, квалификацию, сохранение истории, отсутствие отправки лидов,
недоступность административных методов и 429 при превышении частоты запросов.

Скрипт `python -m scripts.seed_knowledge <corpus.json>` использует
`KnowledgeIngestionService`, заполняет только пустую БД и допускает лишь
`innova` либо временные БД `_test`/`_eval`. Не запускать его с рабочими
локальными env-настройками. В CI все необходимые параметры задаются явно.

Vercel Hobby и Neon Free имеют квоты. Первый ответ после простоя может быть
медленнее; лимит OpenRouter может быстро исчерпаться на публичной ссылке.
Изменение CI/CD не выключает старый VPS и не прекращает его оплату.

Официальные справочники: [FastAPI](https://vercel.com/docs/frameworks/backend/fastapi),
[Hobby](https://vercel.com/docs/plans/hobby), [Neon Free](https://neon.com/pricing),
[лимиты ключей OpenRouter](https://openrouter.ai/docs/api/api-reference/api-keys/create-keys).
