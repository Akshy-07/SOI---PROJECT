import os
import re
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Any

from rag.vector_index import VectorIndex
from rag.embeddings import EmbeddingEngine
from rag.retriever import HybridRetriever
from ai.generator import generate_grounded_answer

logger = logging.getLogger(__name__)

def sanitize_chat_input(query: str, max_chars: int = 500) -> str:
    """Cap question length and strip control characters (M5)."""
    if not query:
        return ""
    # Strip non-printable and control characters except common whitespace
    cleaned = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]", "", query)
    return cleaned[:max_chars].strip()

def get_active_document_ids(db_path: str) -> List[int]:
    """
    Document Freshness Filter (Phase 8):
    Returns list of document IDs where status='active' and today's date falls
    within [effective_from, effective_until].
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT id, effective_from, effective_until
        FROM kb_documents
        WHERE status = 'active'
    """)
    rows = cur.fetchall()
    valid_ids = []

    for r in rows:
        ef_from = r["effective_from"]
        ef_until = r["effective_until"]

        if ef_from and ef_from > today_str:
            # Future document, not yet active
            continue
        if ef_until and ef_until < today_str:
            # Expired document, no longer active
            continue

        valid_ids.append(r["id"])

    conn.close()
    return valid_ids

class RAGHandler:
    def __init__(self, db_path: str, index_dir: str = None):
        self.db_path = db_path
        self.index = VectorIndex(index_dir=index_dir) if index_dir else VectorIndex()
        self.embedding_engine = EmbeddingEngine(vectorizer_path=self.index.vectorizer_path)
        self.retriever = HybridRetriever(self.index, self.embedding_engine)

    def answer_query(self, query: str) -> Dict[str, Any]:
        """
        Handle RAG query with document freshness filtering, hybrid retrieval, and grounded generation.
        """
        self.index.check_and_reload()
        if os.path.exists(self.index.vectorizer_path):
            vec_mtime = os.path.getmtime(self.index.vectorizer_path)
            if getattr(self, '_vec_mtime', 0.0) != vec_mtime or self.embedding_engine.tfidf_vectorizer is None:
                self.embedding_engine.load_tfidf(self.index.vectorizer_path)
                self._vec_mtime = vec_mtime
        clean_query = sanitize_chat_input(query)
        if not clean_query:
            return {
                "answer": "Please provide a valid question.",
                "confidence": "none",
                "sources": [],
                "offer_escalation": False,
                "generation_status": "empty_input"
            }

        import time
        active_ids = get_active_document_ids(self.db_path)
        top_k = int(os.environ.get("RAG_TOP_K", 5))

        t_ret_start = time.time()
        chunks = self.retriever.retrieve(clean_query, top_k=top_k, active_doc_ids=active_ids)
        retrieval_ms = int((time.time() - t_ret_start) * 1000)

        backend = self.embedding_engine.backend
        t_gen_start = time.time()
        result = generate_grounded_answer(clean_query, chunks, backend=backend)
        generation_ms = int((time.time() - t_gen_start) * 1000)

        result["retrieval_ms"] = retrieval_ms
        result["generation_ms"] = generation_ms
        return result
