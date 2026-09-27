import pytest

def test_session_scoping_ignores_tampered_payload_fields(client):
    # Login as student Akshayaa (id 1, reg 711724UEC101)
    client.post('/login', data={'username': '711724UEC101', 'password': 'password123'})

    # Try to tamper with student_id in body
    tampered_payload = {
        'question': 'What is my attendance?',
        'student_id': 2, # Rahul's student_id
        'reg_no': '711724UEC102'
    }

    res = client.post('/chat', json=tampered_payload)
    assert res.status_code == 200
    data = res.get_json()

    # Must return Akshayaa's attendance (80.0%), never Rahul's (72.5%)
    assert '80.0%' in data['answer']
    assert '72.5%' not in data['answer']

    client.get('/logout')

def test_cross_student_name_query_is_blocked(client):
    # Login as student Akshayaa
    client.post('/login', data={'username': '711724UEC101', 'password': 'password123'})

    res = client.post('/chat', json={'question': 'What is marks of Rahul?'})
    assert res.status_code == 200
    data = res.get_json()

    assert data['route'] == 'blocked'
    assert 'Access Denied' in data['answer'] or 'Security Alert' in data['answer']

    client.get('/logout')

def test_unauthenticated_request_cannot_access_personal_data(client):
    res = client.post('/chat', json={'question': 'What is my attendance?'})
    assert res.status_code == 401
