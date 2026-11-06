# Оценка качества RAG

Используются только две встроенные метрики DeepEval 4.3.3:
`AnswerRelevancyMetric` и `FaithfulnessMetric`. Судья — Jev через
`eval_mode="system_one"`, без LLM-судьи и fallback на LLM.

Runner `python -m evals.run` собирает реальные ответы `AgentService` и использованный
ими контекст в изолированной временной PostgreSQL-базе `_eval`/`_test`.
Сохранённые ответы можно повторно оценивать без вызовов агента и embeddings.
Оригинальные датасеты сохранены; для текущих метрик используются answerable-кейсы
набора generation. Retrieval, отказы и бизнес-состояния этими метриками не оцениваются.

Пошаговый запуск, разбор отчётов и результаты статической проверки датасетов:
[evals/README.md](../evals/README.md).
