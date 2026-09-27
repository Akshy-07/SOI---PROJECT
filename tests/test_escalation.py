import pytest
import sqlite3

def test_full_escalation_and_faq_loop(client, temp_db):
    # 1. Student asks an unknown question
    client.post('/login', data={'username': '711724UEC101', 'password': 'password123'})
    res = client.post('/chat', json={'question': 'What are the rules for swimming pool membership?'})
    data = res.get_json()
    req_id = data['request_id']

    # 2. Student escalates query using request_id
    res_esc = client.post('/submit_unresolved_query', json={'request_id': req_id})
    assert res_esc.status_code == 200
    assert res_esc.get_json()['status'] == 'ok'

    # Verify query in DB is open
    conn = sqlite3.connect(temp_db)
    cur = conn.cursor()
    cur.execute("SELECT id, status, question FROM unresolved_queries ORDER BY id DESC LIMIT 1;")
    q_row = cur.fetchone()
    q_id = q_row[0]
    assert q_row[1] == 'open'
    conn.close()

    client.get('/logout')

    # 3. Staff logs in and views queries
    client.post('/login', data={'username': 'staff', 'password': 'staff123'})
    res_staff = client.get('/staff')
    assert res_staff.status_code == 200
    assert b"swimming pool" in res_staff.data

    # Staff resolves the query with promote_to_faq checked
    res_res = client.post(f'/staff/resolve_query/{q_id}', data={
        'staff_response': 'The campus swimming pool is open from 6am to 8am for students with valid sports pass.',
        'promote_to_faq': '1'
    }, follow_redirects=True)
    assert res_res.status_code == 200

    # Verify query is now resolved and draft FAQ created
    conn = sqlite3.connect(temp_db)
    cur = conn.cursor()
    cur.execute("SELECT status FROM unresolved_queries WHERE id = ?", (q_id,))
    assert cur.fetchone()[0] == 'resolved'

    cur.execute("SELECT id, status, question, answer FROM faq_entries WHERE source_query_id = ?", (q_id,))
    faq_row = cur.fetchone()
    assert faq_row is not None
    faq_id = faq_row[0]
    assert faq_row[1] == 'draft'
    conn.close()

    client.get('/logout')

    # 4. Admin logs in and approves FAQ entry
    client.post('/login', data={'username': 'admin', 'password': 'admin123'})
    res_adm = client.get('/admin')
    assert res_adm.status_code == 200
    assert b"swimming pool" in res_adm.data

    res_app = client.post(f'/admin/faq/approve/{faq_id}', follow_redirects=True)
    assert res_app.status_code == 200

    # Verify FAQ entry approved
    conn = sqlite3.connect(temp_db)
    cur = conn.cursor()
    cur.execute("SELECT status FROM faq_entries WHERE id = ?", (faq_id,))
    assert cur.fetchone()[0] == 'approved'
    conn.close()

    client.get('/logout')

    # 5. Student re-asks the question: Now it is answered with knowledge base citation!
    client.post('/login', data={'username': '711724UEC101', 'password': 'password123'})
    res_reask = client.post('/chat', json={'question': 'What are the rules for swimming pool membership?'})
    assert res_reask.status_code == 200
    reask_data = res_reask.get_json()
    assert "swimming pool" in reask_data['answer'].lower() or "sports pass" in reask_data['answer'].lower()
    client.get('/logout')
