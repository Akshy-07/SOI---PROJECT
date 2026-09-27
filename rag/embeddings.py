import os
import pickle
import logging
import numpy as np
from typing import List, Union

logger = logging.getLogger(__name__)

class EmbeddingEngine:
    """Pluggable embedding engine supporting sentence-transformers and TF-IDF."""
    def __init__(self, backend: str = None, model_name: str = None, vectorizer_path: str = None):
        configured_backend = backend or os.environ.get("EMBEDDING_BACKEND", "auto").lower()
        self.model_name = model_name or os.environ.get("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
        self.backend = configured_backend
        self.st_model = None
        self.tfidf_vectorizer = None
        self.vectorizer_path = vectorizer_path

        if self.backend == "auto":
            try:
                from sentence_transformers import SentenceTransformer
                self.st_model = SentenceTransformer(self.model_name)
                self.backend = "sentence_transformers"
                logger.info("SentenceTransformers loaded successfully as primary backend.")
            except Exception as e:
                logger.info(f"SentenceTransformers unavailable ({e}). Falling back to TF-IDF backend.")
                self.backend = "tfidf"
        elif self.backend == "sentence_transformers":
            try:
                from sentence_transformers import SentenceTransformer
                self.st_model = SentenceTransformer(self.model_name)
            except Exception as e:
                logger.warning(f"Failed to load configured SentenceTransformers ({e}). Falling back to TF-IDF.")
                self.backend = "tfidf"

        if self.vectorizer_path and os.path.exists(self.vectorizer_path):
            self.load_tfidf(self.vectorizer_path)

    def fit_tfidf(self, texts: List[str]):
        """Fit and normalize TF-IDF vectorizer over corpus (Fix F1)."""
        from sklearn.feature_extraction.text import TfidfVectorizer
        if not texts:
            texts = ["college policy document empty placeholder"]
        self.tfidf_vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words='english',
            ngram_range=(1, 2),
            max_features=5000
        )
        self.tfidf_vectorizer.fit(texts)

    def save_tfidf(self, file_path: str):
        """Persist fitted vectorizer to avoid vocabulary drift (Fix F1)."""
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "wb") as f:
            pickle.dump(self.tfidf_vectorizer, f)

    def load_tfidf(self, file_path: str) -> bool:
        """Load persisted fitted vectorizer."""
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                self.tfidf_vectorizer = pickle.load(f)
            return True
        return False

    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """Generate normalized embeddings for a list of texts."""
        if not texts:
            return np.empty((0, 0), dtype=np.float32)

        if self.backend == "sentence_transformers" and self.st_model is not None:
            vectors = self.st_model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
            return vectors.astype(np.float32)
        else:
            # TF-IDF backend
            if self.tfidf_vectorizer is None:
                self.fit_tfidf(texts)
            matrix = self.tfidf_vectorizer.transform(texts).toarray()
            # Normalize rows to unit length for cosine similarity via dot product
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            matrix = matrix / norms
            return matrix.astype(np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        """Generate normalized embedding for a single query."""
        vecs = self.embed_texts([query])
        return vecs[0]
