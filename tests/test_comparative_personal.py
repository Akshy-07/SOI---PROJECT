import pytest
from chatbot.personal_handler import handle_personal_query
from chatbot.followup import rewrite_query_deterministic

def test_comparative_attendance(temp_db):
    # Student 1 has subjects: DSP (72%), VLSI (92%), etc.
    res_low = handle_personal_query(temp_db, student_id=1, query_type="attendance", question="Which of my subjects has the lowest attendance?")
    assert res_low["status"] == "ok"
    assert "lowest attendance" in res_low["answer"].lower()
    assert "vlsi" in res_low["answer"].lower() or "70" in res_low["answer"]

    res_high = handle_personal_query(temp_db, student_id=1, query_type="attendance", question="Which subject has the highest attendance?")
    assert res_high["status"] == "ok"
    assert "highest attendance" in res_high["answer"].lower()
    assert "dsp" in res_high["answer"].lower() or "digital signal processing" in res_high["answer"].lower() or "90" in res_high["answer"]

    res_below = handle_personal_query(temp_db, student_id=1, query_type="attendance", question="Which subjects are below 75%?")
    assert res_below["status"] == "ok"
    assert "below 75%" in res_below["answer"].lower()

    res_comp = handle_personal_query(temp_db, student_id=1, query_type="attendance", question="Compare my attendance across subjects")
    assert res_comp["status"] == "ok"
    assert "comparison" in res_comp["answer"].lower() or "highest" in res_comp["answer"].lower()

    res_avg = handle_personal_query(temp_db, student_id=1, query_type="attendance", question="What is my average attendance?")
    assert res_avg["status"] == "ok"
    assert "average attendance" in res_avg["answer"].lower()

def test_comparative_marks(temp_db):
    res_high = handle_personal_query(temp_db, student_id=1, query_type="marks", question="Which subject has the highest marks?")
    assert res_high["status"] == "ok"
    assert "highest internal marks" in res_high["answer"].lower()

    res_low = handle_personal_query(temp_db, student_id=1, query_type="marks", question="Which subject has the lowest marks?")
    assert res_low["status"] == "ok"
    assert "lowest internal marks" in res_low["answer"].lower()

def test_comparative_fees(temp_db):
    res_due = handle_personal_query(temp_db, student_id=1, query_type="fees", question="When is it due?")
    assert res_due["status"] == "ok"
    assert "due date" in res_due["answer"].lower()
    assert "2026-10-15" in res_due["answer"]

def test_followup_rewriting_comparisons():
    # Attendance follow-up
    hist_att = [{"user_query": "What is my attendance?", "route": "personal", "sub_category": "attendance"}]
    rewritten_att = rewrite_query_deterministic("Which subject is the lowest?", hist_att)
    assert "lowest attendance" in rewritten_att.lower()

    # Marks follow-up
    hist_marks = [{"user_query": "What are my marks?", "route": "personal", "sub_category": "marks"}]
    rewritten_marks = rewrite_query_deterministic("Which is the highest?", hist_marks)
    assert "highest marks" in rewritten_marks.lower()

    # Fee follow-up
    hist_fee = [{"user_query": "How much fee do I have to pay?", "route": "personal", "sub_category": "fees"}]
    rewritten_fee = rewrite_query_deterministic("When is it due?", hist_fee)
    assert "due date" in rewritten_fee.lower() or "when" in rewritten_fee.lower()
