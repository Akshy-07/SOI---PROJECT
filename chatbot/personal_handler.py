import sqlite3
from typing import Dict, Any, Optional

def handle_personal_query(db_path: str, student_id: int, query_type: str, question: str = "") -> Dict[str, Any]:
    """
    Handle personal queries deterministically from SQLite (Rule 4, 5).
    Scoped strictly to student_id from session.
    Supports comparative queries (lowest, highest, below threshold, comparisons).
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
    q_lower = (question or "").lower()

    if query_type == "attendance":
        cur.execute("SELECT subject, attended_classes, total_classes, percentage FROM attendance WHERE student_id = ?", (student_id,))
        rows = cur.fetchall()
        if not rows:
            conn.close()
            return {"answer": "No attendance records found.", "facts": {}, "status": "ok"}

        avg_p = sum(r["percentage"] for r in rows) / len(rows)
        facts["avg_attendance"] = avg_p
        facts["subject_attendance"] = [dict(r) for r in rows]

        # Comparative checks
        if any(w in q_lower for w in ["lowest", "minimum", "least", "shortage"]):
            min_sub = min(rows, key=lambda r: r["percentage"])
            answer = f"Your lowest attendance is in {min_sub['subject']} with {min_sub['percentage']:.1f}% ({min_sub['attended_classes']}/{min_sub['total_classes']} classes)."
            conn.close()
            return {"answer": answer, "facts": facts, "status": "ok"}

        if any(w in q_lower for w in ["highest", "maximum", "best", "top"]):
            max_sub = max(rows, key=lambda r: r["percentage"])
            answer = f"Your highest attendance is in {max_sub['subject']} with {max_sub['percentage']:.1f}% ({max_sub['attended_classes']}/{max_sub['total_classes']} classes)."
            conn.close()
            return {"answer": answer, "facts": facts, "status": "ok"}

        if any(w in q_lower for w in ["below", "less than"]):
            threshold = 75.0
            # Check for numbers in query
            import re
            num_match = re.search(r"(\d{2})%", q_lower)
            if num_match:
                threshold = float(num_match.group(1))
            below_subs = [r for r in rows if r["percentage"] < threshold]
            if below_subs:
                sub_str = ", ".join([f"{r['subject']} ({r['percentage']:.1f}%)" for r in below_subs])
                answer = f"You have {len(below_subs)} subject(s) below {threshold:.0f}% attendance: {sub_str}."
            else:
                answer = f"Great news! None of your subjects are below {threshold:.0f}% attendance."
            conn.close()
            return {"answer": answer, "facts": facts, "status": "ok"}

        if any(w in q_lower for w in ["compare", "comparison", "across"]):
            min_sub = min(rows, key=lambda r: r["percentage"])
            max_sub = max(rows, key=lambda r: r["percentage"])
            lines = [f"• {r['subject']}: {r['percentage']:.1f}%" for r in rows]
            comp_details = "\n".join(lines)
            answer = f"Attendance Comparison (Average: {avg_p:.1f}%):\n{comp_details}\nHighest: {max_sub['subject']} ({max_sub['percentage']:.1f}%), Lowest: {min_sub['subject']} ({min_sub['percentage']:.1f}%)."
            conn.close()
            return {"answer": answer, "facts": facts, "status": "ok"}

        if "average" in q_lower:
            answer = f"Your overall average attendance is {avg_p:.1f}% across {len(rows)} registered subjects."
            conn.close()
            return {"answer": answer, "facts": facts, "status": "ok"}

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

        if any(w in q_lower for w in ["highest", "maximum", "best", "top"]):
            max_sub = max(rows, key=lambda r: r["total"])
            answer = f"Your highest internal marks are in {max_sub['subject']} with {max_sub['total']}/110 (I1: {max_sub['internal1']}, I2: {max_sub['internal2']}, Assign: {max_sub['assignment']})."
            conn.close()
            return {"answer": answer, "facts": facts, "status": "ok"}

        if any(w in q_lower for w in ["lowest", "minimum", "least"]):
            min_sub = min(rows, key=lambda r: r["total"])
            answer = f"Your lowest internal marks are in {min_sub['subject']} with {min_sub['total']}/110 (I1: {min_sub['internal1']}, I2: {min_sub['internal2']}, Assign: {min_sub['assignment']})."
            conn.close()
            return {"answer": answer, "facts": facts, "status": "ok"}

        if "average" in q_lower:
            avg_m = sum(r["total"] for r in rows) / len(rows)
            answer = f"Your average internal total marks are {avg_m:.1f}/110 across {len(rows)} subjects."
            conn.close()
            return {"answer": answer, "facts": facts, "status": "ok"}

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

        if any(w in q_lower for w in ["when", "due date", "deadline"]):
            answer = f"Your fee payment due date is {row['due_date']} (Pending Dues: ₹{row['due_fee']:,}, Status: {row['status']})."
            conn.close()
            return {"answer": answer, "facts": facts, "status": "ok"}

        if any(w in q_lower for w in ["how much", "due", "pending", "balance", "owe", "to pay"]):
            answer = f"Your pending fee due amount is ₹{row['due_fee']:,} (Total: ₹{row['total_fee']:,}, Paid: ₹{row['paid_fee']:,}, Due Date: {row['due_date']})."
            conn.close()
            return {"answer": answer, "facts": facts, "status": "ok"}

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

        # Check for specific day
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
        for day in days:
            if day in q_lower:
                day_row = next((r for r in rows if r["day_of_week"].lower() == day), None)
                if day_row:
                    answer = f"Timetable for {day_row['day_of_week']}:\nP1: {day_row['period_1']}, P2: {day_row['period_2']}, P3: {day_row['period_3']}, P4: {day_row['period_4']}, P5: {day_row['period_5']}."
                else:
                    answer = f"No classes scheduled on {day.capitalize()}."
                conn.close()
                return {"answer": answer, "facts": facts, "status": "ok"}

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
