# Оценка качества RAG

Используются пять встроенных метрик DeepEval 4.3.3:
`AnswerRelevancyMetric`, `FaithfulnessMetric`, `ContextualRelevancyMetric`,
`ContextualPrecisionMetric` и `ContextualRecallMetric`. Судья — Jev через
`eval_mode="system_one"`, без LLM-судьи и fallback на LLM.

Runner `python -m evals.run` собирает реальные ответы `AgentService` и использованный
ими контекст в изолированной временной PostgreSQL-базе `_eval`/`_test`.
Сохранённые ответы можно повторно оценивать без вызовов агента и embeddings.
Прежние синтетические датасеты удалены. Для создания новых single-turn goldens
из `docs/RAG/Agent_memory.txt` подготовлен `python -m evals.generate` с DeepEval
Synthesizer и EvolutionConfig. Генерация запускается вручную через OpenRouter;
скрипт сохраняет эталонные ответы, контекст и metadata в JSON для runner.
Первый набор содержит 100 single-turn goldens. Один набор используется для
проверки поиска и ответа: `expected_output` служит эталоном для Contextual
Precision/Recall, а `retrieval_context` собирается из фактической выдачи поиска.
Исходный `golden.context` не подставляется вместо результатов поиска.
Отказы, бизнес-состояния и multi-turn диалоги этими метриками не оцениваются.

Генерация датасета, пошаговый запуск оценки и разбор отчётов:
[evals/README.md](../evals/README.md).
