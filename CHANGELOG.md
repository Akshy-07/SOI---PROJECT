# Project Changelog & Milestone Progression

All notable changes and architectural evolutions made to the Smart College Assistant.

---

## [Milestone M10] - Gaps Remediation, Caching, Follow-Ups & Final Hardening
- **Answer Caching (Phase 5)**: Implemented runtime `answer_cache` in `ResponseComposer` with question normalization, SHA-256 hashing, index-version tracking, and automatic invalidation upon corpus modification. Personal and hybrid responses are strictly excluded.
- **Follow-Up Rewriting (Phase 6)**: Added session-scoped follow-up resolution (`chatbot/followup.py`) keeping the last 3 turns, deterministic antecedent merging, and safe LLM fallback without personal data leakage.
- **Audit Data Minimization (Phase 8)**: Refactored `chatbot/audit.py` to record only safe enum tokens (`PERSONAL_ATTENDANCE_QUERY`, etc.) with zero personal values or question snippets.
- **Asynchronous Ingestion (Phase 9)**: Added background document ingestion worker with state tracking (`queued` -> `processing` -> `active`/`failed`), preserving active vector index integrity on failures.
- **Evaluation Honesty & Regression Gate (Phase 3, 4, 10)**: Replaced hardcoded passes with dynamic evaluation status labeling (`BELOW TARGET`), fixed inverted calibration thresholds, and added an automated regression gate (`tests/test_eval_gate.py`).
- **Observability & Diagnostics (Phase 7, 11)**: Added retrieval/generation latency breakdown, structured JSON logging, and comprehensive `/healthz` diagnostics.
- **Test Suite Expansion**: Grew test coverage from 38 to 55 tests passing green (100% pass rate).

## [Milestone M9] - Packaging, Deployment & Hackathon Deliverables
- Added `Dockerfile` with slim Python 3.11, non-root user, and Gunicorn WSGI server.
- Added `docker-compose.yml` configured with volume persistence for `database.db`, `rag_index/`, and uploads.
- Created `seed_demo.py` all-in-one demo seed script for instant 30-second setup.
- Added `README.md`, `ARCHITECTURE.md`, `DEMO_SCRIPT.md`, and `PITCH.md`.
- Full regression suite passing: 38/38 tests green.

## [Milestone M8] - Performance & Observability
- Added `/healthz` endpoint reporting database status, vector index backend, and LLM provider configuration without leaking credentials.
- Added structured JSON audit logging with per-stage latency timings.
- Configured request ID tracing across all error responses and logs.

## [Milestone M7] - Evaluation & Calibration
- Created benchmark evaluation suite `eval/run_eval.py` running on `eval/test_questions.json` (42 comprehensive questions).
- Calibrated confidence thresholds for TF-IDF and dense embeddings.
- Measured results: 88.1% routing accuracy, 100.0% retrieval recall@5, 100.0% refusal recall, 100.0% injection resistance, ~13ms latency.

## [Milestone M6] - Error Handling & Graceful Degradation
- Implemented global error handlers for 400, 401, 403, 404, 429, and 500 returning consistent JSON contracts for API requests and styled error pages for HTML navigation.
- Established graceful degradation ladder: Full LLM answer -> Extractive quotation fallback -> Refusal + Staff Escalation.

## [Milestone M5] - Security Hardening & Audit Logging
- Enforced server-side `@role_required` decorators across all protected endpoints.
- Implemented CSRF protection using `Flask-WTF CSRFProtect`.
- Configured rate limiting on login (15/min) and `/chat` (20/min) using `Flask-Limiter`.
- Added data minimisation in audit logs (personal query values are never recorded).
- Added `SECURITY.md` detailing mitigations for IDOR, prompt injection, CSRF, and SQL injection.

## [Milestone M4] - Staff Escalation & FAQ Closed Loop
- Added `unresolved_queries` and `faq_entries` tables.
- Built `/submit_unresolved_query` endpoint tied to verified `request_id`.
- Built faculty queue at `/staff` for query resolution with optional FAQ promotion.
- Built admin approval at `/admin/faq/approve/<id>` which indexes approved answers into KB.

## [Milestone M3] - Document Management & Freshness Filtering
- Added admin document management: Upload, Activate/Deactivate, Delete, Re-index.
- Implemented SHA-256 deduplication rejecting duplicate file contents.
- Added document date validity filtering (`effective_from`, `effective_until`) so expired documents are never cited.
- Implemented versioning and superseding logic.

## [Milestone M2] - Retrieval Hardening & Index Consistency
- Fixed TF-IDF vocabulary drift (Fix F1) by refitting vectorizer on active chunks.
- Added `rag_index/manifest.json` tracking embedding backend and document list (Fix F2).
- Added atomic file replacement and file locking (`FileLock`) during index rebuilds (Fix F6).
- Added Hybrid Retrieval combining BM25 keyword matching with Vector Cosine Similarity fused via Reciprocal Rank Fusion (k=60).

## [Milestone M1] - Hybrid Routing & Section 4.1 Chat Contract
- Re-architected `/chat` response contract to return unified JSON format with `reply`, `answer`, `route`, `confidence`, `sources`, `offer_escalation`, `generation_status`, and `latency_ms`.
- Added two-layer router (Transparent regex rules + Exemplar cosine similarity in `chatbot/intents.json`).
- Added deterministic `hybrid` route combining personal attendance and `policy_rules` table.

## [Milestone M0] - Audit & Safety Net
- Audited legacy codebase and verified database schema.
- Added regression test suite `tests/test_existing_regression.py` preserving existing ERP features (login, dashboards, attendance, marks, fees, timetable, leave/OD).
