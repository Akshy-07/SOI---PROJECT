# Threshold Calibration (Fix F3)

## Method
Calibrated using the score distributions of answerable policy questions vs unanswerable/out-of-domain questions:
- **Median Answerable Score**: 0.081
- **Median Unanswerable Score**: 0.182

## Calibrated Thresholds for Active Backend (TF-IDF)
- `CONF_MIN_TFIDF = 0.23` : Score below this indicates irrelevance or missing document -> Trigger refusal & escalation.
- `CONF_MED_TFIDF = 0.16` : Moderate score -> Answer with verification notice.
- `CONF_HIGH_TFIDF = 0.35` : High score with clear rank separation -> Full confident answer.
