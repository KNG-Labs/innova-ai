# 🚀 DeepEval Evaluation Results

## ❌ FAIL - ret_test_chery_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Можно оформить у вас ипотеку на квартиру?
- **Actual Output:** ["installment"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **abstention_accuracy@10** | 0.00 | 1.00 | Retrieval вернул контекст |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ❌ FAIL - ret_test_audi_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Можно застраховать через вас квартиру?
- **Actual Output:** ["kasko_insurance"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **abstention_accuracy@10** | 0.00 | 1.00 | Retrieval вернул контекст |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ❌ FAIL - ret_test_mercedes_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Какой сегодня курс евро?
- **Actual Output:** ["price_and_inventory_freshness"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **abstention_accuracy@10** | 0.00 | 1.00 | Retrieval вернул контекст |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ❌ FAIL - ret_test_mazda_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Можно купить у вас велосипед?
- **Actual Output:** ["remote_purchase"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **abstention_accuracy@10** | 0.00 | 1.00 | Retrieval вернул контекст |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ❌ FAIL - ret_test_negative_01

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Посоветуй хороший отель в центре города
- **Actual Output:** ["vehicle_inventory"]

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ❌ | **abstention_accuracy@10** | 0.00 | 1.00 | Retrieval вернул контекст |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## ✅ PASS - ret_test_negative_02

<details><summary><b>View Test Case Data</b></summary>

- **Input:** Как лечить сильную головную боль?
- **Actual Output:** []

</details>

### Metrics

| Status | Metric | Score | Threshold | Reason |
|:---:|:---|:---:|:---:|:---|
| ✅ | **abstention_accuracy@10** | 1.00 | 1.00 | Retrieval воздержался |
| ✅ | **_case_collected** | 1.00 | 1.00 | N/A |

---

## Aggregate Metrics

| Metric | Average Score | Pass Rate | Total |
|:---|:---:|:---:|:---:|
| **abstention_accuracy@10** | 0.17 | 16.67% | passed=1 | failed=5 | 6 |
| **_case_collected** | 1.00 | 100.00% | passed=6 | failed=0 | 6 |

---
