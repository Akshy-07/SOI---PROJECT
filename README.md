# Smart College Assistant Chatbot (Hybrid Database + RAG)

A production-quality College ERP and Smart Assistant built with Flask, SQLite, and a Hybrid RAG (Retrieval-Augmented Generation) pipeline.

---

## 1. Key Innovations & Architecture
The assistant uses a 3-way hybrid architecture:
1. **Personal Queries (Deterministic SQL)**: Attendance, internal marks, fee arrears, and class timetables are queried directly from SQLite using session-scoped identity (`session['student_id']`). **Personal data never reaches any external LLM.**
2. **Policy Queries (Grounded RAG)**: College regulations, library policies, and scholarship criteria are answered from retrieved, verified, date-valid document chunks with transparent source citations (document name and page number).
3. **Hybrid Eligibility Queries**: Queries like *"Am I eligible to write the semester exam?"* retrieve the student's deterministic attendance from SQLite and college regulations from RAG side-by-side, executing a deterministic rule engine (e.g. `min_attendance_percent = 75`) to avoid hallucinations.
4. **Staff Escalation & FAQ Closed Loop**: When confidence is low or information is unavailable, students can escalate unresolved queries to faculty with 1 click. When staff resolve the query, it can be approved by an administrator to instantly become a trusted Knowledge Base FAQ.
5. **Answer Caching (Phase 5)**: High-confidence general RAG answers are normalized, hashed, and cached against the active `index_version`. Personal and hybrid responses are strictly excluded from the cache.
6. **Session-Scoped Follow-Up Rewriting (Phase 6)**: Elliptical follow-up queries (e.g. "and for semester 2?") are rewritten into standalone queries across the user's last 3 session turns using deterministic rules and optional LLM rewriting without leaking private student data.
7. **Background Document Ingestion (Phase 9)**: Uploads return immediately while processing runs in background threads (`queued` -> `processing` -> `active`/`failed`), preserving active index consistency during indexing.
8. **Evaluation Regression Gate (Phase 10)**: Automated test ensures key benchmark metrics (routing accuracy and refusal recall) never regress below baseline minus allowable tolerance.
9. **Observability & Diagnostics (Phase 7 & 11)**: Request UUID tracing, latency breakdown (retrieval vs. generation), structured JSON logs, and `/healthz` diagnostics reporting index and provider health without leaking credentials.

---

## 2. Quickstart (< 2 Minutes)

### Prerequisites
- Python 3.10+ (Tested on Python 3.11 & 3.13)
- pip

### Step 1: Clone and Set Up Virtual Environment
```bash
git clone <repo-url>
cd akshayaa_soi_prokect1
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 3: Configure Environment
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Default `.env` settings work completely offline without needing any API keys (`LLM_PROVIDER=mock`, `EMBEDDING_BACKEND=tfidf`).

### Step 4: Seed Demo Data and Index
Run the all-in-one demo seed script:
```bash
python seed_demo.py
```
This initializes the database, executes schema migrations, ingests official sample college documents, and builds the search vector index.

### Step 5: Run the Web Server
```bash
python app.py
```
Open your browser at **http://localhost:5000**.

---

## 3. Demo User Accounts

| Role | Username | Password | Notes |
| :--- | :--- | :--- | :--- |
| **Student** | `711724UEC101` | `password123` | Akshayaa S (ECE, 4th Sem, 80% Attendance) |
| **Student** | `711724UEC102` | `password123` | Rahul K (ECE, 4th Sem, 72.5% Attendance) |
| **Staff** | `staff` | `staff123` | Department Faculty (Shared Queue) |
| **Admin** | `admin` | `admin123` | System Administrator (KB & Audit Management) |

---

## 4. Running with Docker

```bash
docker compose up --build
```
The application will be live at `http://localhost:5000`. Volumes persist `database.db`, `rag_index/`, and uploaded files.

---

## 5. Switching AI Providers

Change these values in `.env`:

### Offline Mode (Default):
```ini
LLM_PROVIDER=mock
EMBEDDING_BACKEND=tfidf
```

### OpenAI Mode:
```ini
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...
EMBEDDING_BACKEND=auto
```

### Anthropic Claude Mode:
```ini
LLM_PROVIDER=anthropic
LLM_MODEL=claude-3-5-sonnet-20241022
ANTHROPIC_API_KEY=sk-ant-...
EMBEDDING_BACKEND=auto
```

---

## 6. Running Tests & Evaluation

### Run Test Suite (55 Tests)
```bash
pytest -q
# or
python -m pytest -q
```
All 55 tests run against isolated temporary test databases (never touching production `database.db`), covering:
- ERP regression (10 tests)
- Intent router (4 tests)
- Personal data scoping & IDOR prevention (3 tests)
- RAG loading, chunking, search (3 tests)
- Manifest & index consistency (3 tests)
- Document freshness & date filters (3 tests)
- Document management (3 tests)
- Escalation & FAQ feedback loop (3 tests)
- Security & injection resistance (3 tests)
- Error handlers & HTTP contracts (3 tests)
- Section 4.1 Chat response contract (3 tests)
- Answer caching & invalidation (3 tests)
- Session follow-up rewriting (6 tests)
- Audit data minimization (2 tests)
- Background ingestion & fault tolerance (2 tests)
- Evaluation regression gate (2 tests)
- Health check contract (1 test)

### Run Benchmark Evaluation Pipeline
```bash
python eval/run_eval.py
```
Outputs measured accuracy, recall, refusal rates, and latency figures saved into `eval/results.json`, `eval/REPORT.md`, and `eval/calibration.md`.

---

## 7. Troubleshooting & Known Limitations

- **Rate Limiting**: `/login` is limited to 15 attempts/minute and `/chat` to 20 requests/minute. If exceeded, wait 60 seconds.
- **Shared Staff Login**: By institutional design, faculty share a common queue login. The system clearly discloses this in the staff portal.
- **Sentence-Transformers Weights**: If internet access is unavailable, the system automatically falls back to Scikit-Learn TF-IDF embeddings without throwing errors.
