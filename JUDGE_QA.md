# Judge Q&A Cheat Sheet — Smart College Assistant

This cheat sheet equips the presenter to answer challenging architectural, security, and algorithmic questions from hackathon judges.

---

### Core Architecture & Privacy

#### Q1: Why not just put the student database schema into the LLM prompt and let it write SQL (Text-to-SQL)?
**A**: Sending live database schemas and records to an LLM introduces severe privacy risks (FERPA/GDPR compliance violations), unpredictable latency, high token costs, and vulnerability to prompt injection or SQL injection. Our deterministic Python/SQL layer guarantees instant, free, 100% accurate personal answers scoped exclusively to `session['student_id']`.

#### Q2: How is cross-student data access (IDOR) prevented?
**A**: Identity is extracted strictly from the server-side signed session (`session['student_id']`). Any client-supplied `student_id`, `reg_no`, or parameters in the request JSON are completely discarded. Furthermore, our router scans query text for foreign register numbers or student names and diverts unauthorized queries to a security block route.

#### Q3: How does the audit trail maintain privacy without storing sensitive data?
**A**: Strict data minimization (Section 6, Rule 4 & Phase 8) is enforced. For personal queries, neither the question text nor the answer (e.g. percentages, marks, fees) is stored. Only safe enum tokens (`PERSONAL_ATTENDANCE_QUERY`, `PERSONAL_MARKS_QUERY`, `PERSONAL_FEES_QUERY`, `PERSONAL_TIMETABLE_QUERY`, `PERSONAL_LEAVE_QUERY`) are recorded.

---

### Retrieval, Embeddings & RAG

#### Q4: How does the system work completely offline without internet access?
**A**: By setting `LLM_PROVIDER=mock` and `EMBEDDING_BACKEND=tfidf`, the application uses a local Scikit-Learn TF-IDF vectorizer and brute-force cosine similarity index. Extractive quotation mode answers questions by quoting verified source chunks with exact citations. Zero third-party API calls are made.

#### Q5: How do you prevent TF-IDF vocabulary drift when documents are uploaded?
**A**: Whenever documents are uploaded, deleted, or toggled, `IngestionPipeline.rebuild_index()` refits the TF-IDF vectorizer over all active chunks, saves the vectorizer alongside the vector index, and atomically replaces the index files under a file lock.

#### Q6: What is Reciprocal Rank Fusion (RRF) and why do you use it?
**A**: Vector search captures semantic similarity, while BM25 captures exact lexical matches (such as course codes or acronyms). RRF merges both ranked lists using $RRF(d) = \sum \frac{1}{60 + r_i(d)}$, eliminating the need for delicate score normalization across different scoring distributions and achieving 100% Recall@5.

#### Q7: How does confidence calibration prevent hallucination?
**A**: Rather than fabricating artificial percentages, our confidence logic (`ai/generator.py`) evaluates three empirical signals: Top-1 score, Top-1/Top-2 score gap, and supporting chunk count. Thresholds are backend-specific (`CONF_MIN_TFIDF = 0.04`, `CONF_MED_TFIDF = 0.08`, `CONF_HIGH_TFIDF = 0.15` vs dense `0.30/0.45/0.60`). If Top-1 falls below `CONF_MIN`, the assistant refuses to answer and offers 1-click staff escalation.

---

### Answer Caching & Follow-Ups

#### Q8: How does the answer cache work and how do you prevent privacy leaks?
**A**: Only general policy/RAG queries are eligible for caching. Personal and hybrid queries are strictly excluded. The cache normalizes and hashes the question (`SHA-256`), stores the answer JSON, and tags it with the active `index_version`. When a document is modified or re-indexed, stale cache entries are automatically invalidated.

#### Q9: How are follow-up questions (e.g., "and for semester 2?") resolved?
**A**: Session history maintains the last 3 relevant turns. When an elliptical follow-up is detected, a deterministic rewriter combines the antecedent's subject with the follow-up modifier into a standalone query before routing. If an external LLM provider is active, it can assist with rewriting, but personal values are never sent in the rewrite prompt.

---

### Document Ingestion & Fault Tolerance

#### Q10: Does uploading a large document block the web server?
**A**: No. Document uploads validate file headers and magic bytes immediately, save the file with a UUID name, set status to `queued`, and return HTTP 200 within milliseconds. Ingestion runs asynchronously in a background worker (`queued` -> `processing` -> `active` / `failed`).

#### Q11: What happens if an uploaded document is corrupted or fails processing?
**A**: The background worker catches the parsing error, flags the document as `failed` in the database, and leaves the active vector index untouched. The existing index remains 100% operational with zero downtime.

#### Q12: How do you handle document freshness and superseding?
**A**: Documents possess `effective_from`, `effective_until`, and `supersedes_id` metadata. Our freshness filter checks the query timestamp against these ranges and excludes expired documents before retrieval.

---

### Evaluation Honesty & Benchmark Integrity

#### Q13: Why are some metrics in your evaluation report labeled "BELOW TARGET"?
**A**: In accordance with our core design principle of *Honesty over Appearance*, we report true measured results. Routing accuracy is measured at 88.1% (target 90%), MRR at 0.6792 (target 0.80), and Citation Correctness at 70.0% (target 90%). We explicitly label these as `BELOW TARGET` rather than fabricating synthetic 100% claims.

#### Q14: How does the evaluation regression gate work?
**A**: We implemented an automated regression gate (`tests/test_eval_gate.py`) that checks that key benchmark metrics do not fall below the measured baseline minus tolerance (e.g., Routing Accuracy >= 83.1%, Refusal Recall >= 72.8%). If a code change degrades system accuracy below this tolerance floor, the test suite immediately fails.

#### Q15: What is your production scaling roadmap?
**A**: The modular design allows straightforward enterprise scaling: SQLite can be replaced with PostgreSQL (`pgvector`), rate limiting can be backed by Redis, and the Gunicorn WSGI server can run horizontally behind an Nginx reverse proxy.
