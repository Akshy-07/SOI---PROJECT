import json
import sqlite3
import pytest
from chatbot.composer import ResponseComposer

def test_answer_cache_hit_and_miss(temp_db):
    """Test answer cache miss on first question and hit on subsequent identical question."""
    composer = ResponseComposer(db_path=temp_db)
    
    # Clean answer cache
    composer.invalidate_cache()
    
    q = "What is the minimum attendance requirement for semester exams?"
    q_norm, q_hash = composer.normalize_and_hash_question(q)
    idx_ver = composer.rag_handler.index.get_index_version()
    
    # 1. First call: Cache miss
    res1 = composer.compose_response(question=q, student_id=1, user_role="student", student_reg="711724UEC101")
    assert res1["route"] == "general"
    assert res1["generation_status"] != "cached"
    
    # Verify entry in answer_cache table
    conn = sqlite3.connect(temp_db)
    cur = conn.cursor()
    cur.execute("SELECT answer_json, index_version FROM answer_cache WHERE question_norm_hash = ?", (q_hash,))
    row = cur.fetchone()
    conn.close()
    
    if res1["confidence"] in ["high", "medium"]:
        assert row is not None
        assert row[1] == idx_ver
        
        # 2. Second call: Cache hit
        res2 = composer.compose_response(question=q, student_id=1, user_role="student", student_reg="711724UEC101")
        assert res2["route"] == "general"
        assert res2["generation_status"] == "cached"
        assert res2["answer"] == res1["answer"]

def test_index_version_invalidation(temp_db):
    """Test that modifying index version invalidates cached answers."""
    composer = ResponseComposer(db_path=temp_db)
    q = "What are the rules regarding dress code on campus?"
    q_norm, q_hash = composer.normalize_and_hash_question(q)
    
    # Store with older index version
    composer.set_cached_answer(
        q_hash=q_hash,
        answer_data={"answer": "Wear formal uniform.", "confidence": "high", "sources": []},
        index_version="old_version_v1"
    )
    
    # Attempt read with current index version
    current_ver = composer.rag_handler.index.get_index_version()
    assert current_ver != "old_version_v1"
    
    cached = composer.get_cached_answer(q_hash, current_ver)
    assert cached is None, "Cache should not return answer when index version does not match"
    
    # Test explicit invalidate_cache
    composer.invalidate_cache(current_index_version=current_ver)
    conn = sqlite3.connect(temp_db)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM answer_cache WHERE index_version = 'old_version_v1'")
    assert cur.fetchone()[0] == 0
    conn.close()

def test_personal_and_hybrid_answers_never_cached(temp_db):
    """Verify that personal and hybrid answers containing private data are NEVER cached."""
    composer = ResponseComposer(db_path=temp_db)
    composer.invalidate_cache()
    
    # 1. Personal question
    personal_q = "What is my attendance percentage?"
    res_p = composer.compose_response(question=personal_q, student_id=1, user_role="student", student_reg="711724UEC101")
    assert res_p["route"] == "personal"
    
    # 2. Hybrid question
    hybrid_q = "Am I eligible to write the semester exam based on my attendance?"
    res_h = composer.compose_response(question=hybrid_q, student_id=1, user_role="student", student_reg="711724UEC101")
    assert res_h["route"] == "hybrid"
    
    # Verify answer_cache contains neither query
    _, p_hash = composer.normalize_and_hash_question(personal_q)
    _, h_hash = composer.normalize_and_hash_question(hybrid_q)
    
    conn = sqlite3.connect(temp_db)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM answer_cache WHERE question_norm_hash IN (?, ?)", (p_hash, h_hash))
    count = cur.fetchone()[0]
    conn.close()
    
    assert count == 0, "Personal and hybrid responses must NEVER be inserted into answer_cache"
