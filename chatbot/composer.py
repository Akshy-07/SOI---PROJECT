import os
import re
import time
import json
import uuid
import hashlib
import sqlite3
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

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

    # --- Phase 5: Answer Cache Implementation ---
    @staticmethod
    def normalize_and_hash_question(question: str) -> Tuple[str, str]:
        """Normalize question (lowercase, strip punctuation, collapse whitespace) and compute SHA-256 hash."""
        q_clean = re.sub(r'[^\w\s]', '', question.lower())
        q_norm = " ".join(q_clean.split())
        q_hash = hashlib.sha256(q_norm.encode('utf-8')).hexdigest()
        return q_norm, q_hash

    def get_cached_answer(self, q_hash: str, index_version: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached answer if index version matches current index."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute(
                "SELECT answer_json, index_version FROM answer_cache WHERE question_norm_hash = ?",
                (q_hash,)
            )
            row = cur.fetchone()
            conn.close()
            if row and row["index_version"] == index_version:
                return json.loads(row["answer_json"])
        except Exception as e:
            logger.error(f"Error reading answer_cache: {e}")
        return None

    def set_cached_answer(self, q_hash: str, answer_data: Dict[str, Any], index_version: str):
        """Store general RAG answer in answer_cache. Personal & hybrid queries are strictly excluded."""
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute("""
                INSERT INTO answer_cache (question_norm_hash, answer_json, index_version, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(question_norm_hash) DO UPDATE SET
                    answer_json = excluded.answer_json,
                    index_version = excluded.index_version,
                    created_at = excluded.created_at
            """, (q_hash, json.dumps(answer_data), index_version, now))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error writing to answer_cache: {e}")

    def invalidate_cache(self, current_index_version: Optional[str] = None):
        """Invalidate answer cache when documents or index change."""
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            if current_index_version:
                cur.execute("DELETE FROM answer_cache WHERE index_version != ?", (current_index_version,))
            else:
                cur.execute("DELETE FROM answer_cache")
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error invalidating answer_cache: {e}")

    def compose_response(self, question: str, student_id: int, user_role: str = "student", student_reg: str = None) -> Dict[str, Any]:
        """
        Orchestrate validation -> router -> cache check -> handler -> composer -> audit -> JSON contract.
        Always returns Section 4.1 compliant response with observability metrics.
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
        retrieval_ms = 0
        generation_ms = 0
        tokens_info = None
        estimated_cost_usd = None

        # 1. Blocked Route (Security firewall: zero model or DB execution)
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

        # 3. Personal Route (Scoped strictly to logged-in student; NEVER CACHED)
        elif route == "personal":
            confidence = "high"
            offer_escalation = False
            gen_status = "deterministic_db"
            personal_res = handle_personal_query(self.db_path, student_id, sub_category)
            reply_text = personal_res.get("answer", "Personal record retrieved.")

        # 4. Hybrid Route (Personal DB + Policy RAG; NEVER CACHED due to personal student data)
        elif route == "hybrid":
            # Deterministic personal fact from SQLite
            personal_res = handle_personal_query(self.db_path, student_id, "attendance")
            avg_attendance = personal_res.get("facts", {}).get("avg_attendance")

            # General RAG policy answer
            rag_res = self.rag_handler.answer_query(question)
            confidence = rag_res.get("confidence", "medium")
            sources = rag_res.get("sources", [])
            offer_escalation = rag_res.get("offer_escalation", False)
            gen_status = rag_res.get("generation_status", "hybrid")
            retrieval_ms = rag_res.get("retrieval_ms", 0)
            generation_ms = rag_res.get("generation_ms", 0)

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

        # 5. General Route (RAG with Answer Caching)
        else:
            q_norm, q_hash = self.normalize_and_hash_question(question)
            current_index_version = self.rag_handler.index.get_index_version()
            use_cache = os.environ.get("SEMANTIC_CACHE", "1") == "1"

            cached_entry = self.get_cached_answer(q_hash, current_index_version) if use_cache else None

            if cached_entry:
                # Cache HIT
                reply_text = cached_entry.get("answer", "")
                confidence = cached_entry.get("confidence", "high")
                sources = cached_entry.get("sources", [])
                offer_escalation = cached_entry.get("offer_escalation", False)
                gen_status = "cached"
            else:
                # Cache MISS - Execute live RAG
                rag_res = self.rag_handler.answer_query(question)
                reply_text = rag_res.get("answer", "No reliable information found.")
                confidence = rag_res.get("confidence", "low")
                sources = rag_res.get("sources", [])
                offer_escalation = rag_res.get("offer_escalation", False)
                gen_status = rag_res.get("generation_status", "ok")
                retrieval_ms = rag_res.get("retrieval_ms", 0)
                generation_ms = rag_res.get("generation_ms", 0)

                # Store in cache only for general answers with verified confidence
                if use_cache and confidence in ["high", "medium"]:
                    self.set_cached_answer(q_hash, {
                        "answer": reply_text,
                        "confidence": confidence,
                        "sources": sources,
                        "offer_escalation": offer_escalation,
                        "generation_status": gen_status
                    }, current_index_version)

        latency_ms = int((time.time() - start_time) * 1000)

        # Audit Logging (Strict data minimisation enforced)
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
            status=gen_status,
            sub_category=sub_category
        )

        # Structured Observability JSON logging (Phase 7 - Zero Personal Data)
        observability_log = {
            "event": "chat_request",
            "request_id": request_id,
            "route": route,
            "sub_category": sub_category if route != "personal" else None,
            "confidence": confidence,
            "generation_status": gen_status,
            "timings_ms": {
                "retrieval": retrieval_ms,
                "generation": generation_ms,
                "total": latency_ms
            },
            "tokens": tokens_info,
            "estimated_cost_usd": estimated_cost_usd
        }
        logger.info(json.dumps(observability_log))

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
            "latency_ms": latency_ms,
            "retrieval_ms": retrieval_ms,
            "generation_ms": generation_ms
        }
