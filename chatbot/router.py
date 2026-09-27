import os
import re
import json
import logging
import numpy as np
from typing import Tuple, Dict, Any, List

from rag.embeddings import EmbeddingEngine

logger = logging.getLogger(__name__)

INTENTS_FILE = os.path.join(os.path.dirname(__file__), "intents.json")

class QuestionRouter:
    """
    3-Layer Hybrid Intent Router:
    Layer 1: Deterministic rules (keywords, regex, indicator phrases)
    Layer 2: Exemplar-similarity intent classifier (intents.json embeddings)
    Layer 3: Default fallback -> 'general'
    """
    def __init__(self, embedding_engine: EmbeddingEngine = None):
        self.embedding_engine = embedding_engine or EmbeddingEngine()
        self.exemplars: List[Dict[str, Any]] = []
        self.exemplar_vectors: np.ndarray = np.empty((0, 0), dtype=np.float32)
        self.load_exemplars()

    def load_exemplars(self):
        """Load labeled intent examples and pre-embed them for offline Layer 2 classification."""
        if not os.path.exists(INTENTS_FILE):
            return

        try:
            with open(INTENTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            all_examples = []
            for item in data.get("intents", []):
                intent_name = item["intent"]
                for ex in item["examples"]:
                    all_examples.append({
                        "intent": intent_name,
                        "text": ex
                    })

            self.exemplars = all_examples
            texts = [e["text"] for e in all_examples]
            self.exemplar_vectors = self.embedding_engine.embed_texts(texts)
        except Exception as e:
            logger.error(f"Failed to load intent exemplars: {e}")

    def route(self, question: str, logged_in_reg: str = None) -> Tuple[str, str, float]:
        """
        Route question into (route_name, sub_category, confidence_score).
        Routes: 'smalltalk', 'blocked', 'personal', 'hybrid', 'general'
        """
        q_lower = question.lower().strip()

        # ----------------- LAYER 1: DETERMINISTIC RULES -----------------
        # 1. Blocked: Attacks / Injections / Unauthorized Access
        attack_patterns = [
            r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
            r"system\s*prompt",
            r"dump\s+database",
            r"drop\s+table",
            r"select\s+\*\s+from",
            r"show\s+passwords",
            r"developer\s+mode"
        ]
        for pat in attack_patterns:
            if re.search(pat, q_lower):
                return "blocked", "injection_attempt", 1.0

        # Blocked: Cross-student data query attempts (e.g. asking for another student's marks/reg)
        reg_pattern = r"\b[0-9]{5,7}[a-z]{2,5}[0-9]{2,4}\b"
        found_regs = re.findall(reg_pattern, q_lower)
        for r in found_regs:
            if logged_in_reg and r != logged_in_reg.lower():
                return "blocked", "cross_student_access", 1.0

        name_probe = re.search(r"(?:marks|attendance|fees|phone|gpa|cgpa)\s+of\s+([a-zA-Z]+)", q_lower)
        if name_probe:
            probe_name = name_probe.group(1).lower()
            if probe_name not in ["my", "mine", "me", "the"]:
                return "blocked", "cross_student_access", 1.0

        # 2. Smalltalk
        q_clean = re.sub(r"[^\w\s]", "", q_lower).strip()
        smalltalk_phrases = {
            "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
            "how are you", "who are you", "what can you do", "thank you", "thanks", "bye", "goodbye"
        }
        if q_clean in smalltalk_phrases or any(q_clean.startswith(p + " ") or q_clean == p for p in ["hi", "hello", "hey"]):
            if len(q_clean.split()) <= 5:
                return "smalltalk", "conversation", 1.0

        # 3. Hybrid Eligibility: Combines personal state with policy requirements
        # e.g., "Am I eligible to write exam?", "Can I appear for semester exam with my attendance?"
        hybrid_indicators = ["am i eligible", "can i appear", "do i meet", "can i write the exam", "eligible to write", "eligible for exam", "satisfy the requirement"]
        for ind in hybrid_indicators:
            if ind in q_lower:
                if any(w in q_lower for w in ["attendance", "exam", "marks", "fee"]):
                    return "hybrid", "exam_eligibility", 0.95

        # 4. Personal vs General Rule Checks
        personal_pronouns = ["my", "mine", "i", "me"]
        has_personal = any(re.search(r"\b" + p + r"\b", q_lower) for p in personal_pronouns)

        general_indicators = [
            "policy", "minimum", "rule", "regulations", "general", "working hours",
            "library hours", "campus", "anti-ragging", "dress code", "refund policy",
            "hostel rules", "hod of", "principal", "how to apply for", "guidelines"
        ]
        has_general = any(ind in q_lower for ind in general_indicators)

        if has_general and not has_personal:
            return "general", "policy", 0.9

        # Personal domains
        if has_personal or not has_general:
            if "attendance" in q_lower or "present" in q_lower or "absent" in q_lower:
                return "personal", "attendance", 0.95
            if "mark" in q_lower or "internal" in q_lower or "score" in q_lower or "result" in q_lower:
                return "personal", "marks", 0.95
            if "fee" in q_lower or "dues" in q_lower or "tuition" in q_lower or "paid" in q_lower:
                return "personal", "fees", 0.95
            if "timetable" in q_lower or "schedule" in q_lower or "class today" in q_lower or "period" in q_lower:
                return "personal", "timetable", 0.95
            if "leave" in q_lower or "od" in q_lower or "on-duty" in q_lower or "permission" in q_lower:
                return "personal", "leave", 0.95

        # ----------------- LAYER 2: EXEMPLAR SIMILARITY CLASSIFIER -----------------
        if self.exemplar_vectors.size > 0 and len(self.exemplars) > 0:
            q_vec = self.embedding_engine.embed_query(question)
            scores = np.dot(self.exemplar_vectors, q_vec)
            best_idx = int(np.argmax(scores))
            best_score = float(scores[best_idx])
            best_intent = self.exemplars[best_idx]["intent"]

            if best_score > 0.45:
                # Map intent to sub-category
                sub_cat = "general"
                if best_intent == "personal":
                    for d in ["attendance", "marks", "fees", "timetable", "leave"]:
                        if d in q_lower:
                            sub_cat = d
                            break
                elif best_intent == "hybrid":
                    sub_cat = "exam_eligibility"
                return best_intent, sub_cat, best_score

        # ----------------- LAYER 3: DEFAULT FALLBACK -----------------
        return "general", "fallback", 0.5
