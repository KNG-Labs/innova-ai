# Оценка качества

Версионируемые наборы в `evals/datasets/` проверяют поиск документов, качество
ответов и сценарии работы с диалогом. Evaluation suite построен на
[DeepEval](https://deepeval.com/): фреймворк хранит golden cases, запускает
метрики для каждого кейса и формирует JSON отчёты и Markdown дашборды.
Результаты прогонов сохраняются в `evals/reports/runs/`.

Для semantic-метрик применяется подход **LLM-as-a-Judge**: отдельная LLM с
temperature `0` получает ответ или полный transcript и возвращает
структурированный verdict. Такой judge оценивает полноту обязательных фактов,
наличие запрещённых утверждений и качество бизнес-диалога там, где сравнения
строк недостаточно. Judge не заменяет детерминированные проверки: retrieval
метрики вычисляются по document ID и relevance labels, а состояние диалога,
intent, недостающие поля, поля лида и контакты дополнительно проверяются
локальными guardrails. В manifest фиксируются модели, хеши dataset и corpus,
RAG-параметры и признак `self_judge`; для основного baseline agent и judge
разделены.

## Baseline от 29 июля 2026 года

Сохранённый прогон:
[real-baseline-v4](../evals/reports/runs/real-baseline-v4).
Он выполнен 29 июля 2026 года на 100 кейсах (`test` и `regression`) с agent
`openai/gpt-5.6-luna`, независимым judge `openai/gpt-5.6-luna-pro` и одним
повтором.

| Метрика |       Результат | n | Направление и смысл                      |
|---|----------------:|---:|------------------------------------------|
| `retrieval_recall@10` | 0.7255 (72.55%) | 34 | доля найденных релевантных документов    |
| `retrieval_mrr@10` | 0.8824 (88.24%) | 34 | позиция первого релевантного документа   |
| `context_precision@10` | 0.8824 (88.24%) | 34 | точность контекста в top-10              |
| `abstention_accuracy@10` | 0.1667 (16.67%) | 6 |  корректный отказ при отсутствии ответа в базе |
| `required_fact_coverage` |   0.85 (85.00%) | 40 | полнота обязательных фактов, LLM-as-a-Judge |
| `forbidden_claim_rate` |  0.0909 (9.09%) | 44 | доля запрещённых утверждений, LLM-as-a-Judge |
| `business_dialogue_success` | 0.3333 (33.33%) | 12 | semantic verdict и локальные guardrails  |
| `average_agent_token_usage` |            3021 | 60 | среднее число токенов agent на eval-кейс |

Результаты LLM-as-a-Judge зависят от выбранной модели, prompt и набора данных.
Один повтор показывает baseline, но не разброс; для сравнения изменений следует
использовать одинаковые модели и dataset/corpus hashes и запускать несколько
повторов через `--repetitions`.

Проверить структуру наборов без запуска приложения:

```bash
uv run python -m evals.runners.evaluate --dataset evals/datasets
```

Оценку нельзя запускать на рабочей БД: программа принимает только базу с
суффиксом `_eval` или `_test` и заново загружает в неё корпус базы знаний.
Рекомендуемый изолированный запуск:

```bash
EVAL_REPORT_NAME=real-baseline-next \
  docker compose -f docker-compose.eval.yml up --build \
  --abort-on-container-exit --exit-code-from eval-runner eval-runner
docker compose -f docker-compose.eval.yml down
```

Подробности по наборам, метрикам и параметрам runner — в [evals/README.md](../evals/README.md).
