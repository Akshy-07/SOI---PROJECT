import os
import time
import uuid
import sqlite3
import logging
from typing import Dict, Any, Optional

from chatbot.router import QuestionRouter
from chatbot.personal_handler import handle_personal_query
from chatbot.rag_handler import RAGHandler
from chatbot.audit import log_audit_event

logger = logging.getLogger(__name__)

class ResponseComposer:
    def __init__(self, db_path: str, index_dir: str = None):
        self.db_path = db_path
        self.router = QuestionRouter()
        self.rag_handler = RAGHandler(db_path, index_dir=index_dir)

    def get_policy_rule(self, rule_key: str) -> Optional[float]:
        """Fetch configured threshold from policy_rules table (Fix F4)."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT value FROM policy_rules WHERE key = ?", (rule_key,))
            row = cur.fetchone()
            conn.close()
            if row:
                return float(row["value"])
        except Exception as e:
            logger.error(f"Error fetching policy rule {rule_key}: {e}")
        return None

    def compose_response(self, question: str, student_id: int, user_role: str = "student", student_reg: str = None) -> Dict[str, Any]:
        """
        Orchestrate validation -> router -> handler -> composer -> audit -> JSON contract.
        Always returns Section 4.1 compliant response.
        """
        start_time = time.time()
        request_id = str(uuid.uuid4())

        # Route classification
        route, sub_category, router_conf = self.router.route(question, logged_in_reg=student_reg)

        reply_text = ""
        confidence = "high"
        sources = []
        offer_escalation = False
        gen_status = "ok"

        # 1. Blocked Route
        if route == "blocked":
            confidence = "n/a"
            offer_escalation = False
            gen_status = "blocked_security"
            if sub_category == "cross_student_access":
                reply_text = "Access Denied: You are only permitted to access your own academic and personal records. Inquiring about other students' data is strictly prohibited."
            else:
                reply_text = "Security Alert: This request cannot be processed as it violates campus system security policies."

        # 2. Smalltalk Route
        elif route == "smalltalk":
            confidence = "n/a"
            offer_escalation = False
            gen_status = "smalltalk"
            q_lower = question.lower()
            if any(w in q_lower for w in ["thank", "thx"]):
                reply_text = "You're welcome! Feel free to ask if you need anything else regarding your courses, attendance, or college policies."
            elif any(w in q_lower for w in ["bye", "goodbye"]):
                reply_text = "Goodbye! Have a great day ahead."
            elif "who are you" in q_lower or "what can you do" in q_lower:
                reply_text = "I am the Smart College Assistant. I can look up your personal attendance, marks, fees, timetable, and leave requests, or answer questions about official college regulations and policies."
            else:
                reply_text = "Hello! How can I assist you with your academic details or college policy questions today?"

        # 3. Personal Route
        elif route == "personal":
            confidence = "high"
            offer_escalation = False
            gen_status = "deterministic_db"
            personal_res = handle_personal_query(self.db_path, student_id, sub_category)
            reply_text = personal_res.get("answer", "Personal record retrieved.")

        # 4. Hybrid Route (Fix F4: Questions needing both personal data and policy)
        elif route == "hybrid":
            # Deterministic personal fact
            personal_res = handle_personal_query(self.db_path, student_id, "attendance")
            avg_attendance = personal_res.get("facts", {}).get("avg_attendance")

            # General RAG policy answer
            rag_res = self.rag_handler.answer_query(question)
            confidence = rag_res.get("confidence", "medium")
            sources = rag_res.get("sources", [])
            offer_escalation = rag_res.get("offer_escalation", False)
            gen_status = rag_res.get("generation_status", "hybrid")

            personal_fact_str = f"Your current overall attendance is {avg_attendance:.1f}%." if avg_attendance is not None else "Could not retrieve attendance record."
            policy_rule_val = self.get_policy_rule("min_attendance_percent")

            # Deterministic verdict only if structured policy rule exists
            verdict_str = ""
            if policy_rule_val is not None and avg_attendance is not None:
                if avg_attendance >= policy_rule_val:
                    verdict_str = f"\n\nDeterministic Assessment: You MEET the requirement (Current: {avg_attendance:.1f}% vs Required: {policy_rule_val:.0f}%)."
                else:
                    shortage = policy_rule_val - avg_attendance
                    verdict_str = f"\n\nDeterministic Assessment: You DO NOT MEET the requirement (Current: {avg_attendance:.1f}% vs Required: {policy_rule_val:.0f}% — Shortage of {shortage:.1f}%)."

            reply_text = f"{personal_fact_str}\n\nCollege Policy:\n{rag_res.get('answer')}{verdict_str}"

        # 5. General Route (RAG)
        else:
            rag_res = self.rag_handler.answer_query(question)
            reply_text = rag_res.get("answer", "No reliable information found.")
            confidence = rag_res.get("confidence", "low")
            sources = rag_res.get("sources", [])
            offer_escalation = rag_res.get("offer_escalation", False)
            gen_status = rag_res.get("generation_status", "ok")

        latency_ms = int((time.time() - start_time) * 1000)

        # Audit Logging (Data minimisation enforced in audit module)
        log_audit_event(
            db_path=self.db_path,
            request_id=request_id,
            user_role=user_role,
            user_id=str(student_id),
            event_type="security_block" if route == "blocked" else "chat_query",
            route=route,
            question=question,
            answer=reply_text,
            sources=sources,
            confidence=confidence,
            latency_ms=latency_ms,
            status=gen_status
        )

        # Final Section 4.1 response contract
        return {
            "request_id": request_id,
            "reply": reply_text,
            "answer": reply_text,
            "route": route,
            "confidence": confidence,
            "sources": sources,
            "offer_escalation": offer_escalation,
            "generation_status": gen_status,
            "latency_ms": latency_ms
        }
