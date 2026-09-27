import os
import re
import math
import logging
from typing import List, Dict, Any, Tuple
from collections import defaultdict
import numpy as np

from rag.vector_index import VectorIndex
from rag.embeddings import EmbeddingEngine

logger = logging.getLogger(__name__)

class SimpleBM25:
    """Pure-Python BM25 fallback implementation if rank_bm25 is unavailable."""
    def __init__(self, corpus: List[List[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = len(corpus)
        self.doc_lens = [len(doc) for doc in corpus]
        self.avgdl = sum(self.doc_lens) / max(1, self.corpus_size)
        self.doc_freqs = defaultdict(int)
        self.doc_term_counts = []

        for doc in corpus:
            counts = defaultdict(int)
            for token in doc:
                counts[token] += 1
            for token in counts:
                self.doc_freqs[token] += 1
            self.doc_term_counts.append(counts)

        self.idf = {}
        for token, df in self.doc_freqs.items():
            self.idf[token] = math.log((self.corpus_size - df + 0.5) / (df + 0.5) + 1.0)

    def get_scores(self, query_tokens: List[str]) -> List[float]:
        scores = [0.0] * self.corpus_size
        for i in range(self.corpus_size):
            doc_len = self.doc_lens[i]
            counts = self.doc_term_counts[i]
            score = 0.0
            for token in query_tokens:
                if token in counts:
                    freq = counts[token]
                    numerator = self.idf.get(token, 0.0) * freq * (self.k1 + 1)
                    denominator = freq + self.k1 * (1 - self.b + self.b * (doc_len / self.avgdl))
                    score += (numerator / denominator)
            scores[i] = score
        return scores

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

class HybridRetriever:
    """Hybrid Retriever combining Vector Index and BM25 with Reciprocal Rank Fusion and Keyword Coverage."""
    def __init__(self, index: VectorIndex, embedding_engine: EmbeddingEngine):
        self.index = index
        self.embedding_engine = embedding_engine

    def tokenize_meaningful(self, text: str) -> List[str]:
        tokens = re.findall(r"\w+", text.lower())
        return [t for t in tokens if t not in ENGLISH_STOP_WORDS and len(t) > 1]

    def tokenize(self, text: str) -> List[str]:
        return self.tokenize_meaningful(text)

    def retrieve(self, query: str, top_k: int = 5, active_doc_ids: List[int] = None) -> List[Dict[str, Any]]:
        """
        Perform hybrid retrieval:
        1. Query embedding and vector search.
        2. BM25 sparse search with stop-word filtered corpus.
        3. Term coverage and heading match scoring.
        4. Hybrid scoring combining vector similarity, BM25, and coverage.
        5. Optional cross-encoder reranking.
        """
        if not self.index.chunks:
            return []

        # Vector search
        query_vec = self.embedding_engine.embed_query(query)
        if len(self.index.vectors.shape) > 1 and self.index.vectors.shape[1] != query_vec.shape[0]:
            # Auto-realign if index vocabulary was updated by another process/thread
            if os.path.exists(self.index.vectorizer_path):
                self.embedding_engine.load_tfidf(self.index.vectorizer_path)
                query_vec = self.embedding_engine.embed_query(query)

        v_scores_all = np.dot(self.index.vectors, query_vec) if self.index.vectors.size > 0 else np.zeros(len(self.index.chunks))

        # BM25 Search
        query_tokens = self.tokenize_meaningful(query)
        bm25_corpus = [
            self.tokenize_meaningful(c.get("text", "") + " " + c.get("section_title", "") + " " + c.get("document_name", ""))
            for c in self.index.chunks
        ]

        try:
            from rank_bm25 import BM25Okapi
            bm25 = BM25Okapi(bm25_corpus)
            b_scores_all = bm25.get_scores(query_tokens)
        except Exception:
            bm25 = SimpleBM25(bm25_corpus)
            b_scores_all = bm25.get_scores(query_tokens)

        # Normalize scores
        max_v = max(v_scores_all) if len(v_scores_all) > 0 and max(v_scores_all) > 0 else 1.0
        max_b = max(b_scores_all) if len(b_scores_all) > 0 and max(b_scores_all) > 0 else 1.0

        q_kw_set = set(query_tokens)

        ranked_candidates = []
        for idx, chunk in enumerate(self.index.chunks):
            doc_id = chunk.get("doc_id")
            if active_doc_ids is not None and doc_id is not None and doc_id not in active_doc_ids:
                continue

            v_raw = float(v_scores_all[idx]) if idx < len(v_scores_all) else 0.0
            b_raw = float(b_scores_all[idx]) if idx < len(b_scores_all) else 0.0

            norm_v = max(0.0, v_raw / max_v)
            norm_b = max(0.0, b_raw / max_b)

            chunk_words = set(bm25_corpus[idx])
            kw_coverage = len(q_kw_set & chunk_words) / max(1, len(q_kw_set))

            title_words = set(self.tokenize_meaningful(chunk.get("section_title", "") + " " + chunk.get("document_name", "")))
            title_coverage = len(q_kw_set & title_words) / max(1, len(q_kw_set))

            # Penalty for ultra-short chunks (< 12 words) so isolated titles don't overpower content
            chunk_word_count = len(chunk.get("text", "").split())
            len_penalty = 0.75 if chunk_word_count < 12 else 1.0

            hybrid_score = ((0.55 * norm_v) + (0.35 * norm_b) + (0.15 * kw_coverage) + (0.10 * title_coverage)) * len_penalty

            c = dict(chunk)
            c["score"] = v_raw
            c["hybrid_score"] = float(hybrid_score)
            c["kw_coverage"] = float(kw_coverage)
            c["bm25_score"] = b_raw
            ranked_candidates.append(c)

        if not ranked_candidates:
            return []

        # Sort descending by hybrid_score
        ranked_candidates.sort(key=lambda x: x["hybrid_score"], reverse=True)
        final_chunks = ranked_candidates[:top_k]

        # Optional Reranker (behind RAG_USE_RERANKER)
        if os.environ.get("RAG_USE_RERANKER", "0") == "1":
            try:
                from sentence_transformers import CrossEncoder
                reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
                pairs = [[query, c["text"]] for c in final_chunks]
                rerank_scores = reranker.predict(pairs)
                for idx, r_score in enumerate(rerank_scores):
                    final_chunks[idx]["score"] = float(r_score)
                final_chunks.sort(key=lambda x: x["score"], reverse=True)
            except Exception as e:
                logger.warning(f"Cross-encoder reranker unavailable ({e}). Using hybrid ordering.")

        return final_chunks
