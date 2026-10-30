# Доставка лидов через Celery

API сохраняет готовый лид и публикует его UUID в `innova.lead_delivery`.
Worker доставляет лид в CRM и сохраняет результат в PostgreSQL.
Запуск и окружение описаны в [инструкции по разработке](../DEVELOPMENT.md#локальная-разработка).

## Повторы и состояния

| Статус | Значение |
| --- | --- |
| `delivered` | Успех подтверждён; повтор не обращается к CRM |
| `delivery_failed` | Подтверждено отсутствие создания; повтор разрешён |
| `needs_review` | Результат неизвестен; новая отправка запрещена |

Celery повторяет только `ConnectError`, `ConnectTimeout` и `PoolTimeout`:
первая попытка плюс максимум три повтора с backoff и jitter.
Остальные неподтверждённые ошибки, включая HTTP 4xx/5xx, требуют ручной проверки.

До запроса в CRM отдельно сохраняется отметка `lead_delivery_attempts`.
Блокировка строки согласует параллельные доставки. При падении worker отметка
переживает откат; повторная выдача задачи переводит лид в `needs_review`
без нового запроса создания. Падение до отправки HTTP-запроса тоже может
потребовать проверки: наличие отметки не доказывает, что сделка создана.

## Проверка и повторная отправка

С тем же окружением, что у worker:

```bash
curl --fail http://127.0.0.1:8000/leads/LEAD_UUID
curl --fail 'http://127.0.0.1:8000/leads?status=needs_review'
.venv/bin/python -c "from app.worker.lead_delivery import deliver_lead; print(deliver_lead.delay('LEAD_UUID').id)"
```

Проверяйте статус лида: ID задачи и `SUCCESS` не подтверждают доставку.
`POST /leads/LEAD_UUID/deliver` выполняет одну синхронную попытку без повторов
Celery; для `needs_review` возвращает HTTP 409.

## Ручная проверка needs_review

Сначала установите результат в CRM. Автоматического поиска сделки по UUID Innova
в адаптере amoCRM нет. Если результат неизвестен, отметку и статус не сбрасывайте.
Время попытки доступно в `lead_delivery_attempts.started_at`.

После подтверждения существующей сделки выполните в psql, заменив UUID:

```sql
\set lead_id '00000000-0000-0000-0000-000000000000'
BEGIN;
SELECT id, status FROM leads WHERE id = :'lead_id' FOR NO KEY UPDATE;
WITH resolved AS (
  UPDATE leads SET status = 'delivered', last_delivery_error = NULL
  WHERE id = :'lead_id' AND status = 'needs_review' RETURNING id
), cleared AS (
  DELETE FROM lead_delivery_attempts USING resolved
  WHERE lead_delivery_attempts.lead_id = resolved.id
  RETURNING lead_delivery_attempts.lead_id
)
SELECT id FROM resolved;
COMMIT;
```

Если подтверждено, что сделка не создана, замените `delivered` на `ready`
в `UPDATE`, затем явно опубликуйте задачу командой выше. Запрос должен вернуть
нужный UUID; пустой результат означает отсутствие изменений.

## Ограничения

- Между сохранением готового лида и публикацией остаётся разрыв; outbox нет.
  После ошибки брокера или БД оставшиеся `ready`-лиды публикуются явно.
- После потери дочернего процесса Celery выдаёт задачу повторно. При падении
  всего worker восстановление Redis может ждать visibility timeout — по умолчанию час.
  Повторная выдача не расходует `max_retries`; при циклическом падении worker
  нужно остановить и устранить причину.
- Активная доставка может использовать два соединения PostgreSQL. Начальный
  параллелизм worker — один процесс.
