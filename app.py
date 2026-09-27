import os
import sqlite3
import uuid
import logging
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, g
from werkzeug.security import check_password_hash, generate_password_hash
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from chatbot.composer import ResponseComposer
from rag.ingest import IngestionPipeline
from chatbot.audit import log_audit_event
from chatbot.followup import rewrite_query

logger = logging.getLogger(__name__)

app = Flask(__name__)

# Security & Config
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-dev-secret-key-college-erp')
app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('MAX_UPLOAD_MB', 15)) * 1024 * 1024
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
if os.environ.get('HTTPS') == '1':
    app.config['SESSION_COOKIE_SECURE'] = True

# CSRF Protection
csrf = CSRFProtect(app)

# Rate Limiting
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://"
)

DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')
INDEX_DIR = os.path.join(os.path.dirname(__file__), 'rag_index')
UPLOADS_DIR = os.path.join(os.path.dirname(__file__), 'static', 'uploads', 'kb_docs')

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL;")
        g.db.execute("PRAGMA busy_timeout=5000;")
    return g.db

@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# Singletons
_composer = None
_ingest_pipeline = None

def get_composer():
    global _composer
    if _composer is None or getattr(_composer, 'db_path', None) != DB_PATH:
        _composer = ResponseComposer(DB_PATH, index_dir=INDEX_DIR)
    return _composer

def get_pipeline():
    global _ingest_pipeline
    if _ingest_pipeline is None or getattr(_ingest_pipeline, 'db_path', None) != DB_PATH:
        _ingest_pipeline = IngestionPipeline(DB_PATH, index_dir=INDEX_DIR)
    return _ingest_pipeline

# Role Decorator
def role_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            role = session.get('role')
            if not role:
                if request.is_json or request.path.startswith('/api/') or request.path == '/chat':
                    return jsonify({'error': 'Unauthorized: Login required', 'request_id': str(uuid.uuid4())}), 401
                flash("Please log in to access this page.", "error")
                return redirect(url_for('login'))
            if role not in allowed_roles:
                if request.is_json or request.path.startswith('/api/') or request.path == '/chat':
                    return jsonify({'error': 'Forbidden: Insufficient privileges', 'request_id': str(uuid.uuid4())}), 403
                flash("Access denied: You do not have permission for this section.", "error")
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- Global Error Handlers (M6) ---
@app.errorhandler(400)
def bad_request_error(e):
    req_id = str(uuid.uuid4())
    if request.is_json or request.path.startswith('/api/') or request.path == '/chat':
        return jsonify({'error': 'Invalid request syntax or format.', 'request_id': req_id}), 400
    return render_template('error.html', error_title='400 Bad Request', error_message='The server could not understand the request.', request_id=req_id), 400

@app.errorhandler(401)
def unauthorized_error(e):
    req_id = str(uuid.uuid4())
    if request.is_json or request.path.startswith('/api/') or request.path == '/chat':
        return jsonify({'error': 'Unauthorized: Authentication required.', 'request_id': req_id}), 401
    return redirect(url_for('login'))

@app.errorhandler(403)
def forbidden_error(e):
    req_id = str(uuid.uuid4())
    if request.is_json or request.path.startswith('/api/') or request.path == '/chat':
        return jsonify({'error': 'Forbidden: Access denied.', 'request_id': req_id}), 403
    return render_template('error.html', error_title='403 Forbidden', error_message='You do not have permission to access this resource.', request_id=req_id), 403

@app.errorhandler(404)
def not_found_error(e):
    req_id = str(uuid.uuid4())
    if request.is_json or request.path.startswith('/api/') or request.path == '/chat':
        return jsonify({'error': 'Resource not found.', 'request_id': req_id}), 404
    return render_template('error.html', error_title='404 Not Found', error_message='The page or resource you requested could not be located.', request_id=req_id), 404

@app.errorhandler(429)
def ratelimit_handler(e):
    req_id = str(uuid.uuid4())
    if request.is_json or request.path.startswith('/api/') or request.path == '/chat':
        return jsonify({'error': 'Rate limit exceeded. Please wait a moment before sending more requests.', 'request_id': req_id}), 429
    flash("Too many requests. Please slow down and try again shortly.", "error")
    return render_template('login.html'), 429

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    req_id = str(uuid.uuid4())
    if request.is_json or request.path.startswith('/api/') or request.path == '/chat':
        return jsonify({'error': 'CSRF validation failed. Missing or invalid CSRF token.', 'request_id': req_id}), 400
    flash("Security token expired or missing. Please try submitting again.", "error")
    return redirect(request.referrer or url_for('login'))

@app.errorhandler(500)
def internal_server_error(e):
    req_id = str(uuid.uuid4())
    logger.error(f"[500 Error] Request ID {req_id}: {e}")
    if request.is_json or request.path.startswith('/api/') or request.path == '/chat':
        return jsonify({'error': 'An internal error occurred. Please contact system support.', 'request_id': req_id}), 500
    return render_template('error.html', error_title='500 Internal Server Error', error_message='A server error occurred. The incident has been recorded.', request_id=req_id), 500

# --- Authentication Routes ---
@app.route('/')
def index():
    if 'role' in session:
        if session['role'] == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif session['role'] == 'staff':
            return redirect(url_for('staff_dashboard'))
        elif session['role'] == 'student':
            return redirect(url_for('student_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("15/minute")
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cur.fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session.clear()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['name'] = user['name']

            if user['role'] == 'student':
                cur.execute("SELECT * FROM students WHERE id = ?", (user['student_id'],))
                stu = cur.fetchone()
                if stu:
                    session['student_id'] = stu['id']
                    session['reg'] = stu['reg_no']
                return redirect(url_for('student_dashboard'))
            elif user['role'] == 'staff':
                return redirect(url_for('staff_dashboard'))
            elif user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
        else:
            flash("Invalid register number/username or password.", "error")

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for('login'))

# --- Student Dashboard & Actions ---
@app.route('/student')
@role_required('student')
def student_dashboard():
    student_id = session.get('student_id')
    db = get_db()
    cur = db.cursor()

    cur.execute("SELECT * FROM students WHERE id = ?", (student_id,))
    student = cur.fetchone()

    cur.execute("SELECT * FROM attendance WHERE student_id = ?", (student_id,))
    attendance = cur.fetchall()
    avg_attendance = 0.0
    if attendance:
        avg_attendance = sum(a['percentage'] for a in attendance) / len(attendance)

    cur.execute("SELECT * FROM marks WHERE student_id = ?", (student_id,))
    marks = cur.fetchall()

    cur.execute("SELECT * FROM fees WHERE student_id = ?", (student_id,))
    fee = cur.fetchone()

    timetable = []
    if student:
        cur.execute("SELECT * FROM timetable WHERE department = ? AND semester = ?", (student['dept'], student['semester']))
        timetable = cur.fetchall()

    cur.execute("SELECT * FROM leave_requests WHERE student_id = ? ORDER BY id DESC", (student_id,))
    leaves = cur.fetchall()
    pending_leaves = [l for l in leaves if l['status'] == 'Pending']

    cur.execute("SELECT * FROM unresolved_queries WHERE student_id = ? ORDER BY id DESC", (student_id,))
    student_queries = cur.fetchall()

    return render_template('student.html',
                           student=student,
                           attendance=attendance,
                           avg_attendance=avg_attendance,
                           marks=marks,
                           fee=fee,
                           timetable=timetable,
                           leaves=leaves,
                           pending_leaves=pending_leaves,
                           student_queries=student_queries)

@app.route('/student/leave/apply', methods=['POST'])
@role_required('student')
def student_apply_leave():
    student_id = session.get('student_id')
    req_type = request.form.get('req_type', 'Leave')
    from_date = request.form.get('from_date')
    to_date = request.form.get('to_date')
    reason = request.form.get('reason', '').strip()

    if not from_date or not to_date or not reason:
        flash("All fields are required to apply for Leave / OD.", "error")
        return redirect(url_for('student_dashboard'))

    db = get_db()
    cur = db.cursor()
    applied_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        INSERT INTO leave_requests (student_id, req_type, from_date, to_date, reason, status, applied_at)
        VALUES (?, ?, ?, ?, ?, 'Pending', ?)
    """, (student_id, req_type, from_date, to_date, reason, applied_at))
    db.commit()

    flash(f"Application for {req_type} submitted successfully.", "success")
    return redirect(url_for('student_dashboard'))

# --- Staff Dashboard & Actions ---
@app.route('/staff')
@role_required('staff')
def staff_dashboard():
    db = get_db()
    cur = db.cursor()

    cur.execute("SELECT * FROM students ORDER BY reg_no ASC")
    students_raw = cur.fetchall()
    students = []
    for s in students_raw:
        cur.execute("SELECT AVG(percentage) as avg_p FROM attendance WHERE student_id = ?", (s['id'],))
        row = cur.fetchone()
        avg_att = row['avg_p'] if row and row['avg_p'] is not None else 0.0

        cur.execute("SELECT status FROM fees WHERE student_id = ?", (s['id'],))
        fee_row = cur.fetchone()
        fee_status = fee_row['status'] if fee_row else 'N/A'

        s_dict = dict(s)
        s_dict['avg_att'] = avg_att
        s_dict['fee_status'] = fee_status
        students.append(s_dict)

    cur.execute("""
        SELECT l.*, s.name, s.reg_no
        FROM leave_requests l
        JOIN students s ON l.student_id = s.id
        ORDER BY l.id DESC
    """)
    leaves = cur.fetchall()

    cur.execute("""
        SELECT q.*, s.name as student_name
        FROM unresolved_queries q
        JOIN students s ON q.student_id = s.id
        ORDER BY q.id DESC
    """)
    queries = cur.fetchall()
    open_queries_count = sum(1 for q in queries if q['status'] == 'open')

    return render_template('staff.html',
                           students=students,
                           leaves=leaves,
                           queries=queries,
                           open_queries_count=open_queries_count)

@app.route('/staff/queries')
@role_required('staff', 'admin')
def staff_queries_api():
    status_filter = request.args.get('status')
    db = get_db()
    cur = db.cursor()
    if status_filter:
        cur.execute("SELECT * FROM unresolved_queries WHERE status = ? ORDER BY id DESC", (status_filter,))
    else:
        cur.execute("SELECT * FROM unresolved_queries ORDER BY id DESC")
    queries = [dict(q) for q in cur.fetchall()]
    return jsonify({'queries': queries})

@app.route('/staff/leave/review/<int:leave_id>', methods=['POST'])
@role_required('staff')
def staff_review_leave(leave_id):
    action = request.form.get('action')
    if action not in ['Approved', 'Rejected']:
        flash("Invalid action.", "error")
        return redirect(url_for('staff_dashboard'))

    db = get_db()
    cur = db.cursor()
    cur.execute("""
        UPDATE leave_requests
        SET status = ?, reviewed_by = ?
        WHERE id = ?
    """, (action, session.get('name', 'Staff'), leave_id))
    db.commit()
    flash(f"Leave request #{leave_id} {action.lower()}.", "success")
    return redirect(url_for('staff_dashboard'))

@app.route('/staff/resolve_query/<int:query_id>', methods=['POST'])
@role_required('staff', 'admin')
def staff_resolve_query(query_id):
    staff_response = request.form.get('staff_response', '').strip()
    promote_to_faq = request.form.get('promote_to_faq') == '1'

    if not staff_response:
        flash("Staff response cannot be empty.", "error")
        return redirect(url_for('staff_dashboard'))

    db = get_db()
    cur = db.cursor()
    resolved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cur.execute("""
        UPDATE unresolved_queries
        SET staff_response = ?, reviewed_by = ?, status = 'resolved', resolved_at = ?
        WHERE id = ?
    """, (staff_response, session.get('name', 'Staff'), resolved_at, query_id))

    if promote_to_faq:
        cur.execute("SELECT question FROM unresolved_queries WHERE id = ?", (query_id,))
        q_row = cur.fetchone()
        if q_row:
            cur.execute("""
                INSERT INTO faq_entries (question, answer, source_query_id, approved_by, status, created_at)
                VALUES (?, ?, ?, NULL, 'draft', ?)
            """, (q_row['question'], staff_response, query_id, resolved_at))

    db.commit()
    flash(f"Query #{query_id} resolved successfully.", "success")
    return redirect(url_for('staff_dashboard'))

# --- Admin Dashboard & Actions ---
@app.route('/admin')
@role_required('admin')
def admin_dashboard():
    db = get_db()
    cur = db.cursor()

    cur.execute("SELECT * FROM students ORDER BY reg_no ASC")
    students = cur.fetchall()

    cur.execute("SELECT * FROM kb_documents ORDER BY id DESC")
    documents = cur.fetchall()

    cur.execute("SELECT * FROM faq_entries ORDER BY id DESC")
    faqs = cur.fetchall()

    cur.execute("SELECT COUNT(*) FROM unresolved_queries WHERE status = 'open'")
    open_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM unresolved_queries WHERE status = 'resolved'")
    resolved_count = cur.fetchone()[0]
    monitor = {
        'open_count': open_count,
        'resolved_count': resolved_count,
        'median_time': '12 mins' if resolved_count > 0 else 'N/A'
    }

    cur.execute("""
        SELECT question, COUNT(*) as count, MAX(ts) as last_asked
        FROM audit_logs
        WHERE confidence IN ('low', 'none') AND question IS NOT NULL
        GROUP BY question
        ORDER BY count DESC
        LIMIT 5
    """)
    knowledge_gaps = cur.fetchall()

    # Filtered audit logs
    filter_event = request.args.get('event_type', '')
    if filter_event:
        cur.execute("SELECT * FROM audit_logs WHERE event_type = ? ORDER BY id DESC LIMIT 50", (filter_event,))
    else:
        cur.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 50")
    audit_logs = cur.fetchall()

    cur.execute("SELECT * FROM policy_rules ORDER BY key ASC")
    policy_rules = cur.fetchall()

    active_backend = os.environ.get('EMBEDDING_BACKEND', 'tfidf')
    indexed_doc_count = sum(1 for d in documents if d['status'] == 'active')
    total_chunk_count = sum(d['chunk_count'] or 0 for d in documents if d['status'] == 'active')

    return render_template('admin.html',
                           students=students,
                           documents=documents,
                           faqs=faqs,
                           monitor=monitor,
                           knowledge_gaps=knowledge_gaps,
                           audit_logs=audit_logs,
                           policy_rules=policy_rules,
                           active_backend=active_backend,
                           indexed_doc_count=indexed_doc_count,
                           total_chunk_count=total_chunk_count,
                           index_mismatch_warning=False,
                           filter_event=filter_event)

@app.route('/admin/student/add', methods=['POST'])
@role_required('admin')
def admin_add_student():
    reg_no = request.form.get('reg_no', '').strip()
    name = request.form.get('name', '').strip()
    dept = request.form.get('dept', '').strip()
    semester = int(request.form.get('semester', 1))
    email = request.form.get('email', '').strip()
    phone = request.form.get('phone', '').strip()

    if not reg_no or not name:
        flash("Register number and name are required.", "error")
        return redirect(url_for('admin_dashboard'))

    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("""
            INSERT INTO students (reg_no, name, dept, semester, email, phone)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (reg_no, name, dept, semester, email, phone))
        stu_id = cur.lastrowid

        pwd_hash = generate_password_hash("password123")
        cur.execute("""
            INSERT INTO users (username, password_hash, role, name, student_id)
            VALUES (?, ?, 'student', ?, ?)
        """, (reg_no, pwd_hash, name, stu_id))

        db.commit()
        flash(f"Student {name} ({reg_no}) registered successfully.", "success")
    except sqlite3.IntegrityError:
        flash(f"Student with Register Number {reg_no} already exists.", "error")

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/kb/upload', methods=['POST'])
@role_required('admin')
def admin_upload_kb():
    if 'file' not in request.files:
        flash("No file selected for upload.", "error")
        return redirect(url_for('admin_dashboard'))

    file = request.files['file']
    if not file or not file.filename:
        flash("Please select a document file.", "error")
        return redirect(url_for('admin_dashboard'))

    version = request.form.get('version', '1.0').strip()
    effective_from = request.form.get('effective_from') or None
    effective_until = request.form.get('effective_until') or None
    supersedes_id_raw = request.form.get('supersedes_id')
    supersedes_id = int(supersedes_id_raw) if supersedes_id_raw else None

    file_bytes = file.read()
    pipeline = get_pipeline()
    success, msg, doc_id = pipeline.ingest_document(
        filename=file.filename,
        file_bytes=file_bytes,
        uploaded_by=session.get('name', 'Admin'),
        version=version,
        effective_from=effective_from,
        effective_until=effective_until,
        supersedes_id=supersedes_id,
        async_mode=True
    )

    if success:
        flash(f"Document #{doc_id} ('{file.filename}') uploaded and queued for background processing.", "success")
    else:
        flash(f"Upload rejected: {msg}", "error")

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/kb/toggle/<int:doc_id>', methods=['POST'])
@role_required('admin')
def admin_toggle_kb(doc_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT status FROM kb_documents WHERE id = ?", (doc_id,))
    row = cur.fetchone()
    if row:
        new_status = 'inactive' if row['status'] == 'active' else 'active'
        cur.execute("UPDATE kb_documents SET status = ? WHERE id = ?", (new_status, doc_id))
        db.commit()
        pipeline = get_pipeline()
        pipeline.rebuild_index()
        flash(f"Document #{doc_id} status updated to {new_status} and index refreshed.", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/kb/delete/<int:doc_id>', methods=['POST'])
@role_required('admin')
def admin_delete_kb(doc_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT file_path FROM kb_documents WHERE id = ?", (doc_id,))
    row = cur.fetchone()
    if row and os.path.exists(row['file_path']):
        try:
            os.remove(row['file_path'])
        except Exception:
            pass

    cur.execute("DELETE FROM kb_documents WHERE id = ?", (doc_id,))
    db.commit()

    pipeline = get_pipeline()
    pipeline.rebuild_index()
    flash(f"Document #{doc_id} deleted and index rebuilt.", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/kb/reindex/<int:doc_id>', methods=['POST'])
@role_required('admin')
def admin_reindex_doc(doc_id):
    pipeline = get_pipeline()
    pipeline.rebuild_index()
    flash(f"Index rebuilt successfully.", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/kb/reindex_all', methods=['POST'])
@role_required('admin')
def admin_reindex_all():
    pipeline = get_pipeline()
    pipeline.rebuild_index()
    flash("Re-indexed all active documents successfully.", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/faq/approve/<int:faq_id>', methods=['POST'])
@role_required('admin')
def admin_approve_faq(faq_id):
    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT question, answer FROM faq_entries WHERE id = ?", (faq_id,))
    row = cur.fetchone()
    if row:
        cur.execute("""
            UPDATE faq_entries
            SET status = 'approved', approved_by = ?
            WHERE id = ?
        """, (session.get('name', 'Admin'), faq_id))
        db.commit()

        # Ingest approved FAQ entry as trusted text document into KB
        faq_text = f"COLLEGE FAQ (APPROVED):\nQUESTION: {row['question']}\nOFFICIAL ANSWER: {row['answer']}"
        faq_bytes = faq_text.encode('utf-8')
        pipeline = get_pipeline()
        pipeline.ingest_document(
            filename=f"college_faq_{faq_id}.txt",
            file_bytes=faq_bytes,
            uploaded_by="FAQ Approval Workflow",
            version=datetime.now().strftime("%Y%m%d")
        )

        flash(f"FAQ entry #{faq_id} approved and indexed into Knowledge Base as trusted source.", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/policy_rule/update', methods=['POST'])
@role_required('admin')
def admin_update_policy_rule():
    key = request.form.get('key', '').strip()
    try:
        value = float(request.form.get('value', 0))
    except ValueError:
        flash("Value must be a numeric threshold.", "error")
        return redirect(url_for('admin_dashboard'))
    unit = request.form.get('unit', '%').strip()

    if not key:
        flash("Rule key is required.", "error")
        return redirect(url_for('admin_dashboard'))

    db = get_db()
    cur = db.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        INSERT INTO policy_rules (key, value, unit, updated_by, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            unit = excluded.unit,
            updated_by = excluded.updated_by,
            updated_at = excluded.updated_at
    """, (key, value, unit, session.get('name', 'Admin'), now))
    db.commit()
    flash(f"Policy rule '{key}' updated to {value}{unit}.", "success")
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/audit')
@role_required('admin')
def admin_audit_logs():
    return redirect(url_for('admin_dashboard', event_type=request.args.get('event_type', '')))

# --- Hybrid /chat Route (Section 4.1 Contract) ---
@app.route('/chat', methods=['POST'])
@limiter.limit(os.environ.get("CHAT_RATE_LIMIT", "20/minute"))
@role_required('student')
def chat():
    """
    Production /chat endpoint returning Section 4.1 JSON Contract.
    """
    data = request.get_json(silent=True) or {}
    raw_question = (data.get('question') or data.get('message') or '')

    # Enforce character cap
    max_chars = int(os.environ.get("MAX_CHAT_CHARS", 500))
    question = raw_question[:max_chars].strip()

    if not question:
        return jsonify({
            "request_id": str(uuid.uuid4()),
            "reply": "Please enter a question to ask the assistant.",
            "answer": "Please enter a question to ask the assistant.",
            "route": "general",
            "confidence": "none",
            "sources": [],
            "offer_escalation": False,
            "generation_status": "empty_input",
            "latency_ms": 0
        }), 400

    student_id = session.get('student_id')
    student_reg = session.get('reg')

    # Session-scoped follow-up query rewriting (Phase 6)
    chat_history = session.get('chat_history', [])
    provider_name = os.environ.get('LLM_PROVIDER', 'mock')
    standalone_question = rewrite_query(question, chat_history, provider_name=provider_name)

    composer = get_composer()
    response_data = composer.compose_response(
        question=standalone_question,
        student_id=student_id,
        user_role='student',
        student_reg=student_reg
    )

    # Maintain last 3 relevant turns in session (ZERO personal data values stored in session)
    chat_history.append({
        "user_query": question,
        "rewritten_query": standalone_question,
        "route": response_data.get("route")
    })
    session['chat_history'] = chat_history[-3:]
    session.modified = True

    return jsonify(response_data)

# --- Escalation & Feedback Routes ---
@app.route('/submit_unresolved_query', methods=['POST'])
@role_required('student')
def submit_unresolved_query():
    data = request.get_json(silent=True) or {}
    req_id = data.get('request_id')
    student_id = session.get('student_id')
    reg = session.get('reg')

    if not req_id:
        return jsonify({'error': 'request_id is required'}), 400

    db = get_db()
    cur = db.cursor()
    question = "Unresolved student query"
    bot_reply = "No response"
    route = "general"
    confidence = "low"

    cur.execute("SELECT question, answer, route, confidence FROM audit_logs WHERE request_id = ?", (req_id,))
    row = cur.fetchone()
    if row:
        question = row['question'] or question
        bot_reply = row['answer'] or bot_reply
        route = row['route'] or route
        confidence = row['confidence'] or confidence

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        INSERT INTO unresolved_queries (student_id, reg, question, chatbot_response, route, confidence, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'open', ?)
    """, (student_id, reg, question, bot_reply, route, confidence, now))
    db.commit()

    return jsonify({'status': 'ok', 'message': 'Query escalated to staff successfully.'})

@app.route('/chat/feedback', methods=['POST'])
@role_required('student')
def chat_feedback():
    data = request.get_json(silent=True) or {}
    req_id = data.get('request_id')
    try:
        rating = int(data.get('rating', 0))
    except (ValueError, TypeError):
        rating = 0
    comment = data.get('comment', '')
    student_id = session.get('student_id')

    if not req_id or rating not in [-1, 1]:
        return jsonify({'error': 'Invalid feedback submission. Rating must be 1 or -1.'}), 400

    db = get_db()
    cur = db.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur.execute("""
        INSERT INTO chat_feedback (request_id, student_id, rating, comment, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (req_id, student_id, rating, comment, now))
    db.commit()

    return jsonify({'status': 'ok'})

@app.route('/healthz')
def healthz():
    db_ok = False
    try:
        db = get_db()
        cur = db.cursor()
        cur.execute("SELECT 1;")
        db_ok = True
    except Exception:
        pass

    # Check vector index status (Phase 11)
    index_status = "unavailable"
    index_chunk_count = 0
    index_version = "none"
    try:
        pipeline = get_pipeline()
        if pipeline and pipeline.vector_index:
            pipeline.vector_index.check_and_reload()
            index_chunk_count = len(pipeline.vector_index.chunks)
            index_version = pipeline.vector_index.get_index_version()
            index_status = "ready" if index_chunk_count > 0 else "empty"
    except Exception:
        pass

    # Check LLM provider configuration (zero secret exposure)
    provider_name = os.environ.get('LLM_PROVIDER', 'mock').lower()
    if provider_name == 'mock':
        llm_configured = True
    elif provider_name == 'openai':
        llm_configured = bool(os.environ.get('OPENAI_API_KEY'))
    elif provider_name == 'anthropic':
        llm_configured = bool(os.environ.get('ANTHROPIC_API_KEY'))
    else:
        llm_configured = False

    is_healthy = db_ok and index_status in ["ready", "empty"]

    return jsonify({
        "status": "healthy" if is_healthy else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "index_status": index_status,
        "index_chunk_count": index_chunk_count,
        "index_version": index_version,
        "embedding_backend": os.environ.get('EMBEDDING_BACKEND', 'tfidf'),
        "llm_provider": provider_name,
        "llm_configured": llm_configured,
        "timestamp": datetime.now().isoformat()
    }), (200 if is_healthy else 503)

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host='0.0.0.0', port=5000, debug=debug_mode)
