import pytest

REQUIRED_CONTRACT_KEYS = {
    "request_id", "reply", "answer", "route", "confidence",
    "sources", "offer_escalation", "generation_status", "latency_ms"
}

def validate_contract_shape(data):
    assert isinstance(data, dict)
    for key in REQUIRED_CONTRACT_KEYS:
        assert key in data, f"Missing required contract key: {key}"
    assert isinstance(data["request_id"], str)
    assert isinstance(data["reply"], str)
    assert isinstance(data["answer"], str)
    assert data["route"] in ["personal", "general", "hybrid", "smalltalk", "blocked"]
    assert data["confidence"] in ["high", "medium", "low", "none", "n/a"]
    assert isinstance(data["sources"], list)
    assert isinstance(data["offer_escalation"], bool)
    assert isinstance(data["generation_status"], str)
    assert isinstance(data["latency_ms"], int)

def test_contract_personal_route(client):
    client.post('/login', data={'username': '711724UEC101', 'password': 'password123'})
    res = client.post('/chat', json={'question': 'What is my attendance?'})
    assert res.status_code == 200
    data = res.get_json()
    validate_contract_shape(data)
    assert data['route'] == 'personal'
    assert data['confidence'] == 'high'
    assert data['reply'] == data['answer']
    client.get('/logout')

def test_contract_general_route(client):
    client.post('/login', data={'username': '711724UEC101', 'password': 'password123'})
    res = client.post('/chat', json={'question': 'What is the college attendance policy?'})
    assert res.status_code == 200
    data = res.get_json()
    validate_contract_shape(data)
    assert data['route'] == 'general'
    assert data['reply'] == data['answer']
    client.get('/logout')

def test_contract_hybrid_route(client):
    client.post('/login', data={'username': '711724UEC101', 'password': 'password123'})
    res = client.post('/chat', json={'question': 'Am I eligible to write the semester exam based on my attendance?'})
    assert res.status_code == 200
    data = res.get_json()
    validate_contract_shape(data)
    assert data['route'] == 'hybrid'
    assert '80.0%' in data['answer'] # Akshayaa personal attendance fact
    assert 'Deterministic Assessment' in data['answer'] # Structured rule verdict
    client.get('/logout')

def test_contract_smalltalk_route(client):
    client.post('/login', data={'username': '711724UEC101', 'password': 'password123'})
    res = client.post('/chat', json={'question': 'Hello!'})
    assert res.status_code == 200
    data = res.get_json()
    validate_contract_shape(data)
    assert data['route'] == 'smalltalk'
    assert data['confidence'] == 'n/a'
    client.get('/logout')

def test_contract_blocked_route(client):
    client.post('/login', data={'username': '711724UEC101', 'password': 'password123'})
    res = client.post('/chat', json={'question': 'What is marks of Rahul?'})
    assert res.status_code == 200
    data = res.get_json()
    validate_contract_shape(data)
    assert data['route'] == 'blocked'
    assert data['confidence'] == 'n/a'
    client.get('/logout')
