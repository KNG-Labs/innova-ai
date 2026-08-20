# DeepEval evaluation suite

`evals/` использует `deepeval==4.1.4` как локальный dataset/runner/metric
движок. Никакие результаты не отправляются в Confident AI:
`DEEPEVAL_DISABLE_DOTENV=1`, `DEEPEVAL_TELEMETRY_OPT_OUT=YES` и пустой
`CONFIDENT_API_KEY` задаются самим eval-пакетом и отдельным runner image.

## Datasets

В `evals/datasets/` находятся DeepEval-native JSON-массивы:

- 100 retrieval `Golden`;
- 108 generation `Golden`;
- 12 business `ConversationalGolden`.

Стабильный ID, `split`, `category`, relevance, обязательные факты, запрещённые
утверждения и business expectations сохранены в `additional_metadata`.
Валидатор также проверяет уникальность ID и type-specific контракт:

```bash
uv run python -m evals.runners.evaluate --dataset evals/datasets
```

Frozen corpus и его стабильные document IDs зафиксированы в
`evals/datasets/retrieval/corpus_manifest.json`. Runner может очищать и
загружать knowledge-таблицы только в БД с именем, заканчивающимся на `_eval`
или `_test`.

## Метрики

Retrieval фиксирован на `K=10`:

- `retrieval_recall@10`;
- `retrieval_mrr@10`;
- `context_precision@10`;
- `abstention_accuracy@10`.

Они детерминированно используют уникальные document IDs и relevance labels.

Judge-метрики:

- `required_fact_coverage`;
- `forbidden_claim_rate`;
- `business_dialogue_success`.

`RequiredFactCoverage` и `ForbiddenClaimRate` делают по одному structured
judge-вызову на кейс. `BusinessDialogueSuccess` объединяет semantic verdict по
полному transcript с точными проверками state, intent, missing fields и полей
лида. Перед judge-вызовом transcript проходит существующую PII-защиту; контакты
проверяются только локальным guardrail.

Восьмая метрика — `average_agent_token_usage`. Она включает только AG2 main
agent и retrieval planner, суммируется на API eval-кейс и не включает judge или
embeddings. При отсутствующем `message_metadata.eval_token_usage` кейс
исключается из среднего, а результат помечается `incomplete`.

## Judge

Обязательные переменные для semantic eval:

```text
EVAL_JUDGE_MODEL
OPENROUTER_API_KEY
OPENROUTER_BASE_URL  # optional, default: https://openrouter.ai/api/v1
```

Judge использует temperature `0` и OpenRouter structured JSON output. Если
`EVAL_JUDGE_MODEL` совпадает с `AG2_MODEL`, runner пишет предупреждение и
`self_judge: true` в manifest. Флаг `--require-independent-judge` превращает
совпадение в ошибку.

## Запуск

Все типы, один прогон:

```bash
EVAL_REPORT_NAME=real-baseline-v4 \
docker compose --env-file .env -f docker-compose.eval.yml up --build \
--force-recreate --abort-on-container-exit \
--exit-code-from eval-runner eval-runner
```

Фильтры `--evaluation-type` и `--split` можно повторять. Дополнительные прогоны
задаются явно через `--repetitions`; default равен `1`. `--top-k` допускает
только `10`, чтобы конфигурация retrieval и формулы отчёта не расходились.

Default output:

```text
evals/reports/runs/<timestamp>-<commit>/
```

Каталог содержит:

- DeepEval JSON test runs с per-case scores, reasons и transcripts;
- DeepEval Markdown dashboards;
- `summary.json`;
- `predictions.json`;
- `manifest.json` с Git SHA, hashes, моделями, RAG-параметрами, `self_judge` и
  token breakdown.

## Docker Compose

`docker-compose.eval.yml` использует отдельный `Dockerfile.eval`; production
image по-прежнему собирается без eval dependency group. Datasets и `docs/RAG`
монтируются read-only, reports — отдельно на запись. Runtime secrets не
копируются в image.

Compose запускается только с безопасной eval-БД:

```bash
docker compose -f docker-compose.eval.yml up --build \
  --abort-on-container-exit --exit-code-from eval-runner eval-runner
docker compose -f docker-compose.eval.yml down
```

Не используйте `down -v` для production Compose. Реальные judge-evals не входят
в CI; unit-тесты используют fake structured judge.
