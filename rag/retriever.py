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

class HybridRetriever:
    """Hybrid Retriever combining Vector Index and BM25 with Reciprocal Rank Fusion."""
    def __init__(self, index: VectorIndex, embedding_engine: EmbeddingEngine):
        self.index = index
        self.embedding_engine = embedding_engine

    def tokenize(self, text: str) -> List[str]:
        return re.findall(r"\w+", text.lower())

    def retrieve(self, query: str, top_k: int = 5, active_doc_ids: List[int] = None) -> List[Dict[str, Any]]:
        """
        Perform hybrid retrieval:
        1. Query embedding and vector search.
        2. BM25 sparse search.
        3. Reciprocal Rank Fusion (k=60).
        4. Optional cross-encoder reranking.
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
        vector_results = self.index.search(query_vec, top_k=top_k * 2, active_doc_ids=active_doc_ids)

        use_bm25 = os.environ.get("RAG_USE_BM25", "1") == "1"
        if not use_bm25 or len(self.index.chunks) == 0:
            final_chunks = []
            for chunk, score in vector_results[:top_k]:
                c = dict(chunk)
                c["score"] = float(score)
                final_chunks.append(c)
            return final_chunks

        # BM25 Search
        query_tokens = self.tokenize(query)
        bm25_corpus = [self.tokenize(c.get("text", "")) for c in self.index.chunks]

        try:
            from rank_bm25 import BM25Okapi
            bm25 = BM25Okapi(bm25_corpus)
            bm25_scores = bm25.get_scores(query_tokens)
        except Exception:
            bm25 = SimpleBM25(bm25_corpus)
            bm25_scores = bm25.get_scores(query_tokens)

        # Filter BM25 results by active_doc_ids
        bm25_ranked = []
        for idx, score in enumerate(bm25_scores):
            chunk = self.index.chunks[idx]
            doc_id = chunk.get("doc_id")
            if active_doc_ids is not None and doc_id is not None and doc_id not in active_doc_ids:
                continue
            bm25_ranked.append((chunk, float(score)))

        bm25_ranked.sort(key=lambda x: x[1], reverse=True)
        bm25_ranked = bm25_ranked[:top_k * 2]

        # Reciprocal Rank Fusion (RRF with k=60)
        K_RRF = 60
        rrf_scores = defaultdict(float)
        chunk_map = {}

        for rank, (chunk, v_score) in enumerate(vector_results):
            if v_score <= 0.0:
                continue
            cid = chunk.get("chunk_id", str(id(chunk)))
            rrf_scores[cid] += 1.0 / (K_RRF + rank + 1)
            chunk_map[cid] = (chunk, v_score)

        for rank, (chunk, b_score) in enumerate(bm25_ranked):
            if b_score <= 0.0:
                continue
            cid = chunk.get("chunk_id", str(id(chunk)))
            rrf_scores[cid] += 1.0 / (K_RRF + rank + 1)
            if cid not in chunk_map:
                chunk_map[cid] = (chunk, 0.0)

        if not rrf_scores:
            return []

        # Sort by combined RRF score
        sorted_rrf = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

        final_chunks = []
        for cid, rrf_score in sorted_rrf[:top_k]:
            chunk, v_score = chunk_map[cid]
            c = dict(chunk)
            c["score"] = float(v_score)
            c["rrf_score"] = float(rrf_score)
            final_chunks.append(c)

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
                logger.warning(f"Cross-encoder reranker unavailable ({e}). Using RRF ordering.")

        return final_chunks
