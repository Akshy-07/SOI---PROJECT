import time
import sqlite3
import pytest
from rag.ingest import IngestionPipeline

def test_async_ingestion_success(temp_db, tmp_path):
    """Test successful async ingestion: queued -> processing -> active/ready."""
    index_dir = str(tmp_path / "rag_index")
    pipeline = IngestionPipeline(db_path=temp_db, index_dir=index_dir)
    
    sample_content = (
        "COLLEGE HOSTEL REGULATIONS 2026\n"
        "Students must return to the hostel by 8:30 PM. Gate closes strictly at 9:00 PM.\n"
        "Late entry requires prior permission from the hostel warden."
    ).encode("utf-8")
    
    success, msg, doc_id = pipeline.ingest_document(
        filename="test_hostel_rules.txt",
        file_bytes=sample_content,
        uploaded_by="Admin",
        version="1.0",
        async_mode=True
    )
    
    assert success is True
    assert doc_id is not None
    assert "queued" in msg.lower()
    
    # Poll database for background worker completion (max 5 seconds)
    final_status = None
    for _ in range(50):
        time.sleep(0.1)
        conn = sqlite3.connect(temp_db)
        cur = conn.cursor()
        cur.execute("SELECT status, chunk_count FROM kb_documents WHERE id = ?", (doc_id,))
        row = cur.fetchone()
        conn.close()
        if row and row[0] in ["active", "ready", "failed"]:
            final_status = row[0]
            chunk_count = row[1]
            break
            
    assert final_status == "active", f"Expected document to transition to active, got {final_status}"
    assert chunk_count > 0, "Document chunks should be indexed"
    
    # Verify index exists and contains document chunks
    assert len(pipeline.vector_index.chunks) > 0

def test_async_ingestion_failure_does_not_corrupt_index(temp_db, tmp_path):
    """Test that a failed ingestion job transitions to 'failed' and does NOT corrupt the existing index."""
    index_dir = str(tmp_path / "rag_index")
    pipeline = IngestionPipeline(db_path=temp_db, index_dir=index_dir)
    
    # 1. Establish initial good index
    good_content = "COLLEGE CAMPUS SAFETY GUIDELINES\nEmergency helpline is 100. Medical centre open 24x7.".encode("utf-8")
    pipeline.ingest_document(
        filename="good_doc.txt",
        file_bytes=good_content,
        uploaded_by="Admin",
        version="1.0",
        async_mode=False
    )
    initial_chunks_count = len(pipeline.vector_index.chunks)
    assert initial_chunks_count > 0
    initial_index_version = pipeline.vector_index.get_index_version()
    
    # 2. Ingest corrupted empty document (which returns no pages)
    # Magic bytes valid for pdf header but corrupted zero-length body
    corrupt_pdf_bytes = b"%PDF-1.4\ncorrupted-unparseable-data\n%%EOF"
    
    # Temporarily monkeypatch load_document to return [] for this file to simulate parsing error
    import rag.ingest
    orig_load = rag.ingest.load_document
    def fail_load(path, ext):
        if "corrupt" in path:
            return []
        return orig_load(path, ext)
    rag.ingest.load_document = fail_load
    
    try:
        success, msg, doc_id = pipeline.ingest_document(
            filename="corrupt_document.pdf",
            file_bytes=corrupt_pdf_bytes,
            uploaded_by="Admin",
            version="1.0",
            async_mode=True
        )
        assert success is True
        
        # Poll for completion
        final_status = None
        for _ in range(50):
            time.sleep(0.1)
            conn = sqlite3.connect(temp_db)
            cur = conn.cursor()
            cur.execute("SELECT status FROM kb_documents WHERE id = ?", (doc_id,))
            row = cur.fetchone()
            conn.close()
            if row and row[0] in ["failed", "active"]:
                final_status = row[0]
                break
                
        assert final_status == "failed", f"Expected failed status, got {final_status}"
        
        # Verify existing index was NOT corrupted and is still usable
        pipeline.vector_index.check_and_reload()
        assert len(pipeline.vector_index.chunks) == initial_chunks_count, "Existing index must remain intact"
        assert pipeline.vector_index.get_index_version() == initial_index_version
    finally:
        rag.ingest.load_document = orig_load
