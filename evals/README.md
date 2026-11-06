# RAG evaluation: DeepEval + Jev

Один runner: `python -m evals.run`. Две встроенные метрики DeepEval 4.3.3:

- **Answer Relevancy**: отвечает ли текст на вопрос пользователя.
- **Faithfulness**: подтверждаются ли утверждения ответа найденным контекстом.

Обе используют `eval_mode="system_one"`: Jev оценивает готовый ответ без
LLM-судьи и без fallback на LLM. Сам агент по-прежнему использует свою LLM,
а поиск — embedding-модель. Оценка Jev также расходует API-бюджет.
Порог обеих метрик — `0.7` (`THRESHOLD` в `run.py`), стартовое значение,
которое ещё нужно проверить на ручной разметке. Это не измеренная гарантия качества.

## Что сохранено в datasets

Все исходные JSON и corpus manifest оставлены без изменений:

- `generation`: 108 вопросов; runner использует только `answerable=true`.
- `retrieval`: 100 вопросов с relevance labels, сохранены для будущих проверок поиска.
- `business`: 12 многошаговых сценариев, сохранены для будущих бизнес-проверок.

Статическая проверка субагентом gpt-6-luna: 220 уникальных ID, корректные splits,
согласованные relevance labels; manifest соответствует всем 50 документам корпуса.
Критичных противоречий ожиданий с корпусом не найдено. Точные вопросы между
retrieval и generation повторяются в пределах одинаковых splits — это связанные
наборы, а не перенос вопроса из calibration в test.

В `generation/test` 24 answerable-кейса. Ещё 6 вопросов без ответа в БЗ
исключены: `gen_test_chery_01`, `gen_test_audi_01`, `gen_test_mercedes_01`,
`gen_test_mazda_01`, `gen_test_negative_01`, `gen_test_negative_02`.
Корректность отказов и полей лида эти две метрики не проверяют.
Старые `required_facts`, `forbidden_claims`, `expected_output` и business expectations
остаются в датасетах как разметка; текущие метрики их не используют.

## Первый запуск: 5 вопросов

Нужны Docker, `OPENROUTER_API_KEY`, `TYPESAFE_API_KEY` и настройки
`AG2_MODEL`/`EMBEDDING_MODEL` в существующем `.env`. Compose прочитает этот файл;
копировать ключи в команды не нужно:

```bash
mkdir -p evals/reports
docker compose -f docker-compose.eval.yml build eval-runner
docker compose -f docker-compose.eval.yml run --rm eval-runner --limit 5
```

Compose поднимает отдельную PostgreSQL `innova_ai_eval` в tmpfs, применяет миграции
и запускает реального агента с реальными embeddings. CRM, Redis-очередь и Langfuse
для этого прогона отключены. Рабочий `DATABASE_URL` из `.env` переопределён
адресом eval-базы; runner дополнительно проверяет суффикс `_eval`/`_test`.
**Корпус временной базы заменяется содержимым `docs/RAG/Данные для RAG.txt`**.

Runner вызывает обычный `AgentService` и сохраняет итоговый ответ с фрагментами,
которые вернул поиск именно в этом вызове. Повторного поиска для оценки нет.
**Контакты перед записью отчёта и отправкой Jev маскируются существующим PII-фильтром;**
ошибка анализа останавливает оценку. Этот фильтр не является универсальным
детектором любых секретов: используйте только подготовленные тестовые данные.

По умолчанию `--split test --limit 5`. Полный текущий test-набор:

```bash
docker compose -f docker-compose.eval.yml run --rm eval-runner --limit 24
```

После работы остановите только eval-окружение:

```bash
docker compose -f docker-compose.eval.yml down
```

Временная БД исчезнет, отчёты останутся в `evals/reports/` и не попадут в Git.

## Разделить генерацию и оценку

Сначала соберите ответы. `--collect-only` не требует Jev и не вызывает его;
реальные агент и embeddings всё ещё платные:

```bash
docker compose -f docker-compose.eval.yml run --rm eval-runner \
  --collect-only --limit 5 --output evals/reports/baseline
```

Прочитайте `evals/reports/baseline/test_cases.json`: `input` — вопрос,
`actual_output` — ответ, `retrieval_context` — использованные фрагменты.
Затем оцените именно эти ответы, без приложения, PostgreSQL и OpenRouter:

```bash
uv sync --frozen
uv run --env-file .env python -m evals.run \
  --predictions evals/reports/baseline/test_cases.json \
  --output evals/reports/baseline-scores
```

`uv --env-file .env` передаёт ключ из существующего файла в окружение процесса.
Runner и DeepEval сами env-файлы не загружают. Рабочий `DATABASE_URL` при
`--predictions` не используется: приложение и БД в этом режиме не запускаются.
Каталог `--output` должен быть новым: runner не перезаписывает прошлые результаты.
`--split` и `--limit` применяются при сборе, а `--predictions` оценивает весь
сохранённый файл.

## Как читать результат

- `test_cases.json`: вопросы, ответы и фактический контекст после маскирования контактов.
- `results.json`: результаты двух встроенных метрик, scores, success и reasons.
- `answer_relevancy/`, `faithfulness/`: стандартные JSON-отчёты DeepEval.
- `manifest.json`: модели, параметры, порог и хеши входных данных. После оценки
  блок `judge` содержит `requested_model` (например, `jev-latest`),
  `response_models` (имена из ответов TypeSafe), версии DeepEval и TypeSafe SDK.
  Если алиас переключился в середине прогона, список покажет несколько моделей.
  При ошибке вызова Jev этот блок тоже сохраняется; пустой список означает, что ни один
  ответ модели ещё не был получен. При `--collect-only` судья не вызывается
  и блока `judge` нет. `reason` остаётся стандартным объяснением метрики,
  для определения фактически использованной версии смотрите manifest.

Обе оценки лежат между 0 и 1, больше — лучше. `success` сравнивает score с 0.7.
В `system_one` reason описывает ответы Jev и их вероятности, а не развёрнутую
сгенерированную аргументацию. Score не равен вероятности корректности агента.
Если для answerable-вопроса поиск вернул пустой контекст, Answer Relevancy
оценивается, а Faithfulness пропускается с явным ID в
`faithfulness_skipped_no_context`. Такой прогон завершается с кодом 1, как и
провал порога: пропуск не считается успехом. Ошибка Jev останавливает прогон
и не запускает другую модель; собранные `test_cases.json` сохраняются.

Для сравнения RAG до/после соберите **новые ответы** на тех же вопросах при
фиксированных agent/embedding/Jev моделях и пороге. Сравнивайте кейсы и их
контексты, а не только средний балл. Повторная оценка старого файла проверяет
судью на тех же ответах и не измеряет изменения агента. Для воспроизводимого
**baseline используйте конкретную версию Jev вместо изменяемого `jev-latest`.**

Для повседневных проверок можно оставлять `jev-latest`: фактически возвращённые
модели будут в `judge.response_models`. Если версии в двух прогонах различаются,
переоцените оба сохранённых набора ответов одной версией судьи.

## Локальные проверки без внешних моделей

После назначения `DATABASE_URL` и `TEST_DATABASE_URL` одной временной базе:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -p pytest_asyncio.plugin -q \
  tests/unit/test_evaluation_runner.py tests/integration/test_rag_evaluation.py
```

В тестах работают настоящие метрики DeepEval, но ответы Jev и агента подменяются.
Это проверка подключения, приватности и сбора контекста; качество моделей она
не измеряет. Пример подготовки временной БД — в `docs/DEVELOPMENT.md`.

Документация: [Answer Relevancy](https://deepeval.com/docs/metrics-answer-relevancy),
[Faithfulness](https://deepeval.com/docs/metrics-faithfulness),
[Jev](https://deepeval.com/integrations/models/typesafe-ai).
Состав typed-вопросов и формулу score определяют сами метрики DeepEval;
собственных prompt-ов или HTTP-адаптеров для TypeSafe в проекте нет.
