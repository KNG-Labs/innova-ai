# Innova AI

Диалоговый сервис лидогенерации для автомобильного дилера: отвечает на вопросы
по базе знаний, уточняет условия покупки, собирает контакт и передаёт лид в CRM.
Текущая реализация рассчитана на одного дилера.

## Возможности

- Веб-виджет, HTTP API и Telegram-бот.
- Ответы по базе знаний через RAG и pgvector.
- Квалификация по модели автомобиля, бюджету и способу покупки.
- Сохранение истории диалога и контактов в PostgreSQL; токенизация контактов перед AI-вызовами.
- Асинхронная доставка в AmoCRM или webhook через Celery и Redis.

## Стек

Python 3.13, FastAPI, Pydantic, SQLAlchemy asyncio, PostgreSQL 17 + pgvector,
Redis, Celery, AG2/OpenRouter. Разработка: uv, pytest, Ruff и mypy.

## Быстрый запуск

Нужны Docker Engine и Docker Compose. Если `.env` ещё нет, создайте его из шаблона:

```bash
cp .env.example .env
```

Шаблон использует заглушки LLM и embeddings; доставка лидов отключена.
Запустите API и worker вместе с PostgreSQL, Redis и миграциями:

```bash
docker compose up --build api worker
```

- [Демо виджета](http://localhost:8000/static/widget-demo.html)
- [Swagger / OpenAPI](http://localhost:8000/docs)

Настройка провайдеров, запуск Telegram-бота и работа с кодом описаны в
[инструкции по разработке](docs/DEVELOPMENT.md).
API пока не имеет аутентификации; административные методы нельзя открывать в интернет.

## Документация

- [Разработка, конфигурация и тестирование](docs/DEVELOPMENT.md)
- [API и встраивание виджета](docs/API.md)
- [Текущая архитектура, состояния диалога и ограничения](docs/ARCHITECTURE.md)
- [Доставка лидов: повторы и ручная проверка](docs/operations/CELERY.md)
- [CI/CD](docs/operations/CI_CD.md) и [развёртывание на VPS](docs/operations/VPS_DEPLOY.md)
- [Оценка качества и метрики](docs/EVALUATION.md)
- [Продуктовое видение](docs/PRD.md) и [целевая архитектура](docs/System_Design.md)
- [Диаграммы текущей системы](docs/diagrams/current/) и [целевой архитектуры](docs/diagrams/target/)
- [Материалы базы знаний](docs/RAG/)
