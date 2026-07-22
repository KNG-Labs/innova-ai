# Evaluation Innova AI

Наборы в `evals/datasets/` проверяют:

- `retrieval` — поиск документов;
- `generation` — содержание ответа агента;
- `business` — состояние диалога и поля лида.

## Датасеты

Каждый кейс содержит уникальный `id`, категорию, вопрос и назначение выборки:

- `calibration` — подбор параметров поиска;
- `test` — итоговая оценка;
- `regression` — критические сценарии.

Для `retrieval` и `generation` поле `answerable` указывает, есть ли ответ в базе
знаний. `relevance` связывает документы с оценкой важности от 1 до 3.

Generation-кейсы содержат обязательные факты `required_facts` и запрещённые
утверждения `forbidden_claims`. Допустимые текстовые варианты факта разделяются
через `||`:

```json
{
  "id": "gen_reg_hours_01",
  "split": "regression",
  "category": "hours",
  "question": "До скольки вы работаете?",
  "answerable": true,
  "relevance": {"dealer_hours": 3},
  "required_facts": ["21:00 || девяти вечера"],
  "forbidden_claims": ["работаете круглосуточно"]
}
```

Business-кейсы поддерживают `setup_messages`, `expected_intent`,
`expected_state`, `expected_missing_fields`, `expected_fields`,
`expected_behavior` и `expected_max_questions`.

## Корпус

`evals/datasets/retrieval/corpus_manifest.json` содержит стабильные ID документов,
контрольные суммы SHA-256 и ID фрагментов.

Runner принимает БД с суффиксом `_eval` или `_test`, очищает knowledge-таблицы и
загружает корпус из `docs/RAG/Данные для RAG.txt`. Рабочую БД использовать нельзя.
Корпус и retrieval подготавливаются один раз на весь запуск.

## Запуск

Изолированный запуск всех метрик:

```bash
cp .env.example .env
EVAL_REPORT_NAME=before-rag \
  docker compose -f docker-compose.eval.yml up --build \
  --abort-on-container-exit --exit-code-from eval-runner eval-runner
docker compose -f docker-compose.eval.yml down
```

По умолчанию Compose использует `stub` LLM и `fake` embeddings. Для измерения
реальной модели задайте `LLM_PROVIDER=ag2`, модель и ключ провайдера в `.env`.
Compose поднимает
отдельную БД `innova_ai_eval`, применяет миграции и запускает API. Каталог
`docs/RAG` монтируется в runner только для чтения. Runner проверяет файл
`Данные для RAG.txt` по manifest и загружает его через штатный ingestion-сервис.
Отчёт сохраняется в `evals/reports/baselines/` на хосте. Для полного удаления
eval-БД выполните `docker compose -f docker-compose.eval.yml down -v`.
В контейнер можно передать `EVAL_GIT_COMMIT` и `EVAL_GIT_DIRTY`; без них Git-поля
отчёта будут пустыми, поскольку каталог `.git` не попадает в образ.
Если UID/GID локального пользователя отличаются от `1000:1000`, передайте
`EVAL_UID` и `EVAL_GID`, чтобы файлы отчёта принадлежали вам.

Проверить датасеты:

```bash
uv run python -m evals.runners.evaluate --dataset evals/datasets
```

Проверить только retrieval без API:

```bash
EVAL_DATABASE_URL=postgresql+asyncpg://innova:innova@localhost:5433/innova_ai_eval \
  uv run python -m evals.runners.run --evaluation-type retrieval
```

Запустить `test` и `regression` через API:

```bash
EVAL_DATABASE_URL=postgresql+asyncpg://innova:innova@localhost:5433/innova_ai_eval \
INNOVA_EVAL_API_URL=http://localhost:8001 \
  uv run python -m evals.runners.run \
  --repetitions 3 \
  --split test --split regression \
  --output evals/reports/baselines/baseline.json
```

API и runner должны использовать одинаковые eval-БД, embedding-модель,
`RAG_TOP_K` и `RAG_MIN_SCORE`.

## Метрики

### RetrievalRecall@K

Доля релевантных документов, найденных среди первых `K` результатов. Диапазон
от 0 до 1. Больше — лучше.

### MRR@K

Обратная позиция первого релевантного документа. Если он первый, значение равно
1; если второй — 0.5. Больше — лучше.

### ContextPrecision@K

Доля релевантных документов среди результатов, переданных агенту. Показывает,
насколько контекст очищен от лишней информации. Больше — лучше.

### AbstentionAccuracy@K

Доля запросов без ответа в базе знаний, для которых retrieval не вернул
документы. Больше — лучше.

### RequiredFactCoverage

Доля обязательных фактов, найденных в ответе. Проверка выполняется по текстовым
вариантам из `required_facts`. Больше — лучше.

### ForbiddenClaimRate

Доля размеченных запрещённых формулировок, найденных в ответе. Проверка
выполняется по текстовым вариантам из `forbidden_claims`; альтернативы
разделяются через `||`. Меньше — лучше. Метрика не распознаёт неразмеченные
перефразирования.

### BusinessDialogueSuccess

Доля business-кейсов, в которых одновременно выполнены все ожидания по ответу,
числу вопросов, intent, состоянию диалога, недостающим полям и данным лида.
Больше — лучше.

## Отчёт

`value` содержит среднее значение метрики, `n` — количество уникальных
оценённых кейсов. Для повторных запусков `observation_n` содержит число
измерений с учётом повторов, а `run_stddev` — разброс результатов между ними.
Поля `prediction_count` и `prediction_observation_count` используют ту же
семантику для полученных predictions.
Retrieval выполняется один раз, поэтому его метрики всегда имеют `runs=1`;
повторения применяются только к generation и business-вызовам через API.

Отдельно сохраняется latency: среднее значение, p50 и p95. Latency не входит в
оценку качества.

Отчёт также содержит Git commit, хэши датасетов и корпуса, модели, параметры
поиска, длительность запуска и predictions. Без `--output` файлы сохраняются в
`evals/reports/runs/`.
