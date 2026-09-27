# M0 Comprehensive Audit Report — Smart College Assistant

**Date:** 2026-09-27  
**Auditor:** Antigravity Pair Programming Assistant  
**Repository:** Smart College Assistant (Flask + SQLite + Hybrid RAG)  
**Environment:** Windows Server / Python 3.13.5 / Local SQLite / TF-IDF Vector Index / Mock LLM Provider  

---

## 1. Executive Summary

This audit assesses the Smart College Assistant codebase against the Master Implementation Plan (M0–M15). The project implements a hybrid architecture combining deterministic SQLite queries for personal student data (attendance, marks, fees, timetable, leave/OD) with Retrieval-Augmented Generation (RAG) over administrative policy documents.

The audit examined all core modules (`app.py`, `migrate.py`, `init_db.py`, `seed_demo.py`, `ai/`, `rag/`, `chatbot/`, `eval/`, `tests/`, templates, static files, and configuration). The core architecture is fundamentally sound and all 38 existing characterisation tests pass without regressions against a temporary test database. However, 10 specific gaps, broken reporting issues, and uncompleted requirements were discovered and cataloged below for immediate remediation in Phases 2–15.

---

## 2. Route Inventory & Access Control Matrix

Every registered Flask route was inspected for HTTP methods, role-based authorization, server-side enforcement, and SQL parameterization:

| Route Path | HTTP Methods | Required Role | Server-Side Auth Enforced? | SQL Parameterized? | Notes & Observations |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `/` | `GET` | None | Public redirect | N/A | Redirects authenticated users to respective role dashboard; unauthenticated to `/login`. |
| `/login` | `GET`, `POST` | None | Public entrypoint | ✅ Yes (`?` placeholders) | Rate-limited (15/min); password verified via PBKDF2 hash (`check_password_hash`). |
| `/logout` | `GET` | Any | Public entrypoint | N/A | Clears session securely. |
| `/student` | `GET` | `student` | ✅ Yes (`@role_required('student')`) | ✅ Yes | Scoped strictly to `session['student_id']`. |
| `/student/leave/apply` | `POST` | `student` | ✅ Yes (`@role_required('student')`) | ✅ Yes | Scoped to `session['student_id']`; CSRF protected. |
| `/staff` | `GET` | `staff` | ✅ Yes (`@role_required('staff')`) | ✅ Yes | Shared faculty queue view for student leaves & unresolved escalations. |
| `/staff/queries` | `GET` | `staff`, `admin` | ✅ Yes (`@role_required('staff', 'admin')`) | ✅ Yes | JSON API for unresolved escalation queries with status filter. |
| `/staff/leave/review/<id>` | `POST` | `staff` | ✅ Yes (`@role_required('staff')`) | ✅ Yes | Reviews student leave/OD application. |
| `/staff/resolve_query/<id>`| `POST` | `staff`, `admin` | ✅ Yes (`@role_required('staff', 'admin')`) | ✅ Yes | Resolves student escalation; supports optional 1-click FAQ promotion. |
| `/admin` | `GET` | `admin` | ✅ Yes (`@role_required('admin')`) | ✅ Yes | Admin dashboard with KB documents, FAQs, audit logs, policy rules. |
| `/admin/student/add` | `POST` | `admin` | ✅ Yes (`@role_required('admin')`) | ✅ Yes | Creates student record and user account with hashed password. |
| `/admin/kb/upload` | `POST` | `admin` | ✅ Yes (`@role_required('admin')`) | ✅ Yes | Handles document upload. Currently blocks synchronously during ingestion (Gap). |
| `/admin/kb/toggle/<id>` | `POST` | `admin` | ✅ Yes (`@role_required('admin')`) | ✅ Yes | Toggles document active/inactive and triggers index rebuild. |
| `/admin/kb/delete/<id>` | `POST` | `admin` | ✅ Yes (`@role_required('admin')`) | ✅ Yes | Deletes document record, file on disk, and rebuilds index. |
| `/admin/kb/reindex/<id>` | `POST` | `admin` | ✅ Yes (`@role_required('admin')`) | ✅ Yes | Rebuilds vector index over active corpus. |
| `/admin/kb/reindex_all` | `POST` | `admin` | ✅ Yes (`@role_required('admin')`) | ✅ Yes | Re-indexes all active documents. |
| `/admin/faq/approve/<id>` | `POST` | `admin` | ✅ Yes (`@role_required('admin')`) | ✅ Yes | Approves staff draft FAQ and automatically ingests text into KB index. |
| `/admin/policy_rule/update`| `POST` | `admin` | ✅ Yes (`@role_required('admin')`) | ✅ Yes | Updates deterministic policy rules (`policy_rules` table). |
| `/admin/audit` | `GET` | `admin` | ✅ Yes (`@role_required('admin')`) | ✅ Yes | Filtered view of audit logs. |
| `/chat` | `POST` | `student` | ✅ Yes (`@role_required('student')`) | ✅ Yes | Core endpoint; rate-limited (20/min); returns Section 4.1 contract JSON. |
| `/submit_unresolved_query` | `POST` | `student` | ✅ Yes (`@role_required('student')`) | ✅ Yes | Escalates unanswered question to staff queue. |
| `/chat/feedback` | `POST` | `student` | ✅ Yes (`@role_required('student')`) | ✅ Yes | Submits thumbs-up / thumbs-down rating for a response. |
| `/healthz` | `GET` | None | Public monitoring | ✅ Yes | Health check reporting DB, backend, provider (Missing index status report). |

---

## 3. Database Schema & Migration Inventory

The project utilizes SQLite with Write-Ahead Logging (`WAL` mode) and busy timeouts (5000ms). Schema migrations in `migrate.py` are idempotent and perform automated timestamped backups to `backups/` before schema modifications.

### Table Inventory
1. **`students`**: Student academic master record (`id`, `reg_no`, `name`, `dept`, `semester`, `email`, `phone`).
2. **`users`**: Authentication credentials (`id`, `username`, `password_hash`, `role`, `name`, `student_id`).
3. **`attendance`**: Course attendance stats (`id`, `student_id`, `subject`, `total_classes`, `attended_classes`, `percentage`).
4. **`marks`**: Internal assessment marks (`id`, `student_id`, `subject`, `internal1`, `internal2`, `assignment`, `total`).
5. **`fees`**: Financial billing (`id`, `student_id`, `total_fee`, `paid_fee`, `due_fee`, `due_date`, `status`).
6. **`timetable`**: Weekly department class schedule (`id`, `department`, `semester`, `day_of_week`, `period_1`..`period_5`).
7. **`leave_requests`**: Student leave/OD applications (`id`, `student_id`, `req_type`, `from_date`, `to_date`, `reason`, `status`, `applied_at`, `reviewed_by`, `review_comment`).
8. **`kb_documents`**: Uploaded administrative knowledge base documents (`id`, `file_name`, `file_path`, `file_hash`, `file_type`, `version`, `uploaded_by`, `effective_from`, `effective_until`, `status`, `chunk_count`, `embedding_backend`, `supersedes_id`, `created_at`).
9. **`unresolved_queries`**: Staff escalation queue (`id`, `student_id`, `reg`, `question`, `chatbot_response`, `route`, `confidence`, `status`, `staff_response`, `reviewed_by`, `created_at`, `resolved_at`).
10. **`faq_entries`**: Staff-promoted knowledge base FAQs (`id`, `question`, `answer`, `source_query_id`, `approved_by`, `status`, `created_at`).
11. **`audit_logs`**: System event and chat audit log (`id`, `request_id`, `ts`, `user_role`, `user_id`, `event_type`, `route`, `question`, `answer`, `sources_json`, `confidence`, `latency_ms`, `status`).
12. **`chat_feedback`**: Student ratings (`id`, `request_id`, `student_id`, `rating`, `comment`, `created_at`).
13. **`policy_rules`**: Grounded business rules (`key`, `value`, `unit`, `source_document_id`, `updated_by`, `updated_at`).
14. **`answer_cache`**: General query response cache table (`question_norm_hash`, `answer_json`, `index_version`, `created_at`).

---

## 4. Verification of Claimed Phases (Master Prompt M0–M15)

| Phase / Milestone | Description | Claimed Status | Actual Verified Status | Detailed Audit Findings |
| :--- | :--- | :--- | :--- | :--- |
| **M0** | Existing ERP Features | Done | ✅ Fully Verified | Attendance, marks, fees, timetable, leave/OD workflows operate correctly and are protected by regression tests. |
| **M1** | Hybrid Routing & Chat Contract | Done | ✅ Verified | Returns Section 4.1 contract (`reply`, `answer`, `route`, `confidence`, `sources`, `offer_escalation`, `generation_status`, `latency_ms`). |
| **M2** | RAG Ingestion & Indexing | Done | ✅ Verified | Word-based overlapping chunking; TF-IDF refit & atomic persistence with `FileLock`; BM25 + Vector RRF search. |
| **M3** | Document Management & Freshness | Done | ⚠️ Partial | Admin toggle, delete, reindex, versioning, and freshness date filters work. However, uploads block synchronously (background queue missing). |
| **M4** | Staff Escalation & FAQ Loop | Done | ✅ Verified | `/submit_unresolved_query` records escalation; staff resolution and FAQ promotion ingest into KB. |
| **M5** | Security Hardening & Audit | Done | ⚠️ Partial | Role checks, CSRF, rate-limiting, and UUID uploads active. Audit logging violates data minimization (logs first 30 chars of personal query). |
| **M6** | Error Handling | Done | ✅ Verified | Custom handlers for 400, 401, 403, 404, 429, 500 returning consistent JSON with request UUIDs. |
| **M7** | Evaluation & Calibration | Done | ❌ Flawed Reporting | Evaluation suite exists (`eval/run_eval.py`), but REPORT.md unconditionally outputs `PASS` for below-target metrics (Routing 88.1%, MRR 0.6792, Citations 70%). Calibration derived inverted thresholds (`CONF_MIN > CONF_MED`). |
| **M8** | Observability | Done | ⚠️ Partial | Request ID and total latency recorded, but stage timings (retrieval vs generation) and token usage/cost tracking are missing. |
| **M9** | Packaging & Docker | Done | ✅ Verified | Dockerfile and docker-compose.yml configured; seed script (`seed_demo.py`) functional. |
| **Answer Cache** | General query cache | Claimed | ❌ Not Implemented | `answer_cache` table exists in schema, but `composer.py` never checks or writes to cache. |
| **Follow-Up Handling** | Multi-turn rewriting | Claimed | ❌ Not Implemented | No session-scoped conversation history or standalone query rewriter in place. |
| **Regression Gate** | Automated eval gate | Planned | ❌ Not Implemented | No test verifying metrics stay above baseline minus tolerance. |

---

## 5. Identified Bugs and Gaps

1. **Direct `pytest -q` CLI Inconvenience**:
   - `pytest.exe` resides in Python user scripts path (`C:\Users\DELL\AppData\Roaming\Python\Python313\Scripts\pytest.exe`) which is not in the system-wide Windows PATH environment variable. Running `pytest -q` directly from powershell fails unless invoked via `python -m pytest` or provided with a root CLI wrapper (`pytest.bat`).
2. **Evaluation Metrics Dishonesty**:
   - `eval/run_eval.py` generates `eval/REPORT.md` with hard-coded `✅ PASS` for all rows regardless of measured thresholds. Routing accuracy (88.1% vs target 90%), MRR (0.6792 vs target 0.80), and citation accuracy (70.0% vs target 90%) must be reported as `BELOW TARGET`.
3. **Flawed Confidence Calibration**:
   - `eval/calibration.md` reports `CONF_MIN_TFIDF = 0.23` and `CONF_MED_TFIDF = 0.16`. This violates basic threshold ordering logic (`MIN <= MED <= HIGH`).
4. **Answer Cache Missing at Runtime**:
   - The `answer_cache` SQLite table is created, but `composer.py` does not perform query normalization, hashing, index-version checks, cache retrieval, or cache population.
5. **Follow-Up Handling Missing**:
   - Follow-up turns (e.g., "and for semester 2?") fail to resolve context from the previous turn because conversation history is not tracked across session turns.
6. **Observability Gaps**:
   - Chatbot requests only record total elapsed latency. Separate retrieval timing, generation timing, structured JSON logging, and token tracking are not implemented.
7. **Personal Audit Data Minimization Violation**:
   - `chatbot/audit.py` logs `[PERSONAL_DATA_QUERY: {question[:30]}...]`. Capturing the first 30 characters of the question leaks personal query details into audit logs.
8. **Document Upload Pipeline Blocks**:
   - Uploading a document via `/admin/kb/upload` invokes `ingest_document` synchronously on the web server thread, blocking the HTTP response. It must be decoupled into an asynchronous background job (`queued` -> `processing` -> `ready` / `failed`).
9. **Missing Evaluation Regression Gate**:
   - No pytest test enforces that evaluation metrics do not regress below baseline tolerances.
10. **Incomplete Health Check (`/healthz`)**:
    - The `/healthz` endpoint does not verify vector index status or detail whether the LLM provider is active or in fallback mode.

---

## 6. Existing Test Inventory

The existing test suite comprises 11 files in `tests/`:
- `test_existing_regression.py` (10 tests): Verifies student dashboard, attendance, marks, fees, timetable, leave submission, staff queue, admin student creation, and logout.
- `test_router.py` (4 tests): Tests personal routing, general RAG routing, smalltalk, and blocked security routes.
- `test_personal_scoping.py` (3 tests): Verifies database scoping to `session['student_id']` and zero cross-student IDOR leakage.
- `test_rag_pipeline.py` (3 tests): Verifies text loading, overlapping chunking, and TF-IDF embedding & vector search.
- `test_index_consistency.py` (3 tests): Tests vector manifest consistency and atomic index rebuilds.
- `test_freshness.py` (3 tests): Verifies date filtering (`effective_from`, `effective_until`) and document deactivation.
- `test_doc_management.py` (3 tests): Tests upload deduplication, document toggle, and document deletion.
- `test_escalation.py` (3 tests): Verifies escalation submission, staff query resolution, and FAQ promotion into KB.
- `test_security.py` (3 tests): Verifies prompt injection blocking, cross-student query blocking, and CSRF protection.
- `test_errors.py` (3 tests): Verifies 400 bad request, 401 unauthorized, and 404 not found JSON error responses.
- `test_chat_contract.py` (3 tests): Tests Section 4.1 JSON contract compliance, personal query answers, and general RAG fallback.

**Test Execution Status:** 38 passed in 22.25 seconds using temporary isolated databases (`tests/conftest.py`). Production `database.db` was untouched.

---

## 7. Action Plan for Remaining Phases

1. **Phase 2**: Add `pytest.bat` / `pytest.ps1` wrapper in project root so `pytest -q` executes immediately from any terminal shell.
2. **Phase 3**: Update `eval/run_eval.py` to honestly label results (`PASS`, `BELOW TARGET`, `NOT MEASURED`, `REQUIRES MANUAL REVIEW`) and update `eval/REPORT.md`.
3. **Phase 4**: Redo confidence calibration with separate TF-IDF and Sentence-Transformer thresholds, strictly maintaining `MIN <= MED <= HIGH`, and incorporate score gaps and chunk counts.
4. **Phase 5**: Implement runtime answer caching for general RAG queries with normalization, hashing, and index-version invalidation, strictly excluding personal and hybrid queries. Add dedicated test suite.
5. **Phase 6**: Implement session-scoped follow-up resolution (last 3 turns) with deterministic rewriting, cross-session isolation, and dedicated test suite.
6. **Phase 7**: Enhance observability with per-request structured JSON logging, stage timing breakdown (retrieval vs. generation), and token/cost tracking.
7. **Phase 8**: Refactor `chatbot/audit.py` to record only sanitized query types (e.g. `PERSONAL_ATTENDANCE_QUERY`) with zero personal question text. Add verification test.
8. **Phase 9**: Build background document ingestion with stateful jobs (`queued` -> `processing` -> `ready` / `failed`), background worker thread, atomic index safety, and admin UI status display.
9. **Phase 10**: Implement automated evaluation regression gate test (`tests/test_eval_gate.py`) checking routing accuracy and refusal recall against baseline minus tolerance.
10. **Phase 11**: Update `/healthz` to report index status, embedding backend, and LLM configuration without credential exposure.
11. **Phase 12**: Run comprehensive security suite ensuring server-side auth, CSRF, rate-limiting, and IDOR protection.
12. **Phase 13**: Synchronize documentation across `README.md`, `ARCHITECTURE.md`, `SECURITY.md`, `CHANGELOG.md`, `eval/REPORT.md`, and `eval/calibration.md`.
13. **Phase 14**: Package clean production ZIP excluding caches, `.env`, index binaries, and backups.
14. **Phase 15**: Execute complete end-to-end regression pass and generate final report.
