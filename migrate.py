import sqlite3
import os
import shutil
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')
BACKUPS_DIR = os.path.join(os.path.dirname(__file__), 'backups')

def backup_database(db_path=DB_PATH):
    """Back up database.db to backups/database_<timestamp>.db before schema change."""
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    if os.path.exists(db_path):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dest = os.path.join(BACKUPS_DIR, f"database_{timestamp}.db")
        shutil.copy2(db_path, backup_dest)
        print(f"[Backup] Successfully backed up {db_path} to {backup_dest}")
        return backup_dest
    return None

def column_exists(cursor, table_name, column_name):
    """Check if column exists in table for idempotent migrations."""
    cursor.execute(f"PRAGMA table_info({table_name});")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns

def run_migrations(db_path=DB_PATH):
    """Run idempotent database migrations."""
    backup_database(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA busy_timeout=5000;")

    # 1. Base kb_documents table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS kb_documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_name TEXT NOT NULL,
        file_path TEXT NOT NULL,
        file_hash TEXT,
        file_type TEXT NOT NULL,
        version TEXT DEFAULT '1.0',
        uploaded_by TEXT NOT NULL,
        effective_from TEXT,
        effective_until TEXT,
        status TEXT NOT NULL DEFAULT 'active', -- active, inactive, processing, needs_ocr
        chunk_count INTEGER DEFAULT 0,
        embedding_backend TEXT,
        supersedes_id INTEGER,
        created_at TEXT NOT NULL
    );
    """)

    # Check and add extended columns to kb_documents if needed
    kb_cols = [
        ('file_hash', 'TEXT'),
        ('effective_from', 'TEXT'),
        ('effective_until', 'TEXT'),
        ('status', 'TEXT DEFAULT "active"'),
        ('version', 'TEXT DEFAULT "1.0"'),
        ('supersedes_id', 'INTEGER')
    ]
    for col, col_type in kb_cols:
        if not column_exists(cur, 'kb_documents', col):
            cur.execute(f"ALTER TABLE kb_documents ADD COLUMN {col} {col_type};")

    # 2. unresolved_queries table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS unresolved_queries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        reg TEXT NOT NULL,
        question TEXT NOT NULL,
        chatbot_response TEXT,
        route TEXT,
        confidence TEXT,
        status TEXT NOT NULL DEFAULT 'open', -- open, in_review, resolved, rejected
        staff_response TEXT,
        reviewed_by TEXT,
        created_at TEXT NOT NULL,
        resolved_at TEXT
    );
    """)

    # 3. faq_entries table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS faq_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        source_query_id INTEGER,
        approved_by TEXT,
        status TEXT NOT NULL DEFAULT 'draft', -- draft, approved, retired
        created_at TEXT NOT NULL
    );
    """)

    # 4. audit_logs table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT NOT NULL,
        ts TEXT NOT NULL,
        user_role TEXT NOT NULL,
        user_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        route TEXT,
        question TEXT,
        answer TEXT,
        sources_json TEXT,
        confidence TEXT,
        latency_ms INTEGER,
        status TEXT NOT NULL
    );
    """)

    # 5. chat_feedback table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS chat_feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT NOT NULL,
        student_id INTEGER NOT NULL,
        rating INTEGER NOT NULL, -- +1 or -1
        comment TEXT,
        created_at TEXT NOT NULL
    );
    """)

    # 6. policy_rules table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS policy_rules (
        key TEXT PRIMARY KEY,
        value REAL NOT NULL,
        unit TEXT NOT NULL,
        source_document_id INTEGER,
        updated_by TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    """)

    # Seed default policy rule if missing: min_attendance_percent = 75
    cur.execute("SELECT COUNT(*) FROM policy_rules WHERE key = 'min_attendance_percent';")
    if cur.fetchone()[0] == 0:
        cur.execute("""
        INSERT INTO policy_rules (key, value, unit, source_document_id, updated_by, updated_at)
        VALUES ('min_attendance_percent', 75.0, '%', NULL, 'system', datetime('now'));
        """)

    # 7. answer_cache table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS answer_cache (
        question_norm_hash TEXT PRIMARY KEY,
        answer_json TEXT NOT NULL,
        index_version TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """)

    # 8. Indexes
    cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_logs_ts ON audit_logs(ts);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_unresolved_queries_status ON unresolved_queries(status);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_kb_documents_status ON kb_documents(status);")

    conn.commit()
    conn.close()
    print("[Migration] All migrations completed successfully and idempotently.")

if __name__ == '__main__':
    run_migrations()
