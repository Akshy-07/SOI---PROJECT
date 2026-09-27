import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')

def init_database(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute("PRAGMA busy_timeout=5000;")

    # Drop existing tables if clean init is called
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reg_no TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        dept TEXT NOT NULL,
        semester INTEGER NOT NULL,
        email TEXT,
        phone TEXT
    );

    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL, -- admin, staff, student
        name TEXT NOT NULL,
        student_id INTEGER,
        FOREIGN KEY (student_id) REFERENCES students(id)
    );

    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        subject TEXT NOT NULL,
        total_classes INTEGER NOT NULL,
        attended_classes INTEGER NOT NULL,
        percentage REAL NOT NULL,
        FOREIGN KEY (student_id) REFERENCES students(id)
    );

    CREATE TABLE IF NOT EXISTS marks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        subject TEXT NOT NULL,
        internal1 REAL NOT NULL,
        internal2 REAL NOT NULL,
        assignment REAL NOT NULL,
        total REAL NOT NULL,
        FOREIGN KEY (student_id) REFERENCES students(id)
    );

    CREATE TABLE IF NOT EXISTS fees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        total_fee REAL NOT NULL,
        paid_fee REAL NOT NULL,
        due_fee REAL NOT NULL,
        due_date TEXT NOT NULL,
        status TEXT NOT NULL, -- Paid, Partial, Due
        FOREIGN KEY (student_id) REFERENCES students(id)
    );

    CREATE TABLE IF NOT EXISTS timetable (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        department TEXT NOT NULL,
        semester INTEGER NOT NULL,
        day_of_week TEXT NOT NULL,
        period_1 TEXT NOT NULL,
        period_2 TEXT NOT NULL,
        period_3 TEXT NOT NULL,
        period_4 TEXT NOT NULL,
        period_5 TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS leave_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        req_type TEXT NOT NULL, -- Leave, On-Duty (OD)
        from_date TEXT NOT NULL,
        to_date TEXT NOT NULL,
        reason TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Pending', -- Pending, Approved, Rejected
        applied_at TEXT NOT NULL,
        reviewed_by TEXT,
        review_comment TEXT,
        FOREIGN KEY (student_id) REFERENCES students(id)
    );
    """)

    # Seed initial data if students table is empty
    cur.execute("SELECT COUNT(*) FROM students;")
    if cur.fetchone()[0] == 0:
        # Seed students
        cur.execute("INSERT INTO students (reg_no, name, dept, semester, email, phone) VALUES (?, ?, ?, ?, ?, ?)",
                    ('711724UEC101', 'Akshayaa S', 'ECE', 4, 'akshayaa@college.edu', '9876543210'))
        s1_id = cur.lastrowid

        cur.execute("INSERT INTO students (reg_no, name, dept, semester, email, phone) VALUES (?, ?, ?, ?, ?, ?)",
                    ('711724UEC102', 'Rahul K', 'ECE', 4, 'rahul@college.edu', '9876543211'))
        s2_id = cur.lastrowid

        # Seed users
        admin_hash = generate_password_hash('admin123')
        staff_hash = generate_password_hash('staff123')
        stu1_hash = generate_password_hash('password123')
        stu2_hash = generate_password_hash('password123')

        cur.execute("INSERT INTO users (username, password_hash, role, name, student_id) VALUES (?, ?, ?, ?, ?)",
                    ('admin', admin_hash, 'admin', 'System Administrator', None))
        cur.execute("INSERT INTO users (username, password_hash, role, name, student_id) VALUES (?, ?, ?, ?, ?)",
                    ('staff', staff_hash, 'staff', 'Department Faculty (Shared)', None))
        cur.execute("INSERT INTO users (username, password_hash, role, name, student_id) VALUES (?, ?, ?, ?, ?)",
                    ('711724UEC101', stu1_hash, 'student', 'Akshayaa S', s1_id))
        cur.execute("INSERT INTO users (username, password_hash, role, name, student_id) VALUES (?, ?, ?, ?, ?)",
                    ('711724UEC102', stu2_hash, 'student', 'Rahul K', s2_id))

        # Seed attendance for Akshayaa (s1)
        cur.execute("INSERT INTO attendance (student_id, subject, total_classes, attended_classes, percentage) VALUES (?, ?, ?, ?, ?)",
                    (s1_id, 'Digital Signal Processing', 40, 36, 90.0))
        cur.execute("INSERT INTO attendance (student_id, subject, total_classes, attended_classes, percentage) VALUES (?, ?, ?, ?, ?)",
                    (s1_id, 'Microprocessors & Microcontrollers', 40, 32, 80.0))
        cur.execute("INSERT INTO attendance (student_id, subject, total_classes, attended_classes, percentage) VALUES (?, ?, ?, ?, ?)",
                    (s1_id, 'VLSI Design', 40, 28, 70.0))

        # Seed attendance for Rahul (s2)
        cur.execute("INSERT INTO attendance (student_id, subject, total_classes, attended_classes, percentage) VALUES (?, ?, ?, ?, ?)",
                    (s2_id, 'Digital Signal Processing', 40, 28, 70.0))
        cur.execute("INSERT INTO attendance (student_id, subject, total_classes, attended_classes, percentage) VALUES (?, ?, ?, ?, ?)",
                    (s2_id, 'Microprocessors & Microcontrollers', 40, 30, 75.0))
        cur.execute("INSERT INTO attendance (student_id, subject, total_classes, attended_classes, percentage) VALUES (?, ?, ?, ?, ?)",
                    (s2_id, 'VLSI Design', 40, 29, 72.5))

        # Seed marks for Akshayaa
        cur.execute("INSERT INTO marks (student_id, subject, internal1, internal2, assignment, total) VALUES (?, ?, ?, ?, ?, ?)",
                    (s1_id, 'Digital Signal Processing', 45.0, 48.0, 10.0, 103.0))
        cur.execute("INSERT INTO marks (student_id, subject, internal1, internal2, assignment, total) VALUES (?, ?, ?, ?, ?, ?)",
                    (s1_id, 'Microprocessors & Microcontrollers', 42.0, 44.0, 9.5, 95.5))
        cur.execute("INSERT INTO marks (student_id, subject, internal1, internal2, assignment, total) VALUES (?, ?, ?, ?, ?, ?)",
                    (s1_id, 'VLSI Design', 38.0, 40.0, 9.0, 87.0))

        # Seed marks for Rahul
        cur.execute("INSERT INTO marks (student_id, subject, internal1, internal2, assignment, total) VALUES (?, ?, ?, ?, ?, ?)",
                    (s2_id, 'Digital Signal Processing', 35.0, 36.0, 8.0, 79.0))
        cur.execute("INSERT INTO marks (student_id, subject, internal1, internal2, assignment, total) VALUES (?, ?, ?, ?, ?, ?)",
                    (s2_id, 'Microprocessors & Microcontrollers', 37.0, 39.0, 8.5, 84.5))
        cur.execute("INSERT INTO marks (student_id, subject, internal1, internal2, assignment, total) VALUES (?, ?, ?, ?, ?, ?)",
                    (s2_id, 'VLSI Design', 34.0, 36.0, 8.0, 78.0))

        # Seed fees
        cur.execute("INSERT INTO fees (student_id, total_fee, paid_fee, due_fee, due_date, status) VALUES (?, ?, ?, ?, ?, ?)",
                    (s1_id, 65000.0, 50000.0, 15000.0, '2026-10-15', 'Due'))
        cur.execute("INSERT INTO fees (student_id, total_fee, paid_fee, due_fee, due_date, status) VALUES (?, ?, ?, ?, ?, ?)",
                    (s2_id, 65000.0, 65000.0, 0.0, '2026-10-15', 'Paid'))

        # Seed timetable
        tt_days = [
            ('Monday', 'DSP', 'MPMC', 'VLSI', 'DSP Lab', 'DSP Lab'),
            ('Tuesday', 'MPMC', 'DSP', 'Library', 'VLSI Lab', 'VLSI Lab'),
            ('Wednesday', 'VLSI', 'DSP', 'MPMC', 'Placement', 'Sports'),
            ('Thursday', 'DSP', 'VLSI', 'MPMC', 'Seminar', 'Mentor Hour'),
            ('Friday', 'MPMC', 'DSP', 'VLSI', 'Project Work', 'Project Work')
        ]
        for day, p1, p2, p3, p4, p5 in tt_days:
            cur.execute("INSERT INTO timetable (department, semester, day_of_week, period_1, period_2, period_3, period_4, period_5) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        ('ECE', 4, day, p1, p2, p3, p4, p5))

        # Seed leave requests
        cur.execute("INSERT INTO leave_requests (student_id, req_type, from_date, to_date, reason, status, applied_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (s1_id, 'Leave', '2026-10-01', '2026-10-02', 'Medical fever and doctor checkup', 'Pending', '2026-09-25 10:30:00'))

    conn.commit()
    conn.close()
    print("Database initialized successfully at", db_path)

if __name__ == '__main__':
    init_database()
