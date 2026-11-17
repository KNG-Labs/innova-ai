# RAG evaluation: DeepEval + Jev

Один runner: `python -m evals.run`. Пять встроенных метрик DeepEval 4.3.3:

- **Answer Relevancy**: отвечает ли текст на вопрос пользователя.
- **Faithfulness**: подтверждаются ли утверждения ответа найденным контекстом.
- **Contextual Relevancy**: насколько найденный контекст относится к вопросу.
- **Contextual Precision**: стоят ли полезные фрагменты раньше бесполезных.
- **Contextual Recall**: содержит ли найденный контекст факты эталонного ответа.

Все используют `eval_mode="system_one"`: Jev оценивает ответ или контекст без
LLM-судьи и без fallback на LLM. Сам агент по-прежнему использует свою LLM,
а поиск — embedding-модель. Оценка Jev также расходует API-бюджет.
Порог всех метрик — `0.7` (`THRESHOLD` в `run.py`), стартовое значение,
которое ещё нужно проверить на ручной разметке. Это не измеренная гарантия качества.

## Создать новый датасет

Прежние синтетические datasets `generation`, `retrieval`, `business` и их corpus
manifest удалены. Новые goldens создаёт скрипт `python -m evals.generate`;
его нужно запустить самостоятельно перед оценкой. Команды ниже выполняются из
корня репозитория. Первый набор уже содержит 100 goldens; повторная генерация
нужна только для нового набора.

Источник — JSON-массив документов `title`/`content` из `docs/RAG/Agent_memory.txt`.
Скрипт использует `generate_goldens_from_contexts` из гайда DeepEval: каждый
документ становится отдельным контекстом, нарезанным существующим `chunk_text`
(800 символов, overlap 120). Это сохраняет нарезку приложения и не требует
embeddings, PostgreSQL, Docker или TypeSafe. Контакты маскируются существующим
PII-фильтром перед передачей модели и сохранением результата; ошибка анализа
останавливает выполнение. `evals/__init__.py` отключает автоматическую загрузку
env и отправку в Confident AI; существующий `.env` передаётся явно через uv.

Для генерации используется встроенный `OpenRouterModel`: нужны
`OPENROUTER_API_KEY`; `--model` переопределяет модель, указанную в генераторе.
Модель генерации также проверяет качество исходных вопросов. Сначала небольшой
прогон: до 3 goldens по первым трём документам, один шаг Evolution на вопрос:

```bash
uv sync --frozen
uv run --env-file .env python -m evals.generate \
  --limit-contexts 3 --max-goldens-per-context 1 --num-evolutions 1 \
  --output evals/datasets/preview.json
```

После просмотра результата — генерация по всему корпусу:

```bash
uv run --env-file .env python -m evals.generate
```

По умолчанию: до 2 goldens на документ (до 100 для текущих 50 документов),
2 шага Evolution, файл `evals/datasets/generation/golden.dataset.json`.
Все записи получают уникальные `name`, `split="test"`, `answerable=true` для
совместимости с текущим runner. Автоматического разбиения на calibration/test
нет. `test` и `calibration` — назначение примеров, а не разные форматы эталона.
Для первого baseline можно использовать весь набор как `test`. Когда начнёте
подбирать настройки, используйте calibration-часть для подбора, а отложенный
test — для проверки уже выбранных настроек. Оба вида примеров содержат эталоны.
Существующий выходной файл не перезаписывается: для нового прогона укажите другой
`--output`.

Более сложный набор, другая модель и больше примеров на документ:

```bash
uv run --env-file .env python -m evals.generate \
  --model openai/gpt-4.1 --num-evolutions 3 --max-goldens-per-context 3 \
  --output evals/datasets/hard.json
```

`--model` принимает ID модели OpenRouter; модель должна уметь выдавать JSON.
Это отдельные платные LLM-вызовы. Число goldens — верхняя граница, а не число
API-вызовов: генерация, проверки, исправления, эволюции и эталонные ответы
вызывают модель отдельно.

В `EVOLUTIONS` в `evals/generate.py` задано распределение:

| Evolution | Вероятность выбора на шаге |
| --- | --- |
| Reasoning | 25% |
| Multicontext | 20% |
| Constrained | 15% |
| Comparative | 15% |
| Hypothetical | 10% |
| Concretizing | 10% |
| In-breadth | 5% |

`--num-evolutions 0` отключает усложнение. Распределение задаёт вероятности,
поэтому фактические доли будут отличаться. Multicontext использует фрагменты
внутри переданного контекста; скрипт не объединяет разные документы.

JSON сохраняет `input`, полноценный `expected_output`, исходный `context`,
источник, `additional_metadata.evolutions`, `synthetic_input_quality`, модель
генерации и хеш корпуса. Используется `Golden.model_dump`, поскольку `save_as`
в DeepEval 4.3.3 теряет `name` и additional metadata. `context` — источник
синтеза; фактический `retrieval_context` runner соберёт отдельно при оценке.

Проверьте вопросы и эталонные ответы вручную: quality score не гарантирует
корректности после Evolution. При генерации из готовых contexts DeepEval не
выполняет отбор контекстов из документов, поэтому `context_quality` может быть
`null`. Результат — single-turn QA goldens; Evolution не создаёт диалоги,
бизнес-ожидания, relevance labels или отдельный набор вопросов без ответа.
Contextual Precision/Recall используют `expected_output`; исходный `context`
служит для проверки разметки и не передаётся поиску как готовый ответ.

API: [Generate From Contexts](https://deepeval.com/docs/synthesizer-generate-from-contexts),
[EvolutionConfig](https://deepeval.com/docs/golden-synthesizer#evolution-complexity),
[OpenRouterModel](https://deepeval.com/integrations/models/openrouter).

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
**Корпус временной базы заменяется содержимым `docs/RAG/Agent_memory.txt`**.

Runner вызывает обычный `AgentService` и сохраняет итоговый ответ с фрагментами,
которые вернул поиск именно в этом вызове. Повторного поиска для оценки нет.
**Контакты перед записью отчёта и отправкой Jev маскируются существующим PII-фильтром;**
ошибка анализа останавливает оценку. Этот фильтр не является универсальным
детектором любых секретов: используйте только подготовленные тестовые данные.

По умолчанию `--split test --limit 5`. Для набора до 100 goldens:

```bash
docker compose -f docker-compose.eval.yml run --rm eval-runner --limit 100
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
`expected_output` — эталон, `actual_output` — ответ, `retrieval_context` —
использованные фрагменты в порядке выдачи поиска.
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
Старые predictions без `expected_output` нужно собрать заново или дополнить
проверенными эталонами по ID. Runner отклоняет такой файл до вызова Jev,
поскольку Contextual Precision/Recall требуют эталонный ответ.

## Как читать результат

- `test_cases.json`: вопросы, эталоны, ответы и фактический контекст после маскирования контактов.
- `results.json`: результаты пяти встроенных метрик, scores, success и reasons.
- `answer_relevancy/`, `faithfulness/`, `contextual_relevancy/`,
  `contextual_precision/`, `contextual_recall/`: стандартные JSON-отчёты DeepEval.
- `manifest.json`: модели, параметры, порог и хеши входных данных. После оценки
  блок `judge` содержит `requested_model` (например, `jev-latest`),
  `response_models` (имена из ответов TypeSafe), версии DeepEval и TypeSafe SDK.
  Если алиас переключился в середине прогона, список покажет несколько моделей.
  При ошибке вызова Jev этот блок тоже сохраняется; пустой список означает, что ни один
  ответ модели ещё не был получен. При `--collect-only` судья не вызывается
  и блока `judge` нет. `reason` остаётся стандартным объяснением метрики,
  для определения фактически использованной версии смотрите manifest.

Все оценки лежат между 0 и 1, больше — лучше. `success` сравнивает score с 0.7.
В `system_one` reason описывает ответы Jev и их вероятности, а не развёрнутую
сгенерированную аргументацию. Score не равен вероятности корректности агента.
Если для answerable-вопроса поиск вернул пустой контекст, Answer Relevancy
оценивается, а Faithfulness и три retrieval-метрики пропускаются с явными ID в
`faithfulness_skipped_no_context` и `retrieval_metrics_skipped_no_context`.
Такой прогон завершается с кодом 1, как и
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
  tests/unit/test_golden_generation.py tests/unit/test_evaluation_runner.py \
  tests/integration/test_rag_evaluation.py
```

В тесте генерации Synthesizer и OpenRouterModel подменены; внешних вызовов нет.
В остальных тестах работают настоящие метрики DeepEval, но ответы Jev и агента подменяются.
Это проверка подключения, приватности и сбора контекста; качество моделей она
не измеряет. Пример подготовки временной БД — в `docs/DEVELOPMENT.md`.

Документация: [Answer Relevancy](https://deepeval.com/docs/metrics-answer-relevancy),
[Faithfulness](https://deepeval.com/docs/metrics-faithfulness),
[Contextual Relevancy](https://deepeval.com/docs/metrics-contextual-relevancy),
[Contextual Precision](https://deepeval.com/docs/metrics-contextual-precision),
[Contextual Recall](https://deepeval.com/docs/metrics-contextual-recall),
[Jev](https://deepeval.com/integrations/models/typesafe-ai).
Состав typed-вопросов и формулу score определяют сами метрики DeepEval;
собственных prompt-ов или HTTP-адаптеров для TypeSafe в проекте нет.
