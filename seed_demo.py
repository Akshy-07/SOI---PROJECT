"""
Seed Demo Script for Smart College Assistant Chatbot
Initializes the database, runs migrations, seeds sample documents from sample_docs/,
and builds the vector index so the application is ready for evaluation or live demo in < 1 minute.
"""
import os
import sys
from init_db import init_database
from migrate import run_migrations
from rag.ingest import IngestionPipeline

def seed_demo():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, "database.db")
    index_dir = os.path.join(base_dir, "rag_index")
    sample_docs_dir = os.path.join(base_dir, "sample_docs")

    print("==================================================")
    print("      SEEDING SMART COLLEGE ASSISTANT DEMO        ")
    print("==================================================")

    # 1. Initialize SQLite Database with students, users, attendance, marks, fees, timetable
    print("\n[1/4] Initializing Database...")
    init_database(db_path)

    # 2. Run Idempotent Schema Migrations
    print("\n[2/4] Running Database Migrations...")
    run_migrations(db_path)

    # 3. Ingest Sample Documents
    print("\n[3/4] Ingesting Sample College Policy Documents...")
    pipeline = IngestionPipeline(db_path=db_path, index_dir=index_dir)

    docs_to_seed = [
        {
            "filename": "academic_regulations_2025_2026.txt",
            "version": "2.0",
            "effective_from": "2025-01-01",
            "effective_until": "2026-12-31",
            "uploaded_by": "Academic Registrar"
        },
        {
            "filename": "campus_facilities_and_library_handbook.txt",
            "version": "1.0",
            "effective_from": "2025-01-01",
            "effective_until": "2027-12-31",
            "uploaded_by": "Campus Facility Manager"
        },
        {
            "filename": "fees_and_scholarship_guidelines.txt",
            "version": "1.0",
            "effective_from": "2025-01-01",
            "effective_until": "2026-12-31",
            "uploaded_by": "Finance Section"
        }
    ]

    for item in docs_to_seed:
        file_path = os.path.join(sample_docs_dir, item["filename"])
        if not os.path.exists(file_path):
            print(f"  [Warning] Missing {file_path}")
            continue

        with open(file_path, "rb") as f:
            content = f.read()

        success, msg, doc_id = pipeline.ingest_document(
            filename=item["filename"],
            file_bytes=content,
            uploaded_by=item["uploaded_by"],
            version=item["version"],
            effective_from=item["effective_from"],
            effective_until=item["effective_until"]
        )
        if success:
            print(f"  [+] Ingested #{doc_id}: {item['filename']} (v{item['version']})")
        else:
            print(f"  [-] Skipped ({msg}): {item['filename']}")

    # 4. Rebuild Index
    print("\n[4/4] Building Vector Index and TF-IDF Vocabulary...")
    pipeline.rebuild_index()

    print("\n==================================================")
    print("             DEMO SEED COMPLETED!                 ")
    print("==================================================")
    print("\nDefault Accounts Available:")
    print("  1. Student:  Username: 711724UEC101  | Password: password123 (Akshayaa S)")
    print("  2. Student:  Username: 711724UEC102  | Password: password123 (Rahul K)")
    print("  3. Staff:    Username: staff        | Password: staff123")
    print("  4. Admin:    Username: admin        | Password: admin123")
    print("\nTo start the web server:")
    print("  python app.py")
    print("Access via browser at: http://localhost:5000\n")

if __name__ == "__main__":
    seed_demo()
