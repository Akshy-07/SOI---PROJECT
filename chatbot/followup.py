import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

FOLLOWUP_PREFIXES = (
    "and ", "and what ", "and how ", "what about ", "how about ", "also ",
    "for ", "in ", "at ", "on ", "is it ", "can i ", "does it ", "what if ",
    "and what is ", "and for "
)

FOLLOWUP_PRONOUNS = ("that", "this", "it", "them", "these", "those")

def is_followup_query(query: str) -> bool:
    """Determine whether a query is an elliptical or contextual follow-up question."""
    if not query:
        return False
    q_lower = query.lower().strip()

    # Starts with conjunction or preposition
    for prefix in FOLLOWUP_PREFIXES:
        if q_lower.startswith(prefix):
            return True

    # Contains reference pronouns in short queries
    tokens = q_lower.split()
    if len(tokens) <= 6:
        if any(p in tokens for p in FOLLOWUP_PRONOUNS):
            return True

    # Very short fragment without verb/subject (e.g. "for semester 2?", "in dsp?")
    if len(tokens) <= 4 and ("?" in query or len(tokens) <= 3):
        if not any(w in tokens for w in ["what", "who", "where", "when", "why", "how", "show", "tell"]):
            return True

    return False

def rewrite_query_deterministic(query: str, history: List[Dict[str, Any]]) -> str:
    """
    Deterministic rule-based rewriter transforming follow-ups into standalone queries.
    History contains session turns: [{'user_query': '...', 'route': '...'}]
    """
    if not history:
        return query

    # Find the most recent non-smalltalk user query
    last_turn = None
    for turn in reversed(history[-3:]):
        r = turn.get("route")
        if r != "smalltalk":
            last_turn = turn
            break

    if not last_turn:
        last_turn = history[-1]

    prev_query = (last_turn.get("user_query") or last_turn.get("query") or "").strip()
    if not prev_query:
        return query

    q_clean = query.strip()
    q_lower = q_clean.lower()

    # Remove trailing question mark for composition
    prev_base = prev_query.rstrip("?.! ")

    # Pattern 1: "and for <X>?" or "for <X>?" or "in <X>?" or "at <X>?"
    # Example: "What is the attendance requirement?" + "and for semester 2?"
    # -> "What is the attendance requirement for semester 2?"
    for conj in ["and ", "also ", "what about ", "how about "]:
        if q_lower.startswith(conj):
            q_clean = q_clean[len(conj):].strip()
            q_lower = q_clean.lower()
            break

    # If remainder starts with preposition (for, in, at, on, during)
    prep_match = re.match(r'^(for|in|at|on|during|of|with)\s+(.+)', q_lower)
    if prep_match:
        prep = prep_match.group(1)
        target = q_clean[len(prep):].strip()

        # If previous query already had that preposition, replace the target
        # e.g. "What are my marks in DSP?" + "in VLSI?" -> "What are my marks in VLSI?"
        pattern = re.compile(rf'\b{prep}\s+([A-Za-z0-9_\s]+)$', re.IGNORECASE)
        if pattern.search(prev_base):
            rewritten = pattern.sub(f"{prep} {target}", prev_base)
            return rewritten + ("?" if not rewritten.endswith("?") else "")
        else:
            return f"{prev_base} {prep} {target}" + ("?" if not target.endswith("?") else "")

    # Pattern 2: "what about <subject/topic>?"
    # e.g. "Show my attendance in DSP" + "what about VLSI?" -> "Show my attendance in VLSI?"
    tokens = q_clean.rstrip("?").split()
    if len(tokens) <= 3:
        # Short topic substitution
        subject_candidate = tokens[-1]
        for prep in ["in", "for", "of"]:
            pattern = re.compile(rf'\b{prep}\s+([A-Za-z0-9_]+)$', re.IGNORECASE)
            if pattern.search(prev_base):
                rewritten = pattern.sub(f"{prep} {subject_candidate}", prev_base)
                return rewritten + "?"

    # Pattern 3: Pronoun reference "after that", "for that", "about it"
    # e.g. "What about the hostel gate timings?" + "and what is the late fine after that?"
    # -> "what is the late fine after the hostel gate timings?"
    if any(p in q_lower for p in ["after that", "for that", "about it", "of that"]):
        topic_phrase = re.sub(r'^(what\s+is\s+|what\s+are\s+|what\s+about\s+|show\s+|tell\s+me\s+about\s+)', '', prev_base, flags=re.IGNORECASE).strip()
        rewritten = re.sub(r'\b(after\s+that|for\s+that|about\s+it|of\s+that)\b', f"for {topic_phrase}", q_clean, flags=re.IGNORECASE)
        return rewritten

    # Default concatenation fallback
    return f"{prev_base} {q_clean}"

def rewrite_query(
    query: str,
    history: List[Dict[str, Any]],
    provider_name: str = "mock"
) -> str:
    """
    Rewrite follow-up query to a standalone query.
    1. Deterministic rewriting first.
    2. LLM rewriting only if provider configured (OpenAI/Anthropic).
    3. Personal values must NEVER be inserted into the LLM prompt.
    4. Session-scoped context only.
    """
    if not is_followup_query(query) or not history:
        return query

    # Run deterministic rewriting first
    deterministic_result = rewrite_query_deterministic(query, history)

    # If provider is mock or not configured, return deterministic result
    provider_clean = (provider_name or "").lower().strip()
    if provider_clean not in ["openai", "anthropic"]:
        return deterministic_result

    # If external provider is configured, optionally use it with strict user-question-only prompt
    try:
        from ai.provider import get_provider
        provider = get_provider()
        if not provider or getattr(provider, "is_mock", False):
            return deterministic_result

        # Build prompt containing ONLY past user questions — ZERO personal data values
        recent_questions = []
        for turn in history[-3:]:
            uq = turn.get("user_query") or turn.get("query")
            if uq:
                recent_questions.append(uq)

        if not recent_questions:
            return deterministic_result

        history_str = "\n".join([f"- Previous question: {q}" for q in recent_questions])
        prompt = (
            "Rewrite the follow-up question into a complete, standalone question based on previous questions.\n"
            f"{history_str}\n"
            f"- Follow-up question: {query}\n"
            "Output ONLY the single rewritten question without commentary."
        )
        llm_rewritten = provider.generate(prompt, max_tokens=100)
        if llm_rewritten and len(llm_rewritten.strip()) > 5:
            return llm_rewritten.strip().strip('"')
    except Exception as e:
        logger.warning(f"LLM rewrite failed or unavailable ({e}); falling back to deterministic rewrite.")

    return deterministic_result
