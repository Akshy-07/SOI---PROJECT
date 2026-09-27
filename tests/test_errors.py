import os
import pytest
import sqlite3
from rag.ingest import validate_file, IngestionPipeline
from ai.generator import generate_grounded_answer
from rag.vector_index import VectorIndex

def test_empty_and_very_long_questions(client):
    client.post('/login', data={'username': '711724UEC101', 'password': 'password123'})

    # 1. Empty question returns 400
    res_empty = client.post('/chat', json={'question': '   '})
    assert res_empty.status_code == 400
    data = res_empty.get_json()
    assert "Please enter a question" in data["answer"]

    # 2. Very long question capped safely at 500 chars without error
    long_question = "What is the policy? " * 100
    res_long = client.post('/chat', json={'question': long_question})
    assert res_long.status_code == 200
    data_long = res_long.get_json()
    assert data_long["route"] in ["general", "smalltalk"]

    client.get('/logout')

def test_nonsense_and_irrelevant_questions(client):
    client.post('/login', data={'username': '711724UEC101', 'password': 'password123'})

    # Nonsense question should have low or none confidence and offer escalation
    res = client.post('/chat', json={'question': 'asdkjhqwuey zxcbmznxbqwe klajsdh?'})
    assert res.status_code == 200
    data = res.get_json()
    assert data['confidence'] in ['low', 'none']
    assert data['offer_escalation'] is True
    assert "could not find reliable information" in data['answer'].lower()

    client.get('/logout')

def test_upload_edge_cases():
    # 1. Disguised extension (.pdf with exe content)
    ok, msg = validate_file("payload.pdf", b"MZ\x90\x00\x03\x00\x00\x00")
    assert ok is False
    assert "magic bytes mismatch" in msg

    # 2. Oversized file
    huge = b"A" * (16 * 1024 * 1024)
    ok, msg = validate_file("rules.pdf", huge, max_mb=15)
    assert ok is False
    assert "exceeds maximum size" in msg

    # 3. Empty file
    ok, msg = validate_file("empty.pdf", b"")
    assert ok is False

def test_extractive_mode_when_provider_unconfigured():
    """Verify graceful degradation to extractive mode when mock provider is active."""
    sample_chunks = [{
        "text": "The Central Library operates from 8:00 AM to 8:00 PM on all working days.",
        "score": 0.85,
        "document_name": "library_handbook.txt",
        "page": 1,
        "version": "1.0",
        "chunk_id": "c1"
    }]
    # With MockProvider, generator catches the provider exception and returns extractive quote
    result = generate_grounded_answer("What are library timings?", sample_chunks, backend="tfidf")
    assert result["generation_status"] == "extractive_fallback"
    assert "8:00 AM to 8:00 PM" in result["answer"]
    assert len(result["sources"]) > 0

def test_missing_or_corrupt_vector_index(tmp_path):
    # Vector index with no files loads gracefully
    empty_index = VectorIndex(index_dir=str(tmp_path / "nonexistent"))
    assert len(empty_index.chunks) == 0
    results = empty_index.search(query_vec=[0.1, 0.2])
    assert results == []
