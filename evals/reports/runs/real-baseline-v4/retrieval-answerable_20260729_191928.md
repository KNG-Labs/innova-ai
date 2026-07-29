# 🚀 DeepEval Evaluation Results

## ✅ PASS - ret_test_hours_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** По какому номеру позвонить в отдел продаж?
- **Actual Output:** ["dealer_hours"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **retrieval_recall@10** | 1.00 | 1.00 | Найдено 1/1 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - ret_test_hours_02

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Как записаться на визит в салон?
- **Actual Output:** ["dealer_hours"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **retrieval_recall@10** | 1.00 | 1.00 | Найдено 1/1 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - ret_test_drive_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Нужно ли платить за пробную поездку?
- **Actual Output:** ["test_drive"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **retrieval_recall@10** | 1.00 | 1.00 | Найдено 1/1 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ❌ FAIL - ret_test_credit_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Что принести для оформления машины в кредит?
- **Actual Output:** ["credit_financing"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **retrieval_recall@10** | 0.50 | 1.00 | Найдено 1/2 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ❌ FAIL - ret_test_credit_02

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Хочу платить за машину ежемесячно несколько лет
- **Actual Output:** ["payment_methods"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **retrieval_recall@10** | 0.00 | 1.00 | Найдено 0/2 |
| ❌ | **retrieval_mrr@10** | 0.00 | 1.00 | Релевантный документ не найден |
| ❌ | **context_precision@10** | 0.00 | 1.00 | Релевантно 0/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ❌ FAIL - ret_test_installment_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Чем ваша рассрочка отличается от кредита?
- **Actual Output:** ["installment"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **retrieval_recall@10** | 0.50 | 1.00 | Найдено 1/2 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ❌ FAIL - ret_test_tradein_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Сколько времени занимает оценка старого авто?
- **Actual Output:** ["trade_in_program"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **retrieval_recall@10** | 0.50 | 1.00 | Найдено 1/2 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ❌ FAIL - ret_test_buyout_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Купите мою машину без обмена на новую?
- **Actual Output:** ["vehicle_buyout"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **retrieval_recall@10** | 0.50 | 1.00 | Найдено 1/2 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ❌ FAIL - ret_test_used_warranty_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Покрывается ли гарантией подержанный автомобиль?
- **Actual Output:** ["new_vehicle_warranty"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **retrieval_recall@10** | 0.00 | 1.00 | Найдено 0/2 |
| ❌ | **retrieval_mrr@10** | 0.00 | 1.00 | Релевантный документ не найден |
| ❌ | **context_precision@10** | 0.00 | 1.00 | Релевантно 0/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ❌ FAIL - ret_test_inventory_order_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** BMW X3 уже есть на площадке или её надо ждать?
- **Actual Output:** ["bmw_x3"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **retrieval_recall@10** | 0.33 | 1.00 | Найдено 1/3 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ❌ FAIL - ret_test_inventory_alt_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Не предлагайте Тойоту. Есть Kia или Hyundai?
- **Actual Output:** ["vehicle_inventory"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **retrieval_recall@10** | 0.33 | 1.00 | Найдено 1/3 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - ret_test_booking_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Когда бронь начинает действовать?
- **Actual Output:** ["vehicle_booking"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **retrieval_recall@10** | 1.00 | 1.00 | Найдено 1/1 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - ret_test_cancel_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Через сколько банк вернёт платёж за отменённую бронь?
- **Actual Output:** ["booking_cancellation"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **retrieval_recall@10** | 1.00 | 1.00 | Найдено 1/1 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - ret_test_payment_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Почему большая оплата картой может не пройти?
- **Actual Output:** ["payment_methods"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **retrieval_recall@10** | 1.00 | 1.00 | Найдено 1/1 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - ret_test_leasing_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Я ИП, могу взять несколько машин в лизинг?
- **Actual Output:** ["corporate_leasing"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **retrieval_recall@10** | 1.00 | 1.00 | Найдено 1/1 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - ret_test_osago_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** От чего зависит цена ОСАГО?
- **Actual Output:** ["osago_insurance"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **retrieval_recall@10** | 1.00 | 1.00 | Найдено 1/1 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ❌ FAIL - ret_test_kasko_credit_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Обязательно ли КАСКО при покупке в кредит?
- **Actual Output:** ["kasko_insurance"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **retrieval_recall@10** | 0.50 | 1.00 | Найдено 1/2 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ❌ FAIL - ret_test_service_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Как записаться на замену масла?
- **Actual Output:** ["maintenance"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **retrieval_recall@10** | 0.50 | 1.00 | Найдено 1/2 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ❌ FAIL - ret_test_warranty_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Заводская гарантия оплатит ремонт после аварии?
- **Actual Output:** ["new_vehicle_warranty"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **retrieval_recall@10** | 0.50 | 1.00 | Найдено 1/2 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - ret_test_delivery_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Доставляете машину в другой город?
- **Actual Output:** ["vehicle_delivery"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **retrieval_recall@10** | 1.00 | 1.00 | Найдено 1/1 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - ret_test_remote_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Можно посмотреть машину по видео и оформить договор удалённо?
- **Actual Output:** ["remote_purchase"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **retrieval_recall@10** | 1.00 | 1.00 | Найдено 1/1 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ❌ FAIL - ret_test_registration_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Нужен ли полис для регистрации автомобиля?
- **Actual Output:** ["vehicle_registration"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **retrieval_recall@10** | 0.50 | 1.00 | Найдено 1/2 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - ret_test_sportage_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Какой объём багажника у Kia Sportage?
- **Actual Output:** ["kia_sportage"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **retrieval_recall@10** | 1.00 | 1.00 | Найдено 1/1 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - ret_test_tucson_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Бывает Hyundai Tucson гибридным?
- **Actual Output:** ["hyundai_tucson"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **retrieval_recall@10** | 1.00 | 1.00 | Найдено 1/1 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - ret_reg_time_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Время
- **Actual Output:** ["dealer_hours"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **retrieval_recall@10** | 1.00 | 1.00 | Найдено 1/1 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - ret_reg_hours_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Часы
- **Actual Output:** ["dealer_hours"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **retrieval_recall@10** | 1.00 | 1.00 | Найдено 1/1 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ❌ FAIL - ret_reg_brands_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Какие марки есть?
- **Actual Output:** ["new_vehicle_warranty"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **retrieval_recall@10** | 0.00 | 1.00 | Найдено 0/1 |
| ❌ | **retrieval_mrr@10** | 0.00 | 1.00 | Релевантный документ не найден |
| ❌ | **context_precision@10** | 0.00 | 1.00 | Релевантно 0/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ❌ FAIL - ret_reg_not_toyota_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Хочу другую, не Toyota
- **Actual Output:** ["toyota_camry"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **retrieval_recall@10** | 0.00 | 1.00 | Найдено 0/4 |
| ❌ | **retrieval_mrr@10** | 0.00 | 1.00 | Релевантный документ не найден |
| ❌ | **context_precision@10** | 0.00 | 1.00 | Релевантно 0/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - ret_reg_credit_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Можно купить автомобиль в кредит?
- **Actual Output:** ["credit_financing"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **retrieval_recall@10** | 1.00 | 1.00 | Найдено 1/1 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - ret_reg_tradein_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** У вас есть trade-in?
- **Actual Output:** ["trade_in_program"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **retrieval_recall@10** | 1.00 | 1.00 | Найдено 1/1 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - ret_reg_close_time_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** До скольки вы работаете?
- **Actual Output:** ["dealer_hours"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **retrieval_recall@10** | 1.00 | 1.00 | Найдено 1/1 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - ret_reg_inventory_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Какие автомобили сейчас в наличии?
- **Actual Output:** ["vehicle_inventory"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **retrieval_recall@10** | 1.00 | 1.00 | Найдено 1/1 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - ret_reg_credit_downpayment_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Какой взнос нужен для кредита?
- **Actual Output:** ["credit_financing"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **retrieval_recall@10** | 1.00 | 1.00 | Найдено 1/1 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - ret_reg_tradein_oldcar_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Хочу сдать старую машину в зачёт новой
- **Actual Output:** ["trade_in_program"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **retrieval_recall@10** | 1.00 | 1.00 | Найдено 1/1 |
| ✅ | **retrieval_mrr@10** | 1.00 | 1.00 | Первый релевантный документ на позиции 1 |
| ✅ | **context_precision@10** | 1.00 | 1.00 | Релевантно 1/1 возвращённых документов |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## Aggregate Metrics

| Metric | Average Score | Pass Rate | Total |
|:---|:---:|:---:|:---:|
| **retrieval_recall@10** | 0.73 | 58.82% | passed=20 | failed=14 | 34 |
| **retrieval_mrr@10** | 0.88 | 88.24% | passed=30 | failed=4 | 34 |
| **context_precision@10** | 0.88 | 88.24% | passed=30 | failed=4 | 34 |
| **_case_collected** | 1.00 | 100.00% | passed=34 | failed=0 | 34 |

---
