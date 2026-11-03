# Проверка демонстрационной страницы

DOM-тесты проверяют карточки, контракт запросов, быстрые ответы, повтор после
ошибки, смену идентификаторов при очистке, поздние ответы, восстановление истории,
клавиатурные события чата и отсутствие дубликатов карточек. Геометрию,
бесконечный цикл и остановку анимации проверяют браузерные тесты.
База данных и запущенный API для них не нужны.

Нужен Node.js 18+. Установите jsdom только во временный каталог:

```bash
npm install --prefix /tmp/innova-demo-tests --no-save --no-audit --no-fund jsdom@26.1.0
NODE_PATH=/tmp/innova-demo-tests/node_modules node --test tests/frontend/demo.test.cjs
```

Страница использует локальные UMD-файлы Embla Carousel + Auto Scroll 8.6.0,
не использует jsdom в runtime и не требует npm или сборки.
Проверку реальной интеграции выполняйте на отдельной временной PostgreSQL-базе
с суффиксом `_test` по инструкции в `docs/DEVELOPMENT.md`.

## Настоящий браузер

`browser.test.cjs` запускает отдельный Chrome через Playwright, проверяет восемь
размеров экрана, покадровую плавность, бесконечный стык, паузу карусели, свайпы, клавиатуру, reduced motion,
клики, API, сброс сессии, ошибки, подсказки и прокрутку истории. Нужны установленный
Google Chrome и API со `stub` LLM на отдельной временной базе `_test`.
Не указывайте рабочий API: тест отправляет сообщения и создаёт сессии.

```bash
npm install --prefix /tmp/innova-demo-tests --no-save --no-audit --no-fund jsdom@26.1.0 playwright@1.64.1
INNOVA_DEMO_LIVE_TEST=1 INNOVA_DEMO_TEST_URL=http://127.0.0.1:8017 \
  NODE_PATH=/tmp/innova-demo-tests/node_modules node --test tests/frontend/browser.test.cjs
```

Скриншоты сохраняются в `/tmp/innova-visual` (переопределяется через
`INNOVA_DEMO_SCREENSHOTS`). Сценарии подсказок и сетевой ошибки используют
контролируемые ответы; отдельный сценарий проверяет настоящий API и историю в БД.
jsdom и Playwright нужны только для тестов.

Проверки интерфейса с контролируемыми ответами можно запускать без API и БД.
Запустите `python3 -m http.server 8023 --bind 127.0.0.1` из корня репозитория,
затем в другом терминале:

```bash
INNOVA_DEMO_TEST_URL=http://127.0.0.1:8023 \
  NODE_PATH=/tmp/innova-demo-tests/node_modules node --test \
  --test-name-pattern='desktop|carousel|reduced|touch|quick' tests/frontend/browser.test.cjs
```
