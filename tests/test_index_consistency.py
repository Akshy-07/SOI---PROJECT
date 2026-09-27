import os
import json
import pytest
import numpy as np
from rag.vector_index import VectorIndex
from rag.embeddings import EmbeddingEngine

def test_manifest_creation_and_consistency(tmp_path):
    index = VectorIndex(index_dir=str(tmp_path))
    engine = EmbeddingEngine(backend="tfidf")

    corpus = ["Document one about college attendance", "Document two about library fine"]
    engine.fit_tfidf(corpus)
    vecs = engine.embed_texts(corpus)

    index.vectors = vecs
    index.chunks = [{"text": t, "doc_id": i+1} for i, t in enumerate(corpus)]
    index.save_atomic("tfidf", "tfidf-ngram", [1, 2])

    assert os.path.exists(index.manifest_path)
    with open(index.manifest_path, "r") as f:
        manifest = json.load(f)

    assert manifest["backend"] == "tfidf"
    assert manifest["chunk_count"] == 2
    assert set(manifest["doc_ids"]) == {1, 2}
    assert manifest["dim"] > 0

def test_tfidf_vocabulary_drift_prevention(tmp_path):
    """Verify that adding new documents refits the vectorizer over the updated corpus (Fix F1)."""
    index = VectorIndex(index_dir=str(tmp_path))
    engine = EmbeddingEngine(backend="tfidf")

    # Initial corpus
    initial_corpus = ["attendance policy in college"]
    engine.fit_tfidf(initial_corpus)
    initial_vocab_size = len(engine.tfidf_vectorizer.vocabulary_)

    # Updated corpus with new terminology
    updated_corpus = ["attendance policy in college", "quantum electronics laboratory syllabus"]
    engine.fit_tfidf(updated_corpus)
    updated_vocab_size = len(engine.tfidf_vectorizer.vocabulary_)

    # Vocabulary should expand to include new corpus terms
    assert updated_vocab_size > initial_vocab_size
    assert "quantum" in engine.tfidf_vectorizer.vocabulary_

def test_atomic_write_and_locking(tmp_path):
    """Verify index writes are atomic and no temp files are left behind (Fix F6)."""
    index = VectorIndex(index_dir=str(tmp_path))
    vecs = np.ones((2, 10), dtype=np.float32)
    index.vectors = vecs
    index.chunks = [{"chunk_id": "c1"}, {"chunk_id": "c2"}]
    index.save_atomic("tfidf", "test", [1])

    # No leftover .tmp files
    assert not os.path.exists(index.vectors_path + ".tmp")
    assert not os.path.exists(index.chunks_path + ".tmp")
    assert not os.path.exists(index.manifest_path + ".tmp")

    # Destination files exist
    assert os.path.exists(index.vectors_path)
    assert os.path.exists(index.chunks_path)
    assert os.path.exists(index.manifest_path)
