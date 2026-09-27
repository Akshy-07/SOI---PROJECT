import os
import json
import pickle
import logging
import numpy as np
from datetime import datetime
from typing import List, Dict, Any, Tuple
from filelock import FileLock

logger = logging.getLogger(__name__)

DEFAULT_INDEX_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "rag_index")

class VectorIndex:
    """Local vector index with manifest, atomic writes, and file locking."""
    def __init__(self, index_dir: str = DEFAULT_INDEX_DIR):
        self.index_dir = index_dir
        self.manifest_path = os.path.join(self.index_dir, "manifest.json")
        self.vectors_path = os.path.join(self.index_dir, "vectors.npy")
        self.chunks_path = os.path.join(self.index_dir, "chunks.pkl")
        self.lock_path = os.path.join(self.index_dir, "index.lock")
        self.vectorizer_path = os.path.join(self.index_dir, "tfidf_vectorizer.pkl")

        os.makedirs(self.index_dir, exist_ok=True)
        self.vectors: np.ndarray = np.empty((0, 0), dtype=np.float32)
        self.chunks: List[Dict[str, Any]] = []
        self.manifest: Dict[str, Any] = {}
        self._last_mtime = 0.0
        self.load()

    def check_and_reload(self) -> bool:
        """Check if index files on disk have changed, and reload if so."""
        if not os.path.exists(self.manifest_path):
            return False
        try:
            mtime = os.path.getmtime(self.manifest_path)
            if self._last_mtime != mtime:
                return self.load()
        except Exception as e:
            logger.error(f"Error checking index reload: {e}")
        return False

    def load(self) -> bool:
        """Load index and manifest from disk."""
        if os.path.exists(self.manifest_path) and os.path.exists(self.vectors_path) and os.path.exists(self.chunks_path):
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    self.manifest = json.load(f)
                self.vectors = np.load(self.vectors_path)
                with open(self.chunks_path, "rb") as f:
                    self.chunks = pickle.load(f)
                self._last_mtime = os.path.getmtime(self.manifest_path)
                return True
            except Exception as e:
                logger.error(f"Error loading vector index: {e}")
        return False

    def save_atomic(self, backend: str, model_name: str, doc_ids: List[int]):
        """
        Atomic write of vectors, chunks, and manifest under file lock (Fix F2, F6).
        Writes to temporary files and renames them atomically.
        """
        lock = FileLock(self.lock_path, timeout=10)
        with lock:
            temp_vectors = os.path.join(self.index_dir, "vectors_temp.npy")
            temp_chunks = os.path.join(self.index_dir, "chunks_temp.pkl")
            temp_manifest = os.path.join(self.index_dir, "manifest_temp.json")

            np.save(temp_vectors, self.vectors)
            with open(temp_chunks, "wb") as f:
                pickle.dump(self.chunks, f)

            now_iso = datetime.now().isoformat()
            doc_ids_sorted = sorted(list(set(doc_ids)))
            import hashlib
            version_hash = hashlib.sha256(f"{backend}_{now_iso}_{len(self.chunks)}_{doc_ids_sorted}".encode('utf-8')).hexdigest()[:16]

            manifest_data = {
                "backend": backend,
                "model_name": model_name,
                "dim": int(self.vectors.shape[1]) if len(self.vectors.shape) > 1 else 0,
                "built_at": now_iso,
                "index_version": version_hash,
                "chunk_count": len(self.chunks),
                "doc_ids": doc_ids_sorted
            }
            with open(temp_manifest, "w", encoding="utf-8") as f:
                json.dump(manifest_data, f, indent=2)

            # Atomic rename (os.replace is atomic on POSIX and Windows in modern Python)
            os.replace(temp_vectors, self.vectors_path)
            os.replace(temp_chunks, self.chunks_path)
            os.replace(temp_manifest, self.manifest_path)
            self.manifest = manifest_data
            if os.path.exists(self.manifest_path):
                self._last_mtime = os.path.getmtime(self.manifest_path)
            logger.info(f"Vector index saved atomically with {len(self.chunks)} chunks (ver: {version_hash}).")

    def get_index_version(self) -> str:
        """Get the current index version hash, reloading if modified on disk."""
        self.check_and_reload()
        return self.manifest.get("index_version") or self.manifest.get("built_at") or "v1.0"

    def search(self, query_vec: np.ndarray, top_k: int = 5, active_doc_ids: List[int] = None) -> List[Tuple[Dict[str, Any], float]]:
        """
        Cosine similarity search with optional document ID filtering.
        Vectors are unit normalized, so cosine similarity is simply the dot product.
        """
        if self.vectors.size == 0 or len(self.chunks) == 0:
            return []

        # Cosine similarity via dot product
        scores = np.dot(self.vectors, query_vec)

        results = []
        for idx, score in enumerate(scores):
            chunk = self.chunks[idx]
            doc_id = chunk.get("doc_id")
            if active_doc_ids is not None and doc_id is not None and doc_id not in active_doc_ids:
                continue
            results.append((chunk, float(score)))

        # Sort descending by score
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]
