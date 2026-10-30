# API и веб-виджет

После запуска интерактивная OpenAPI-документация доступна по адресу `http://localhost:8000/docs`.

## POST /message

Создаёт или продолжает диалог.

```json
{
  "anonymous_id": "browser-user-1",
  "channel": "website",
  "session_id": null,
  "content": "Хочу купить Toyota Camry до 3 миллионов",
  "page_title": "Toyota Camry в наличии"
}
```

| Поле | Обязательное | Описание |
|---|---:|---|
| `anonymous_id` | да | Стабильный ID, созданный клиентом; от 3 до 128 символов |
| `channel` | нет | `website`, `telegram` или `avito`; по умолчанию `website` |
| `session_id` | нет | UUID существующей активной сессии |
| `content` | да | Сообщение пользователя; от 1 до 4000 символов |
| `page_title` | нет | Нормализованный заголовок страницы; не более 200 символов |

API-схема принимает значения каналов `telegram` и `avito`. В репозитории
реализованы виджет для сайта, прямой вызов API и интеграция с Telegram через long polling;
готовой интеграции с Avito пока нет.

Пример ответа:

```json
{
  "user_id": "0c336b9b-6a7e-4494-8af1-e6302b87956f",
  "session_id": "c75f9b38-b169-4901-a3e1-9335d4d7ff6a",
  "user_message_id": "57c7b362-4b4d-4e5f-8a9b-1c2d3e4f5a6b",
  "assistant_message_id": "bb9ffb5f-d98c-4cc2-bf7e-c6e5dfde4b63",
  "answer": "Какой способ покупки вы рассматриваете?",
  "state": "QUALIFICATION",
  "intent": "lead_request",
  "next_step": "QUALIFICATION",
  "missing_fields": ["purchase_type", "contact"],
  "lead_id": "9f1c0c2a-3b4d-4e5f-8a9b-1c2d3e4f5a6b"
}
```

## Сессии и сообщения

```text
GET /sessions/{session_id}
GET /sessions/{session_id}/messages
```

Первый метод API возвращает состояние и владельца сессии. Второй возвращает
сохранённую историю сообщений в порядке создания.

## Лиды

```text
GET  /leads
GET  /leads?status=ready
GET  /leads/{lead_id}
POST /leads/{lead_id}/deliver
```

`GET /leads` возвращает сокращённые элементы списка. `GET /leads/{lead_id}`
дополнительно содержит квалификацию, контакт, краткое описание, статус доставки
и последнюю ошибку.

`POST /leads/{lead_id}/deliver` синхронно повторяет доставку без Redis. Метод
возвращает `404` для неизвестного лида и `409` для лида в недопустимом статусе,
например `draft`.

## База знаний

```text
GET  /knowledge/documents
POST /knowledge/documents
PUT  /knowledge/documents
POST /knowledge/reindex
```

Документы загружаются вручную JSON-массивом:

```json
[
  {
    "title": "Toyota Camry",
    "source": "manual",
    "content": "Toyota Camry доступна в комплектациях ..."
  }
]
```

`PUT /knowledge/documents` атомарно заменяет весь корпус; пустой массив
возвращает `422`. Документы делятся на чанки и индексируются вместе с заголовком.
Retrieval planner определяет, продолжить прошлый источник, искать по новой теме
или пропустить RAG. В контекст попадают не более двух чанков одного документа.
После смены модели или правил индексирования вызовите `POST /knowledge/reindex`.

## Веб-виджет

Виджет раздаётся через FastAPI:

```html
<script
  src="http://localhost:8000/static/widget.js"
  data-api-base="http://localhost:8000">
</script>
```

Демонстрационная страница:

```text
http://localhost:8000/static/widget-demo.html
```

Виджет хранит `anonymous_id` и ID активной сессии в `localStorage`, передаёт
`document.title` в `page_title` и удаляет `session_id`, когда серверная часть
возвращает `CLOSED`.

Настройка CORS и запуск описаны в [инструкции по разработке](DEVELOPMENT.md).
