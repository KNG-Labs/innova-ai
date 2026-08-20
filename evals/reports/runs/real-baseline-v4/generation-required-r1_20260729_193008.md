# 🚀 DeepEval Evaluation Results

## ❌ FAIL - gen_test_hours_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** По какому номеру позвонить в отдел продаж?
- **Actual Output:** Точный номер отдела продаж в доступных данных скрыт. Отдел продаж работает ежедневно с 9:00 до 21:00, клиентов принимает до 20:30.
- **Expected Output:** +7 (999)777-88-01

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **required_fact_coverage** | 0.00 | 1.00 | 0: В ответе прямо указано, что точный номер отдела продаж скрыт; требуемый номер телефона [PHONE_1] не приведён. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_test_hours_02

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Как записаться на визит в салон?
- **Actual Output:** Записаться на визит можно по телефону отдела продаж, через сайт или мобильное приложение салона. Автосалон работает ежедневно с 9:00 до 21:00, отдел продаж принимает клиентов до 20:30.
- **Expected Output:** по телефону; через сайт; мобильное приложение

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: В ответе прямо указано, что записаться на визит можно по телефону отдела продаж.; 1: В ответе прямо указано, что записаться на визит можно через сайт.; 2: В ответе прямо указано, что записаться на визит можно через мобильное приложение салона. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_test_drive_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Нужно ли платить за пробную поездку?
- **Actual Output:** Нет, тест-драйв предоставляется бесплатно.
- **Expected Output:** бесплатно

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: Ответ прямо сообщает, что тест-драйв предоставляется бесплатно. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_test_credit_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Что принести для оформления машины в кредит?
- **Actual Output:** Для оформления автокредита понадобятся паспорт и второй документ: СНИЛС, водительское удостоверение или загранпаспорт.
- **Expected Output:** паспорт; второй документ

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: В ответе прямо указан паспорт.; 1: В ответе прямо указан второй документ, с примерами: СНИЛС, водительское удостоверение или загранпаспорт. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ❌ FAIL - gen_test_credit_02

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Хочу платить за машину ежемесячно несколько лет
- **Actual Output:** Точной информации об оплате автомобиля ежемесячно в течение нескольких лет нет. Хотите, чтобы я помог подобрать или оформить автомобиль для покупки?
- **Expected Output:** автокредит; от 1 до 7 лет

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **required_fact_coverage** | 0.00 | 1.00 | 0: В ответе не упоминается автокредит и не подтверждается возможность покупки автомобиля в кредит.; 1: Диапазон срока от 1 до 7 лет в ответе не указан и не подтверждён. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_test_installment_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Чем ваша рассрочка отличается от кредита?
- **Actual Output:** Рассрочка от автосалона не предоставляется. Покупку с ежемесячными платежами можно оформить через автокредит банка-партнёра: банк отдельно определяет ставку, первоначальный взнос и срок. Рекламные условия «без процентов» не гарантируют автоматического одобрения и требуют расчёта по конкретной программе.
- **Expected Output:** рассрочка от автосалона не предоставляется; кредит банка-партнёра

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: В ответе прямо сказано, что рассрочка от автосалона не предоставляется.; 1: В ответе прямо указано, что покупку можно оформить через автокредит банка-партнёра. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_test_tradein_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Сколько времени занимает оценка старого авто?
- **Actual Output:** Оценка автомобиля по программе Trade-in занимает в среднем 30–40 минут.
- **Expected Output:** 30–40 минут

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: Ответ прямо указывает, что оценка по программе Trade-in занимает 30–40 минут. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_test_buyout_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Купите мою машину без обмена на новую?
- **Actual Output:** Да, автосалон может выкупить ваш автомобиль без обязательной покупки другой машины. Процедура включает осмотр, диагностику и проверку VIN и документов. Предложение о выкупе действует один рабочий день, а деньги переводятся вам, а не засчитываются в стоимость нового автомобиля.
- **Expected Output:** да; без обязательной покупки

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: Ответ прямо подтверждает: «Да, автосалон может выкупить ваш автомобиль».; 1: Ответ прямо указывает, что выкуп возможен «без обязательной покупки другой машины». |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ❌ FAIL - gen_test_used_warranty_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Покрывается ли гарантией подержанный автомобиль?
- **Actual Output:** Точной информации о гарантии на подержанные автомобили у меня нет. Для новых автомобилей действует заводская гарантия производителя, условия указаны в сервисной книжке конкретной марки.
- **Expected Output:** для части автомобилей; 12 месяцев или 20 000 км

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **required_fact_coverage** | 0.50 | 1.00 | 0: Ответ указывает, что заводская гарантия действует для новых автомобилей, то есть для части автомобилей.; 1: Срок и лимит пробега — 12 месяцев или 20 000 км — в ответе не указаны. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ❌ FAIL - gen_test_inventory_order_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** BMW X3 уже есть на площадке или её надо ждать?
- **Actual Output:** По BMW X3 точная информация о текущем наличии на площадке не указана. В базе модель представлена под заказ — цена от 6 800 000 рублей. Хотите, помогу оформить BMW X3 для покупки?
- **Expected Output:** под заказ; 30–90 дней

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **required_fact_coverage** | 0.50 | 1.00 | 0: В ответе прямо указано, что BMW X3 представлена под заказ.; 1: Срок поставки 30–90 дней в ответе не указан. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_test_inventory_alt_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Не предлагайте Тойоту. Есть Kia или Hyundai?
- **Actual Output:** Да, есть Kia и Hyundai:

В наличии:
  • Kia Rio — практичный компактный седан или хэтчбек.
  • Hyundai Creta — компактный кроссовер с передним или полным приводом.

Под заказ:
  • Kia Sportage — семейный пятиместный кроссовер.
  • Hyundai Tucson — среднеразмерный кроссовер.
- **Expected Output:** Kia Rio; Hyundai Creta

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: В ответе явно указано, что в наличии есть Kia Rio.; 1: В ответе явно указано, что в наличии есть Hyundai Creta. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_test_booking_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Когда бронь начинает действовать?
- **Actual Output:** Бронь становится активной после подписания соглашения и поступления обеспечительного платежа.
- **Expected Output:** после подписания соглашения; после поступления платежа

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: Ответ прямо указывает, что бронь становится активной после подписания соглашения.; 1: Ответ указывает на активацию брони после поступления обеспечительного платежа, то есть платежа. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_test_cancel_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Через сколько банк вернёт платёж за отменённую бронь?
- **Actual Output:** Заявление на возврат обеспечительного платежа рассматривается в течение 3 рабочих дней. Зачисление зависит от банка и обычно занимает от 3 до 10 рабочих дней.
- **Expected Output:** от 3 до 10 рабочих дней

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: В ответе прямо указано, что зачисление обычно занимает от 3 до 10 рабочих дней. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_test_payment_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Почему большая оплата картой может не пройти?
- **Actual Output:** Большой платёж картой может не пройти из-за дневного лимита, установленного вашим банком. Точный лимит лучше уточнить в банке.
- **Expected Output:** дневной лимит банка

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: Ответ прямо указывает на дневной лимит, установленный банком. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_test_leasing_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Я ИП, могу взять несколько машин в лизинг?
- **Actual Output:** Да, для ИП доступны лизинг и покупка партий автомобилей. Корпоративный отдел подготовит индивидуальное предложение по сроку договора, авансу, графику платежей и выкупной стоимости. Для расчёта потребуются реквизиты компании, желаемое количество машин и предполагаемый пробег.
- **Expected Output:** индивидуальные предприниматели; лизинг; партии автомобилей

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: В ответе прямо указано: «для ИП доступны», что означает индивидуальных предпринимателей.; 1: В ответе прямо указано, что доступны лизинг.; 2: В ответе прямо указано: «покупка партий автомобилей». |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_test_osago_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** От чего зависит цена ОСАГО?
- **Actual Output:** Стоимость ОСАГО зависит от региона, мощности двигателя, стажа и возраста водителя, а также количества допущенных водителей. Полис можно оформить в автосалоне перед выдачей автомобиля.
- **Expected Output:** регион; мощность двигателя; стаж; возраст

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: В ответе прямо указано, что стоимость ОСАГО зависит от региона.; 1: В ответе прямо указано, что стоимость ОСАГО зависит от мощности двигателя.; 2: В ответе прямо указано, что стоимость ОСАГО зависит от стажа водителя.; 3: В ответе прямо указано, что стоимость ОСАГО зависит от возраста водителя. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_test_kasko_credit_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Обязательно ли КАСКО при покупке в кредит?
- **Actual Output:** Не всегда. При некоторых кредитных программах банк может требовать полис КАСКО — это зависит от условий конкретного банка.
- **Expected Output:** зависит от банка и программы

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: Ответ прямо указывает, что требование зависит от условий конкретного банка и от кредитной программы. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_test_service_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Как записаться на замену масла?
- **Actual Output:** Записаться на замену масла можно по телефону сервиса, через сайт или мобильное приложение.
- **Expected Output:** по телефону сервиса; через сайт; приложение

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: В ответе прямо указано: «по телефону сервиса».; 1: В ответе прямо указано: «через сайт».; 2: В ответе указано «через ... мобильное приложение», что подтверждает возможность записи через приложение. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_test_warranty_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Заводская гарантия оплатит ремонт после аварии?
- **Actual Output:** Нет. Заводская гарантия не покрывает повреждения и ремонт после ДТП. Она распространяется на дефекты материалов и сборки; точный срок и пробег указаны в сервисной книжке марки.
- **Expected Output:** не покрывает повреждения в ДТП

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: Ответ прямо сообщает, что заводская гарантия не покрывает повреждения и ремонт после ДТП. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_test_delivery_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Доставляете машину в другой город?
- **Actual Output:** Да, доставляем. После полной оплаты автомобиль можно отправить эвакуатором или автовозом. Для другого населённого пункта стоимость рассчитывается по расстоянию, а дату и интервал согласовывают после готовности машины к выдаче.
- **Expected Output:** стоимость рассчитывается по расстоянию

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: В ответе прямо указано, что для другого населённого пункта стоимость рассчитывается по расстоянию. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_test_remote_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Можно посмотреть машину по видео и оформить договор удалённо?
- **Actual Output:** Да, можно выбрать модель, получить видеообзор и согласовать договор дистанционно. Для идентификации может потребоваться видеосвязь или усиленная электронная подпись. Выдача автомобиля проходит в салоне или через платную доставку после полной оплаты и подписания документов.
- **Expected Output:** видеообзор; согласовать договор дистанционно

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: В ответе прямо указано, что можно получить видеообзор.; 1: В ответе прямо указано, что можно согласовать договор дистанционно. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_test_registration_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Нужен ли полис для регистрации автомобиля?
- **Actual Output:** Да, для постановки автомобиля на учёт обычно нужен полис ОСАГО. Также потребуются паспорт владельца, договор купли-продажи, ЭПТС и квитанция об оплате госпошлины.
- **Expected Output:** ОСАГО

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: В ответе прямо указано, что для постановки автомобиля на учёт обычно нужен полис ОСАГО. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_test_sportage_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Какой объём багажника у Kia Sportage?
- **Actual Output:** Объём багажника Kia Sportage — около 540 литров.
- **Expected Output:** около 540 литров

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: В ответе прямо указано, что объём багажника составляет около 540 литров. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_test_tucson_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Бывает Hyundai Tucson гибридным?
- **Actual Output:** Да, Hyundai Tucson бывает с гибридной силовой установкой на отдельных рынках. Также доступны бензиновые версии 2,0 и 2,5 л. Хотите, чтобы я помог подобрать или оформить Tucson для покупки?
- **Expected Output:** гибридная силовая установка; на отдельных рынках

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: В ответе прямо указано, что Hyundai Tucson бывает с гибридной силовой установкой.; 1: В ответе прямо уточняется, что это доступно на отдельных рынках. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_reg_time_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Время
- **Actual Output:** Автосалон работает ежедневно с 9:00 до 21:00. Отдел продаж принимает клиентов до 20:30, сервисный центр — с 8:00 до 20:00, в воскресенье с 9:00 до 18:00.
- **Expected Output:** 9:00; 21:00

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: В ответе указано, что автосалон работает ежедневно с 9:00 до 21:00.; 1: В ответе явно указано время окончания работы автосалона — 21:00. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_reg_hours_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Часы
- **Actual Output:** Автосалон работает ежедневно с 9:00 до 21:00. Отдел продаж принимает клиентов до 20:30, сервисный центр — с 8:00 до 20:00, в воскресенье с 9:00 до 18:00.
- **Expected Output:** 9:00; 21:00

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: В ответе указано, что автосалон работает ежедневно с 9:00.; 1: В ответе указано, что автосалон работает до 21:00. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ❌ FAIL - gen_reg_brands_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Какие марки есть?
- **Actual Output:** Точной информации о доступных марках в базе знаний нет.
- **Expected Output:** Tesla; Kia; Toyota; Hyundai

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **required_fact_coverage** | 0.00 | 1.00 | 0: Ответ не подтверждает доступность марки Tesla.; 1: Ответ не подтверждает доступность марки Kia.; 2: Ответ не подтверждает доступность марки Toyota.; 3: Ответ не подтверждает доступность марки Hyundai. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ❌ FAIL - gen_reg_not_toyota_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Хочу другую, не Toyota
- **Actual Output:** Понял, Toyota не рассматриваем. Точной информации по другим моделям сейчас нет. Какая марка или модель вас интересует?
- **Expected Output:** Tesla Model Y; Kia Rio; Hyundai Creta

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **required_fact_coverage** | 0.00 | 1.00 | 0: В ответе Tesla Model Y не упоминается и информация о ней не предоставляется.; 1: В ответе Kia Rio не упоминается и информация о ней не предоставляется.; 2: В ответе Hyundai Creta не упоминается и информация о ней не предоставляется. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_reg_credit_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Можно купить автомобиль в кредит?
- **Actual Output:** Да, автокредит можно оформить прямо в автосалоне через банки-партнёры. Первоначальный взнос — от 10%, срок кредита — от 1 до 7 лет, решение обычно принимается за 30–60 минут. Для оформления нужны паспорт и второй документ.
- **Expected Output:** можно оформить на месте; банки-партнёры

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: В ответе прямо сказано, что автокредит можно оформить прямо в автосалоне, то есть на месте.; 1: В ответе прямо указано оформление через банки-партнёры. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_reg_tradein_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** У вас есть trade-in?
- **Actual Output:** Да, у нас действует программа Trade-in: ваш автомобиль принимается в зачёт стоимости нового. Оценка бесплатная и занимает в среднем 30–40 минут; нужны ПТС или ЭПТС, СТС и паспорт собственника.
- **Expected Output:** автомобиль в зачёт стоимости нового

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: В ответе прямо сказано, что автомобиль принимается в зачёт стоимости нового. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_reg_close_time_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** До скольки вы работаете?
- **Actual Output:** Автосалон работает ежедневно с 9:00 до 21:00. Отдел продаж принимает клиентов до 20:30.
- **Expected Output:** 21:00

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: Ответ прямо указывает, что автосалон работает до 21:00. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_reg_inventory_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Какие автомобили сейчас в наличии?
- **Actual Output:** Сейчас в наличии:

  • Tesla Model Y — электрический кроссовер с запасом хода до 500–530 км
  • Kia Rio — компактный седан или хэтчбек
  • Toyota Land Cruiser Prado — рамный полноприводный внедорожник на 5 или 7 мест
  • Hyundai Creta — компактный кроссовер с передним или полным приводом
  • Toyota Camry — седан бизнес-класса с бензиновой и гибридной версиями

Наличие конкретного цвета и комплектации нужно проверять перед бронированием.
- **Expected Output:** Tesla Model Y; Kia Rio; Toyota Land Cruiser Prado; Hyundai Creta; Toyota Camry

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: Tesla Model Y прямо указана в списке автомобилей в наличии.; 1: Kia Rio прямо указана в списке автомобилей в наличии.; 2: Toyota Land Cruiser Prado прямо указана в списке автомобилей в наличии.; 3: Hyundai Creta прямо указана в списке автомобилей в наличии.; 4: Toyota Camry прямо указана в списке автомобилей в наличии. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_reg_credit_downpayment_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Какой взнос нужен для кредита?
- **Actual Output:** Минимальный первоначальный взнос по автокредиту — от 10% стоимости автомобиля.
- **Expected Output:** от 10%

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: В ответе прямо указано: «от 10% стоимости автомобиля», что подтверждает требование «от 10%». |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_reg_tradein_oldcar_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Хочу сдать старую машину в зачёт новой
- **Actual Output:** По программе Trade-in старый автомобиль принимается в зачёт стоимости нового. Бесплатная оценка занимает в среднем 30–40 минут; нужны ПТС или ЭПТС, СТС и паспорт собственника. Хотите, чтобы я помог с подбором и оформлением нового автомобиля в Trade-in?
- **Expected Output:** trade-in; бесплатная оценка

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: Ответ прямо упоминает программу Trade-in и описывает приём старого автомобиля в зачёт стоимости нового.; 1: Ответ прямо сообщает, что оценка бесплатная. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_reference_hours_001

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Когда работает отдел продаж?
- **Actual Output:** Отдел продаж работает ежедневно с 9:00 до 21:00 и принимает клиентов до 20:30.
- **Expected Output:** 20:30

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: В ответе прямо указано, что клиентов принимают до 20:30. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_reference_camry_trunk_001

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Какой объём багажника у Camry?
- **Actual Output:** Объём багажника Toyota Camry — около 493 литров.
- **Expected Output:** 493 литров

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: В ответе прямо указано, что объём багажника составляет около 493 литров. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_reference_camry_price_001

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Назовите диапазон цен на Toyota Camry.
- **Actual Output:** Стоимость Toyota Camry — от 2 800 000 до 4 200 000 рублей в зависимости от комплектации и типа двигателя.
- **Expected Output:** 2 800 000; 4 200 000

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: В ответе прямо указана минимальная стоимость 2 800 000 рублей.; 1: В ответе прямо указана максимальная стоимость 4 200 000 рублей. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ❌ FAIL - gen_reference_availability_001

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Гарантируете, что синяя Camry сейчас свободна?
- **Actual Output:** Точной информации о наличии синей Toyota Camry сейчас нет, поэтому гарантировать это не могу. Хотите, чтобы я помог подобрать или оформить Camry для покупки?
- **Expected Output:** наличие цвета и комплектации нужно проверить || цвет и комплектацию нужно проверить; может измениться в течение дня

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **required_fact_coverage** | 0.00 | 1.00 | 0: Ответ сообщает об отсутствии точной информации о наличии синей Camry, но не упоминает необходимость проверить комплектацию.; 1: В ответе не сказано, что наличие может измениться в течение дня. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_reference_credit_001

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Сколько рассматривают заявку на автокредит?
- **Actual Output:** Заявку на автокредит рассматривают в течение 30–60 минут.
- **Expected Output:** 30–60 минут || 30-60 минут

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: В ответе прямо указано, что заявку на автокредит рассматривают в течение 30–60 минут, что соответствует требуемому сроку. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - gen_reference_tradein_001

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Какие документы нужны для оценки trade-in?
- **Actual Output:** Для оценки автомобиля в Trade-in понадобятся ПТС или ЭПТС, СТС и паспорт собственника. Оценка бесплатная и занимает в среднем 30–40 минут.
- **Expected Output:** ПТС || ЭПТС; СТС; паспорт собственника

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **required_fact_coverage** | 1.00 | 1.00 | 0: В ответе прямо указаны ПТС или ЭПТС.; 1: В ответе прямо указан СТС.; 2: В ответе прямо указан паспорт собственника. |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## Aggregate Metrics

| Metric | Average Score | Pass Rate | Total |
|:---|:---:|:---:|:---:|
| **required_fact_coverage** | 0.85 | 82.50% | passed=33 | failed=7 | 40 |
| **_case_collected** | 1.00 | 100.00% | passed=40 | failed=0 | 40 |

---
