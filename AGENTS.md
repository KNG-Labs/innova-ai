# Руководство для агентов Innova AI

## Область действия

Эти инструкции применяются ко всему репозиторию.

## Обязательные правила безопасности

- Никогда не изменять `.env` или
  `.env.production`, если пользователь явно не запросил требующую этого операцию.
- Оба env-файла содержат реальные секреты и намеренно не отслеживаются Git.
- Никогда не запускать Alembic без явно заданного безопасного `DATABASE_URL`.
- Тесты и оценки можно запускать только с временными базами данных, имена которых
  оканчиваются на `_test` или `_eval`.
- Никогда не запускать `docker compose down -v` в производственной среде.
- Никогда не коммитить env-файлы, учётные данные, SSH-ключи, токены доступа и
  сгенерированные секреты.
- Не разделять CI и CD на отдельные workflow-файлы, пока веткой GitHub по умолчанию
остаётся `main`.

## Проверка

Подготовка и локальные проверки:

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

Инструкция по деплою находится в `docs/operations/VPS_DEPLOY.md`
