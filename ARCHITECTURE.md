# System Architecture: Smart College Assistant (v2)

This document describes the design, components, data flows, and security boundaries of the Smart College Assistant.

---

## 1. High-Level Architecture Diagram

```
                        +----------------------------+
                        |      Student Question      |
                        +----------------------------+
                                      |
                                      v
                      +--------------------------------+
                      |       Security & Sanitizer     |
                      |  (Length Cap, Control Chars,   |
                      |   Rate Limiter, Request UUID)  |
                      +--------------------------------+
                                      |
                                      v
                      +--------------------------------+
                      |         QuestionRouter         |
                      |  - Layer 1: Rule Regex & Words |
                      |  - Layer 2: Exemplar Vectors   |
                      +--------------------------------+
                                      |
         +-------------+--------------+--------------+-------------+
         |             |                             |             |
         v             v                             v             v
   [smalltalk]    [blocked]                      [personal]    [general/policy]
   (Templates)   (Security Alert)               (SQLite DB)   (RAG Pipeline)
         |             |                             |             |
         |             |                             |             +---> [Freshness Filter]
         |             |                             |             +---> [Hybrid BM25 + Cosine]
         |             |                             |             +---> [RRF Fusion k=60]
         |             |                             |             +---> [Confidence Gating]
         |             |                             |             +---> [Grounded LLM Generation]
         |             |                             |
         |             |               +-------------+-------------+
         |             |               |
         |             |               v
         |             |          [hybrid route]
         |             |          - Personal Attendance (DB)
         |             |          - Policy Regulation (RAG)
         |             |          - Deterministic Verdict (policy_rules)
         |             |
         v             v               v
   +---------------------------------------------------------------+
   |                      Response Composer                        |
   |   - Formats Section 4.1 contract JSON                         |
   |   - Attaches Source Citations & Confidence Level              |
   |   - Data Minimised Audit Log Entry                            |
   +---------------------------------------------------------------+
                                      |
                                      v
                             HTTP 200 JSON Response
```

---

## 2. Core Architectural Pillars

### 2.1 Separation of Personal Data and LLM
- **Deterministic Python/SQL Only**: Student attendance, marks, fees, and timetables are computed directly from the local SQLite database.
- **Zero LLM Leakage**: Personal records are **never** included in LLM prompts, context windows, or sent to external model APIs.

### 2.2 Intent Routing Pipeline
1. **Layer 1: Rule-Based Matcher**: Transparent pattern matching for common intent keywords (e.g., `"attendance"`, `"marks"`, `"fee"`, `"timetable"`).
2. **Layer 2: Exemplar Similarity Classifier (`chatbot/intents.json`)**: When keywords don't match, questions are compared against labeled exemplar utterances using cosine similarity over the active embedding backend.
3. **Layer 3: Default Fallback**: Unclassified general queries fall back to the policy RAG pipeline.

### 2.3 Hybrid Retrieval & RRF Fusion
- **Vector Search**: Cosine similarity against document embeddings (dense sentence-transformers or sparse TF-IDF).
- **BM25 Keyword Search**: Exact-match lexical scoring using BM25.
- **Reciprocal Rank Fusion (RRF)**: Merges ranks with constant $k=60$:
  $$RRF(d) = \sum \frac{1}{60 + r_i(d)}$$
- **Confidence Gate**: Calibrated backend thresholds determine `high`, `medium`, `low`, or `none`. Low/none confidence triggers graceful refusal and offers staff escalation.

### 2.4 Staff Escalation & FAQ Feedback Loop
- **Escalation**: Unanswered queries can be submitted to staff using the request ID.
- **Resolution**: Faculty resolve questions via the staff queue and can flag helpful answers for FAQ promotion.
- **Promotion**: Administrators approve FAQ drafts, which automatically generates a new knowledge base document, re-indexes the corpus, and immediately answers future occurrences of that question with official FAQ citations.
