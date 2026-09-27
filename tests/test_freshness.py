import os
import pytest
from rag.ingest import IngestionPipeline
from chatbot.rag_handler import RAGHandler, get_active_document_ids

def test_document_freshness_supersedes_and_date_filtering(temp_db, tmp_path):
    pipeline = IngestionPipeline(db_path=temp_db, index_dir=str(tmp_path))
    
    docs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample_docs")
    v1_path = os.path.join(docs_dir, "academic_regulations_2024_2025.txt")
    v2_path = os.path.join(docs_dir, "academic_regulations_2025_2026.txt")

    with open(v1_path, "rb") as f:
        v1_bytes = f.read()
    with open(v2_path, "rb") as f:
        v2_bytes = f.read()

    # 1. Ingest older version (v1)
    ok1, msg1, doc1_id = pipeline.ingest_document(
        filename="academic_regulations_2024_2025.txt",
        file_bytes=v1_bytes,
        uploaded_by="Admin",
        version="2024.1",
        storage_dir=os.path.join(str(tmp_path), "docs")
    )
    assert ok1 is True

    # 2. Ingest current version (v2) superseding v1
    ok2, msg2, doc2_id = pipeline.ingest_document(
        filename="academic_regulations_2025_2026.txt",
        file_bytes=v2_bytes,
        uploaded_by="Admin",
        version="2025.1",
        supersedes_id=doc1_id,
        storage_dir=os.path.join(str(tmp_path), "docs")
    )
    assert ok2 is True

    # Check active document IDs in DB: doc1 must be inactive, doc2 must be active
    active_ids = get_active_document_ids(temp_db)
    assert doc1_id not in active_ids
    assert doc2_id in active_ids

    # Query RAG: must cite v2 and return 75%
    rag_handler = RAGHandler(db_path=temp_db, index_dir=str(tmp_path))
    res = rag_handler.answer_query("What is the minimum attendance requirement for semester exams?")

    # Verify citation is ONLY for the active document
    source_names = [s["document_name"] for s in res.get("sources", [])]
    assert "academic_regulations_2025_2026.txt" in source_names
    assert "academic_regulations_2024_2025.txt" not in source_names
    assert "75%" in res.get("answer", "")
