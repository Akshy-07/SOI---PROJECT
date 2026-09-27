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

    def ingest_document(
        self,
        filename: str,
        file_bytes: bytes,
        uploaded_by: str,
        version: str = "1.0",
        effective_from: Optional[str] = None,
        effective_until: Optional[str] = None,
        supersedes_id: Optional[int] = None,
        storage_dir: str = None
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Ingest a document into SQLite and the vector index:
        1. Validate file format and size.
        2. Deduplicate by SHA-256 file_hash.
        3. Save file using UUID name in uploads folder.
        4. Insert into kb_documents table.
        5. Automatically deactivate superseded document if supersedes_id provided.
        6. Rebuild vector index atomically.
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

        # Scanned PDF check for initial status
        pages = load_document(saved_path, clean_ext)
        initial_status = "active"
        if pages and pages[0].get("needs_ocr"):
            initial_status = "needs_ocr"

        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Deactivate superseded document if specified
        if supersedes_id:
            cur.execute("UPDATE kb_documents SET status = 'inactive' WHERE id = ?", (supersedes_id,))

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

        # If document is active, rebuild index
        if initial_status == "active":
            self.rebuild_index()

        return True, "Uploaded and indexed successfully.", new_doc_id
