import pytest
import sqlite3

def test_login_and_logout_student(client):
    # GET login page
    res = client.get('/login')
    assert res.status_code == 200
    assert b"College Portal Login" in res.data

    # POST valid student login
    res = client.post('/login', data={'username': '711724UEC101', 'password': 'password123'}, follow_redirects=True)
    assert res.status_code == 200
    assert b"Welcome, Akshayaa S" in res.data

    # Logout
    res = client.get('/logout', follow_redirects=True)
    assert res.status_code == 200
    assert b"You have been signed out." in res.data

def test_login_staff(client):
    res = client.post('/login', data={'username': 'staff', 'password': 'staff123'}, follow_redirects=True)
    assert res.status_code == 200
    assert b"Staff Dashboard" in res.data
    assert b"Department Students" in res.data
    client.get('/logout')

def test_login_admin(client):
    res = client.post('/login', data={'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
    assert res.status_code == 200
    assert b"Admin Dashboard" in res.data
    assert b"Knowledge Base" in res.data
    client.get('/logout')

def test_student_dashboard_views(client):
    # Login as student Akshayaa
    client.post('/login', data={'username': '711724UEC101', 'password': 'password123'}, follow_redirects=True)
    
    res = client.get('/student')
    assert res.status_code == 200
    # Check attendance rendering
    assert b"Digital Signal Processing" in res.data
    assert b"Microprocessors" in res.data
    assert b"90.0%" in res.data
    
    # Check marks rendering
    assert b"Internal Assessment Marks" in res.data
    assert b"103.0" in res.data # Akshayaa DSP total
    
    # Check fees rendering
    assert b"15000" in res.data # Due fee
    
    # Check timetable rendering
    assert b"Weekly Schedule" in res.data
    assert b"DSP Lab" in res.data
    
    client.get('/logout')

def test_student_leave_application_and_staff_approval(client):
    # Student logs in and applies for leave
    client.post('/login', data={'username': '711724UEC101', 'password': 'password123'}, follow_redirects=True)
    
    res = client.post('/student/leave/apply', data={
        'req_type': 'On-Duty (OD)',
        'from_date': '2026-10-10',
        'to_date': '2026-10-11',
        'reason': 'Paper presentation at IIT'
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b"Paper presentation at IIT" in res.data
    assert b"Application for On-Duty (OD) submitted successfully." in res.data
    client.get('/logout')

    # Staff logs in and approves the leave
    client.post('/login', data={'username': 'staff', 'password': 'staff123'}, follow_redirects=True)
    res = client.get('/staff')
    assert res.status_code == 200
    assert b"Paper presentation at IIT" in res.data

    # Approve request (ID 2 because ID 1 was seeded in init_db)
    res = client.post('/staff/leave/review/2', data={'action': 'Approved'}, follow_redirects=True)
    assert res.status_code == 200
    assert b"approved" in res.data.lower()
    client.get('/logout')

def test_old_chat_behavior_and_contract(client):
    # Unauthenticated /chat returns 401
    res = client.post('/chat', json={'question': 'What is my attendance?'})
    assert res.status_code == 401

    # Login as student
    client.post('/login', data={'username': '711724UEC101', 'password': 'password123'})

    # Attendance query
    res = client.post('/chat', json={'question': 'What is my attendance?'})
    assert res.status_code == 200
    data = res.get_json()
    assert 'reply' in data # Backwards compatibility field
    assert '80.0%' in data['reply']
    assert data['route'] == 'personal'

    # Marks query
    res = client.post('/chat', json={'question': 'What are my internal marks?'})
    assert res.status_code == 200
    data = res.get_json()
    assert 'reply' in data
    assert 'Digital Signal Processing' in data['reply']
    assert '103.0/110' in data['reply']

    # Fees query
    res = client.post('/chat', json={'question': 'Tell me about my fees'})
    assert res.status_code == 200
    data = res.get_json()
    assert 'reply' in data
    assert '15000' in data['reply']

    # Timetable query
    res = client.post('/chat', json={'question': 'Show my timetable schedule'})
    assert res.status_code == 200
    data = res.get_json()
    assert 'reply' in data
    assert 'DSP Lab' in data['reply']

    # Leave query
    res = client.post('/chat', json={'question': 'What is my leave request status?'})
    assert res.status_code == 200
    data = res.get_json()
    assert 'reply' in data
    assert 'Leave' in data['reply'] or 'On-Duty' in data['reply']

    # General question fallback
    res = client.post('/chat', json={'question': 'What is the college library timing?'})
    assert res.status_code == 200
    data = res.get_json()
    assert 'reply' in data
    assert data['route'] == 'general'

    client.get('/logout')
