import sqlite3
from typing import Dict, Any, Optional

def handle_personal_query(db_path: str, student_id: int, query_type: str) -> Dict[str, Any]:
    """
    Handle personal queries deterministically from SQLite (Rule 4, 5).
    Scoped strictly to student_id from session.
    Returns:
        dict with answer, facts (structured numerical data for composer), and status.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM students WHERE id = ?", (student_id,))
    student = cur.fetchone()
    if not student:
        conn.close()
        return {
            "answer": "Student profile not found in system.",
            "facts": {},
            "status": "error"
        }

    facts = {"student_name": student["name"], "reg_no": student["reg_no"]}

    if query_type == "attendance":
        cur.execute("SELECT subject, attended_classes, total_classes, percentage FROM attendance WHERE student_id = ?", (student_id,))
        rows = cur.fetchall()
        if not rows:
            conn.close()
            return {"answer": "No attendance records found.", "facts": {}, "status": "ok"}

        avg_p = sum(r["percentage"] for r in rows) / len(rows)
        facts["avg_attendance"] = avg_p
        facts["subject_attendance"] = [dict(r) for r in rows]

        details = "; ".join([f"{r['subject']}: {r['percentage']:.1f}% ({r['attended_classes']}/{r['total_classes']})" for r in rows])
        answer = f"Your overall attendance is {avg_p:.1f}%. Details: {details}."
        conn.close()
        return {"answer": answer, "facts": facts, "status": "ok"}

    elif query_type == "marks":
        cur.execute("SELECT subject, internal1, internal2, assignment, total FROM marks WHERE student_id = ?", (student_id,))
        rows = cur.fetchall()
        if not rows:
            conn.close()
            return {"answer": "No internal marks recorded yet.", "facts": {}, "status": "ok"}

        facts["marks"] = [dict(r) for r in rows]
        details = "; ".join([f"{r['subject']}: Total {r['total']}/110 (I1: {r['internal1']}, I2: {r['internal2']}, Assign: {r['assignment']})" for r in rows])
        answer = f"Your internal marks are:\n{details}."
        conn.close()
        return {"answer": answer, "facts": facts, "status": "ok"}

    elif query_type == "fees":
        cur.execute("SELECT * FROM fees WHERE student_id = ?", (student_id,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return {"answer": "No fee record found.", "facts": {}, "status": "ok"}

        facts["total_fee"] = row["total_fee"]
        facts["paid_fee"] = row["paid_fee"]
        facts["due_fee"] = row["due_fee"]
        facts["status"] = row["status"]
        facts["due_date"] = row["due_date"]

        answer = f"Fee Summary: Total ₹{row['total_fee']}, Paid ₹{row['paid_fee']}, Due ₹{row['due_fee']}. Due Date: {row['due_date']} (Status: {row['status']})."
        conn.close()
        return {"answer": answer, "facts": facts, "status": "ok"}

    elif query_type == "timetable":
        cur.execute("SELECT day_of_week, period_1, period_2, period_3, period_4, period_5 FROM timetable WHERE department = ? AND semester = ?",
                    (student["dept"], student["semester"]))
        rows = cur.fetchall()
        if not rows:
            conn.close()
            return {"answer": f"No timetable found for {student['dept']} Semester {student['semester']}.", "facts": {}, "status": "ok"}

        facts["timetable"] = [dict(r) for r in rows]
        lines = [f"{r['day_of_week']}: P1={r['period_1']}, P2={r['period_2']}, P3={r['period_3']}, P4={r['period_4']}, P5={r['period_5']}" for r in rows]
        answer = "Weekly Timetable:\n" + "\n".join(lines)
        conn.close()
        return {"answer": answer, "facts": facts, "status": "ok"}

    elif query_type == "leave":
        cur.execute("SELECT req_type, from_date, to_date, reason, status, applied_at, reviewed_by FROM leave_requests WHERE student_id = ? ORDER BY id DESC LIMIT 3", (student_id,))
        rows = cur.fetchall()
        if not rows:
            conn.close()
            return {"answer": "You have no leave or OD applications submitted.", "facts": {}, "status": "ok"}

        facts["leaves"] = [dict(r) for r in rows]
        lines = [f"• {r['req_type']} from {r['from_date']} to {r['to_date']} [{r['status']}] (Reason: {r['reason']})" for r in rows]
        answer = "Your recent leave/OD requests:\n" + "\n".join(lines)
        conn.close()
        return {"answer": answer, "facts": facts, "status": "ok"}

    conn.close()
    return {"answer": "I could not resolve this personal data request.", "facts": facts, "status": "ok"}
