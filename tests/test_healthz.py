import pytest

def test_healthz_endpoint_contract(client):
    """Verify /healthz reports database, index status, embedding backend, and LLM configuration without secrets."""
    response = client.get('/healthz')
    assert response.status_code in [200, 503]
    
    data = response.get_json()
    assert data is not None
    assert "status" in data
    assert "database" in data
    assert data["database"] == "connected"
    assert "index_status" in data
    assert data["index_status"] in ["ready", "empty", "unavailable"]
    assert "embedding_backend" in data
    assert "llm_provider" in data
    assert "llm_configured" in data
    assert isinstance(data["llm_configured"], bool)
    assert "timestamp" in data
    
    # Security checks: ensure NO secrets, NO API keys, and NO personal data appear in health output
    body_str = response.get_data(as_text=True)
    assert "sk-" not in body_str
    assert "SECRET" not in body_str
    assert "password" not in body_str.lower()
    assert "student_id" not in body_str
    assert "attendance" not in body_str.lower()
    assert "marks" not in body_str.lower()
