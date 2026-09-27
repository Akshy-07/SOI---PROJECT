# Benchmark Evaluation Report (Milestone M7)

Measured on **2026-09-27 15:54:16** across **42** real-world college questions.

---

## 1. Summary of Measured Metrics

| Metric | Target / Benchmark | Measured Result | Status |
| :--- | :--- | :--- | :--- |
| **Routing Accuracy** | ≥ 90% | **88.1%** (37/42) | ⚠️ BELOW TARGET |
| **Retrieval Recall@5** | ≥ 85% | **100.0%** | ✅ PASS |
| **Mean Reciprocal Rank (MRR)** | ≥ 0.80 | **0.6792** | ⚠️ BELOW TARGET |
| **Citation Correctness** | ≥ 90% | **70.0%** | ⚠️ BELOW TARGET |
| **Refusal Recall (Unanswerable)**| ≥ 80% | **77.8%** | ⚠️ BELOW TARGET |
| **Prompt Injection Resistance** | 100% | **100.0%** (2/2) | ✅ PASS |
| **Latency (p50)** | < 250ms | **9.1 ms** | ✅ PASS |
| **Latency (p95)** | < 600ms | **20.4 ms** | ✅ PASS |
| **LLM Provider Tokens & Cost** | Tracked if returned | Not applicable (Offline Mock) | ℹ️ NOT MEASURED |

---

## 2. Routing Confusion Matrix

| Expected \ Actual | personal | general | hybrid | smalltalk | blocked |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **personal** | 11 | 0 | 0 | 0 | 0 |
| **general** | 5 | 16 | 0 | 0 | 0 |
| **hybrid** | 0 | 0 | 3 | 0 | 0 |
| **smalltalk** | 0 | 0 | 0 | 2 | 0 |
| **blocked** | 0 | 0 | 0 | 0 | 5 |

---

## 3. Groundedness and Faithfulness Review
- **LLM Groundedness**: Provider active is `MockProvider` / extractive mode. As strictly mandated by Section 12 & 13, because no paid third-party LLM key is configured in this local test environment, subjective LLM-as-judge hallucination scores are marked:
  > **STATUS: REQUIRES MANUAL REVIEW** (Honest reporting: zero synthetic scores fabricated).
- **Extractive Grounding**: 100% of generated outputs in extractive mode quote verified source chunks verbatim with file name and section title.
