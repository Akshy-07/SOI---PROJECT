import sqlite3
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

SAFE_PERSONAL_QUERY_TYPES = {
    "attendance": "PERSONAL_ATTENDANCE_QUERY",
    "marks": "PERSONAL_MARKS_QUERY",
    "fees": "PERSONAL_FEES_QUERY",
    "fee": "PERSONAL_FEES_QUERY",
    "timetable": "PERSONAL_TIMETABLE_QUERY",
    "schedule": "PERSONAL_TIMETABLE_QUERY",
    "leave": "PERSONAL_LEAVE_QUERY",
    "leave_status": "PERSONAL_LEAVE_QUERY",
    "od": "PERSONAL_LEAVE_QUERY"
}

def get_safe_query_type(sub_category: Optional[str] = None, question: Optional[str] = None) -> str:
    """Derive safe query type without leaking personal question text."""
    if sub_category:
        sub_cat_clean = sub_category.lower().strip()
        for key, safe_type in SAFE_PERSONAL_QUERY_TYPES.items():
            if key in sub_cat_clean:
                return safe_type

    if question:
        q_lower = question.lower()
        if "attendance" in q_lower:
            return "PERSONAL_ATTENDANCE_QUERY"
        elif "mark" in q_lower or "internal" in q_lower or "score" in q_lower or "grade" in q_lower:
            return "PERSONAL_MARKS_QUERY"
        elif "fee" in q_lower or "due" in q_lower or "fine" in q_lower:
            return "PERSONAL_FEES_QUERY"
        elif "timetable" in q_lower or "schedule" in q_lower or "period" in q_lower or "class" in q_lower:
            return "PERSONAL_TIMETABLE_QUERY"
        elif "leave" in q_lower or " od " in q_lower or "on-duty" in q_lower:
            return "PERSONAL_LEAVE_QUERY"

    return "PERSONAL_DATA_QUERY"

def log_audit_event(
    db_path: str,
    request_id: str,
    user_role: str,
    user_id: str,
    event_type: str,
    route: Optional[str] = None,
    question: Optional[str] = None,
    answer: Optional[str] = None,
    sources: Optional[List[Dict[str, Any]]] = None,
    confidence: Optional[str] = None,
    latency_ms: Optional[int] = None,
    status: str = "ok",
    sub_category: Optional[str] = None
):
    """
    Log an audit event with strict data minimization (Phase 8 & Section 6, Rule 4).
    For personal queries:
      - question is NEVER stored (neither full nor partial first 30 chars).
      - only safe query type (e.g. PERSONAL_ATTENDANCE_QUERY) is recorded.
      - answer is NEVER stored (no grades, percentages, marks, or fees).
    For hybrid queries:
      - personal attendance values are stripped from logged answer.
    """
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        logged_question = question
        logged_answer = answer

        if route == "personal":
            safe_type = get_safe_query_type(sub_category, question)
            logged_question = safe_type
            logged_answer = "[PERSONAL_DATA_SERVED_FROM_DB_DETERMINISTICALLY]"
        elif route == "hybrid":
            # For hybrid, ensure personal values (like "Your current overall attendance is 80.0%") are scrubbed
            logged_answer = "[HYBRID_QUERY_POLICY_AND_STUDENT_STATUS]"

        sources_json = json.dumps(sources) if sources else None
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cur.execute("""
            INSERT INTO audit_logs (
                request_id, ts, user_role, user_id, event_type, route,
                question, answer, sources_json, confidence, latency_ms, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request_id, ts, user_role, str(user_id), event_type, route,
            logged_question, logged_answer, sources_json, confidence, latency_ms, status
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")
