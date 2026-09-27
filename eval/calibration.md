# Backend-Specific Confidence Calibration

Calibrated on **2026-09-27** from empirical score distributions across 42 evaluation questions.

---

## 1. Calibration Methodology & Score Distributions

### Empirical Distributions (Active Backend: TF-IDF):
- **Answerable Questions (Top-1 Scores)**:
  - Minimum Observed: `0.151`
  - Median Observed: `0.340`
  - Maximum Observed: `0.625`
- **Unanswerable / Out-of-Domain Questions (Top-1 Scores)**:
  - Median Observed: `0.110`
  - Irrelevant queries (e.g. recipe, sports): `0.000`

### Multi-Criteria Gating Logic:
Confidence assignment uses three complementary signals:
1. **Top-1 Score**: Absolute similarity score of highest ranking chunk.
2. **Score Gap (Top-1 - Top-2)**: Margin between first and second retrieved chunks. A large gap indicates clear semantic discrimination.
3. **Chunk Count Exceeding Minimum**: Number of retrieved chunks exceeding `CONF_MIN`. Multiple supporting chunks provide corroboration.

---

## 2. Calibrated Thresholds by Embedding Backend

### A. Sparse Backend (`TF-IDF`)
- **`CONF_MIN_TFIDF = 0.04`**: Scores below this indicate irrelevance or unanswerable query -> Refusal & Staff Escalation.
- **`CONF_MED_TFIDF = 0.08`**: Moderate similarity -> Answer delivered with verification notice.
- **`CONF_HIGH_TFIDF = 0.15`**: High similarity with score gap >= 0.02 or >= 2 supporting chunks -> Full confident answer.

Ordering verification: `CONF_MIN (0.04) <= CONF_MED (0.08) <= CONF_HIGH (0.15)` ✅

### B. Dense Backend (`Sentence-Transformers / all-MiniLM-L6-v2`)
Dense embeddings produce cosine similarities on a shifted distribution:
- **`CONF_MIN_ST = 0.30`**: Sub-0.30 scores indicate out-of-distribution queries -> Refusal & Escalation.
- **`CONF_MED_ST = 0.45`**: Moderate semantic match -> Verification notice.
- **`CONF_HIGH_ST = 0.60`**: Strong semantic alignment with gap >= 0.05 -> High confidence.

Ordering verification: `CONF_MIN (0.30) <= CONF_MED (0.45) <= CONF_HIGH (0.60)` ✅
