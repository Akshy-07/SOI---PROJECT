import sqlite3
import pytest
from chatbot.composer import ResponseComposer

def test_audit_personal_data_minimization(temp_db):
    """
    Test Phase 8 requirement:
    Verify that personal questions, partial question strings, and personal values
    (marks, attendance percentages, fees) NEVER appear in audit records.
    """
    composer = ResponseComposer(db_path=temp_db)
    
    # 1. Personal Attendance Query
    composer.compose_response(
        question="What is my attendance in Microprocessors & Microcontrollers?",
        student_id=1,
        user_role="student",
        student_reg="711724UEC101"
    )
    
    # 2. Personal Marks Query
    composer.compose_response(
        question="Show my internal marks in Digital Signal Processing",
        student_id=1,
        user_role="student",
        student_reg="711724UEC101"
    )
    
    # 3. Personal Fees Query
    composer.compose_response(
        question="How much college fee do I have due right now?",
        student_id=1,
        user_role="student",
        student_reg="711724UEC101"
    )
    
    # Inspect audit_logs table
    conn = sqlite3.connect(temp_db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT question, answer, route FROM audit_logs WHERE route = 'personal'")
    records = cur.fetchall()
    conn.close()
    
    assert len(records) >= 3
    
    for r in records:
        q_text = r["question"]
        ans_text = r["answer"]
        
        # 1. Question must be a safe category enum, NEVER the raw question
        assert q_text in [
            "PERSONAL_ATTENDANCE_QUERY",
            "PERSONAL_MARKS_QUERY",
            "PERSONAL_FEES_QUERY",
            "PERSONAL_TIMETABLE_QUERY",
            "PERSONAL_LEAVE_QUERY",
            "PERSONAL_DATA_QUERY"
        ]
        
        # Must not contain words from the student's question
        assert "Microprocessors" not in q_text
        assert "Digital Signal Processing" not in q_text
        assert "college fee" not in q_text
        assert "..." not in q_text  # Verifies pattern like `question[:30]...` was completely eradicated
        
        # 2. Answer must NEVER contain private numerical grades, percentages, or fee amounts
        assert ans_text == "[PERSONAL_DATA_SERVED_FROM_DB_DETERMINISTICALLY]"
        assert "80" not in ans_text
        assert "90" not in ans_text
        assert "15000" not in ans_text
        assert "%" not in ans_text

def test_audit_hybrid_data_minimization(temp_db):
    """Verify that hybrid answers in audit logs do not store personal attendance percentages."""
    composer = ResponseComposer(db_path=temp_db)
    composer.compose_response(
        question="Am I eligible to write the semester exam based on my attendance?",
        student_id=1,
        user_role="student",
        student_reg="711724UEC101"
    )
    
    conn = sqlite3.connect(temp_db)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT question, answer, route FROM audit_logs WHERE route = 'hybrid'")
    records = cur.fetchall()
    conn.close()
    
    assert len(records) >= 1
    for r in records:
        ans_text = r["answer"]
        # Scrubbed answer placeholder
        assert ans_text == "[HYBRID_QUERY_POLICY_AND_STUDENT_STATUS]"
        assert "%" not in ans_text
