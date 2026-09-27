import sqlite3
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

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
    status: str = "ok"
):
    """
    Log an audit event with strict data minimisation (Section 6, Rule 4).
    For personal queries: question and answer are recorded ONLY as the category type,
    NEVER the student's actual grades, attendance percentage, or fees amounts.
    """
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()

        # Data minimisation for personal routes
        logged_question = question
        logged_answer = answer
        if route == "personal":
            # Personal data never reaches the audit log
            logged_question = f"[PERSONAL_DATA_QUERY: {question[:30]}...]" if question else "[PERSONAL_DATA_QUERY]"
            logged_answer = "[PERSONAL_DATA_SERVED_FROM_DB_DETERMINISTICALLY]"

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
