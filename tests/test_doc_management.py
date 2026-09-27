import os
import pytest
from rag.ingest import IngestionPipeline, validate_file

def test_upload_validation_rules():
    # Unsupported extension
    ok, msg = validate_file("malicious.exe", b"binary content")
    assert ok is False
    assert "Unsupported file type" in msg

    # File with PDF extension but wrong magic bytes
    ok, msg = validate_file("fake.pdf", b"This is plain text not PDF header")
    assert ok is False
    assert "magic bytes mismatch" in msg

    # Oversized file
    big_bytes = b"0" * (16 * 1024 * 1024)
    ok, msg = validate_file("big.txt", big_bytes, max_mb=15)
    assert ok is False
    assert "exceeds maximum size" in msg

def test_deduplication_by_sha256(temp_db, tmp_path):
    pipeline = IngestionPipeline(db_path=temp_db, index_dir=str(tmp_path))
    content = b"COLLEGE POLICY ON CONDUCT: All students must wear ID card."

    ok1, msg1, doc1 = pipeline.ingest_document(
        filename="policy1.txt",
        file_bytes=content,
        uploaded_by="Admin",
        storage_dir=os.path.join(str(tmp_path), "docs")
    )
    assert ok1 is True

    # Exact duplicate upload (even with different name)
    ok2, msg2, doc2 = pipeline.ingest_document(
        filename="policy_duplicate.txt",
        file_bytes=content,
        uploaded_by="Admin",
        storage_dir=os.path.join(str(tmp_path), "docs")
    )
    assert ok2 is False
    assert "Duplicate document" in msg2
