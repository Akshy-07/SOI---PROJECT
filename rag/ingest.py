import os
import hashlib
import uuid
import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
from werkzeug.utils import secure_filename

from rag.loaders import load_document
from rag.chunking import chunk_text_structure_aware
from rag.embeddings import EmbeddingEngine
from rag.vector_index import VectorIndex

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt'}
MAGIC_BYTES = {
    'pdf': b'%PDF',
    'docx': b'PK\x03\x04',
}

def compute_file_hash(file_bytes: bytes) -> str:
    """Compute SHA-256 hash of file content for deduplication."""
    return hashlib.sha256(file_bytes).hexdigest()

def validate_file(filename: str, file_bytes: bytes, max_mb: int = 15) -> Tuple[bool, str]:
    """Validate file extension, size, and magic bytes."""
    if not filename or '.' not in filename:
        return False, "File must have a valid extension."

    ext = filename.rsplit('.', 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Unsupported file type .{ext}. Allowed: PDF, DOCX, TXT."

    if len(file_bytes) > max_mb * 1024 * 1024:
        return False, f"File exceeds maximum size of {max_mb}MB."

    if len(file_bytes) == 0:
        return False, "Uploaded file is empty."

    # Magic byte check
    if ext in MAGIC_BYTES:
        expected = MAGIC_BYTES[ext]
        if not file_bytes.startswith(expected):
            return False, f"File header does not match expected {ext.upper()} format (magic bytes mismatch)."

    return True, "Valid"

class IngestionPipeline:
    def __init__(self, db_path: str, index_dir: str = None):
        self.db_path = db_path
        self.vector_index = VectorIndex(index_dir=index_dir) if index_dir else VectorIndex()
        self.embedding_engine = EmbeddingEngine()

    def rebuild_index(self):
        """
        Rebuild index over all active documents in SQLite (Fix F1, F2).
        Refits TF-IDF vectorizer if backend is TF-IDF.
        Saves atomically with file locking.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        cur.execute("SELECT * FROM kb_documents WHERE status = 'active';")
        active_docs = cur.fetchall()

        all_chunks = []
        doc_ids = []

        for doc in active_docs:
            doc_id = doc["id"]
            file_path = doc["file_path"]
            file_name = doc["file_name"]
            file_type = doc["file_type"]
            version = doc["version"]

            if not os.path.exists(file_path):
                logger.warning(f"File {file_path} for doc #{doc_id} not found on disk. Skipping.")
                continue

            pages = load_document(file_path, file_type)
            doc_chunks = chunk_text_structure_aware(pages)
            for c in doc_chunks:
                c["doc_id"] = doc_id
                c["document_name"] = file_name
                c["version"] = version
                all_chunks.append(c)
            doc_ids.append(doc_id)

            # Update chunk_count in DB
            cur.execute("UPDATE kb_documents SET chunk_count = ? WHERE id = ?", (len(doc_chunks), doc_id))

        conn.commit()
        conn.close()

        if not all_chunks:
            self.vector_index.vectors = np.empty((0, 0), dtype=np.float32)
            self.vector_index.chunks = []
            self.vector_index.save_atomic(self.embedding_engine.backend, self.embedding_engine.model_name, [])
            return

        texts = [c["text"] for c in all_chunks]

        # Fix F1: Refit TF-IDF vectorizer over all active chunks and persist it
        if self.embedding_engine.backend == "tfidf":
            self.embedding_engine.fit_tfidf(texts)
            self.embedding_engine.save_tfidf(self.vector_index.vectorizer_path)

        vectors = self.embedding_engine.embed_texts(texts)
        self.vector_index.vectors = vectors
        self.vector_index.chunks = all_chunks
        self.vector_index.save_atomic(
            backend=self.embedding_engine.backend,
            model_name=self.embedding_engine.model_name,
            doc_ids=doc_ids
        )
        logger.info(f"Rebuilt index with {len(all_chunks)} chunks across {len(doc_ids)} active documents.")

        # Invalidate stale answer_cache entries (Phase 5)
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            new_idx_ver = self.vector_index.get_index_version()
            cur.execute("DELETE FROM answer_cache WHERE index_version != ?", (new_idx_ver,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Could not invalidate answer_cache during index rebuild: {e}")

    def _process_ingestion(self, new_doc_id: int, saved_path: str, clean_ext: str, supersedes_id: Optional[int]):
        """Background worker executing page extraction, OCR checks, and atomic index rebuild."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        try:
            # 1. Transition queued -> processing
            cur.execute("UPDATE kb_documents SET status = 'processing' WHERE id = ?", (new_doc_id,))
            conn.commit()

            # 2. Extract pages
            pages = load_document(saved_path, clean_ext)
            if not pages:
                cur.execute("UPDATE kb_documents SET status = 'failed' WHERE id = ?", (new_doc_id,))
                conn.commit()
                conn.close()
                logger.error(f"Extraction failed for doc #{new_doc_id}: no readable text extracted.")
                return

            initial_status = "active"
            if pages and pages[0].get("needs_ocr"):
                initial_status = "needs_ocr"

            # 3. Deactivate superseded document if specified
            if supersedes_id:
                cur.execute("UPDATE kb_documents SET status = 'inactive' WHERE id = ?", (supersedes_id,))

            cur.execute("UPDATE kb_documents SET status = ? WHERE id = ?", (initial_status, new_doc_id))
            conn.commit()
            conn.close()

            # 4. Rebuild vector index atomically if active
            if initial_status == "active":
                self.rebuild_index()
            logger.info(f"Ingestion succeeded for doc #{new_doc_id} with status '{initial_status}'.")

        except Exception as e:
            logger.error(f"Ingestion processing error for doc #{new_doc_id}: {e}")
            try:
                cur.execute("UPDATE kb_documents SET status = 'failed' WHERE id = ?", (new_doc_id,))
                conn.commit()
                conn.close()
            except Exception:
                pass

    def ingest_document(
        self,
        filename: str,
        file_bytes: bytes,
        uploaded_by: str,
        version: str = "1.0",
        effective_from: Optional[str] = None,
        effective_until: Optional[str] = None,
        supersedes_id: Optional[int] = None,
        storage_dir: str = None,
        async_mode: bool = False
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Ingest a document into SQLite and the vector index:
        1. Validate file format and size.
        2. Deduplicate by SHA-256 file_hash.
        3. Save file using UUID name in uploads folder.
        4. Insert into kb_documents table with initial status ('queued' if async, 'active' if sync).
        5. In async mode, dispatch to background thread (queued -> processing -> active/failed).
        """
        valid, msg = validate_file(filename, file_bytes)
        if not valid:
            return False, msg, None

        file_hash = compute_file_hash(file_bytes)

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Deduplication check
        cur.execute("SELECT id, file_name FROM kb_documents WHERE file_hash = ? AND status != 'deleted'", (file_hash,))
        existing = cur.fetchone()
        if existing:
            conn.close()
            return False, f"Duplicate document: exact identical content already uploaded as #{existing['id']} ('{existing['file_name']}').", None

        # Storage
        if not storage_dir:
            storage_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "uploads", "kb_docs")
        os.makedirs(storage_dir, exist_ok=True)

        clean_ext = filename.rsplit('.', 1)[1].lower()
        storage_name = f"{uuid.uuid4().hex}_{secure_filename(filename)}"
        saved_path = os.path.join(storage_dir, storage_name)

        with open(saved_path, "wb") as f:
            f.write(file_bytes)

        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        initial_status = "queued" if async_mode else "active"

        cur.execute("""
            INSERT INTO kb_documents (
                file_name, file_path, file_hash, file_type, version, uploaded_by,
                effective_from, effective_until, status, chunk_count, embedding_backend, supersedes_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            filename, saved_path, file_hash, clean_ext, version, uploaded_by,
            effective_from or None, effective_until or None, initial_status, 0,
            self.embedding_engine.backend, supersedes_id or None, created_at
        ))
        new_doc_id = cur.lastrowid
        conn.commit()
        conn.close()

        if async_mode:
            import threading
            worker_thread = threading.Thread(
                target=self._process_ingestion,
                args=(new_doc_id, saved_path, clean_ext, supersedes_id),
                daemon=True
            )
            worker_thread.start()
            return True, "Document uploaded and queued for background ingestion.", new_doc_id
        else:
            # Synchronous processing
            self._process_ingestion(new_doc_id, saved_path, clean_ext, supersedes_id)
            return True, "Uploaded and indexed successfully.", new_doc_id
