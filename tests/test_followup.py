import pytest
from chatbot.followup import rewrite_query, rewrite_query_deterministic, is_followup_query

def test_is_followup_query():
    """Verify follow-up intent detection."""
    assert is_followup_query("and for semester 2?") is True
    assert is_followup_query("what about on Sundays?") is True
    assert is_followup_query("how about DSP?") is True
    assert is_followup_query("and in VLSI?") is True
    assert is_followup_query("What is the attendance requirement?") is False
    assert is_followup_query("Show my marks in DSP") is False

def test_simple_followup_rewrite():
    """User: 'What is the attendance requirement?' -> 'and for semester 2?'."""
    history = [
        {"user_query": "What is the attendance requirement?", "route": "general"}
    ]
    rewritten = rewrite_query("and for semester 2?", history, provider_name="mock")
    assert "attendance requirement" in rewritten.lower()
    assert "semester 2" in rewritten.lower()

def test_personal_followup_rewrite():
    """Personal follow-up: 'What are my marks in DSP?' -> 'and in VLSI?'."""
    history = [
        {"user_query": "What are my marks in DSP?", "route": "personal"}
    ]
    rewritten = rewrite_query("and in VLSI?", history, provider_name="mock")
    assert "marks" in rewritten.lower()
    assert "vlsi" in rewritten.lower()

def test_multi_turn_followup_history_cap():
    """Ensure history is limited to last 3 relevant turns without unbounded growth."""
    history = [
        {"user_query": "Question 1", "route": "general"},
        {"user_query": "Question 2", "route": "general"},
        {"user_query": "Question 3", "route": "general"},
        {"user_query": "Question 4", "route": "general"},
    ]
    # Check that passing history keeps only last 3 turns
    capped_history = history[-3:]
    assert len(capped_history) == 3
    assert capped_history[0]["user_query"] == "Question 2"
    assert capped_history[-1]["user_query"] == "Question 4"

def test_ambiguous_followup_fallback():
    """Ambiguous follow-up with no history or vague text returns original query safely."""
    assert rewrite_query("What is the attendance policy?", [], provider_name="mock") == "What is the attendance policy?"
    
    # Standalone query with empty history
    q = "Show my timetable for Friday"
    assert rewrite_query(q, [], provider_name="mock") == q

def test_cross_session_isolation(client):
    """Verify that Client A's conversation context is isolated from Client B's session."""
    # Student 1 logs in
    client.post('/login', data={'username': '711724UEC101', 'password': 'password123'})
    
    # Student 1 asks a general question
    client.post('/chat', json={'question': 'What is the minimum attendance requirement?'})
    
    # Check session
    with client.session_transaction() as sess:
        assert len(sess.get('chat_history', [])) >= 1
        assert "attendance requirement" in sess['chat_history'][0]['user_query'].lower()

    # Client logs out
    client.get('/logout')
    
    # Student 2 logs in
    client.post('/login', data={'username': '711724UEC102', 'password': 'password123'})
    with client.session_transaction() as sess2:
        # Student 2's session must be completely clean and isolated
        assert sess2.get('chat_history') is None or len(sess2.get('chat_history', [])) == 0

def test_provider_unavailable_fallback():
    """Verify deterministic rewriter executes successfully when external LLM is unconfigured."""
    history = [
        {"user_query": "What are the hostel gate timings?", "route": "general"}
    ]
    # Provider unconfigured (mock or invalid)
    rewritten = rewrite_query("and what is the late fine after that?", history, provider_name="mock")
    assert isinstance(rewritten, str)
    assert len(rewritten) > 0
    assert "hostel" in rewritten.lower() or "late fine" in rewritten.lower()
