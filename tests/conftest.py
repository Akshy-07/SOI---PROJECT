import os
import shutil
import tempfile
import pytest
import sqlite3

# Set test environment
os.environ['SECRET_KEY'] = 'test-secret-key-123456789'
os.environ['LLM_PROVIDER'] = 'mock'
os.environ['EMBEDDING_BACKEND'] = 'tfidf'
os.environ['FLASK_DEBUG'] = '0'

import app as app_module
from init_db import init_database
from migrate import run_migrations

@pytest.fixture(scope='session')
def temp_db():
    """Create a temporary copy of the database for the test session."""
    temp_dir = tempfile.mkdtemp()
    test_db_path = os.path.join(temp_dir, 'test_database.db')
    
    # Initialize fresh database and run migrations
    init_database(test_db_path)
    run_migrations(test_db_path)
    
    yield test_db_path
    
    # Clean up temp dir
    shutil.rmtree(temp_dir, ignore_errors=True)

@pytest.fixture(autouse=True)
def reset_test_state():
    app_module.limiter.reset()
    yield
    app_module.limiter.reset()

@pytest.fixture
def client(temp_db, monkeypatch):
    """Provide a Flask test client configured with the temporary database."""
    monkeypatch.setattr(app_module, 'DB_PATH', temp_db)
    app_module.app.config['TESTING'] = True
    app_module.app.config['WTF_CSRF_ENABLED'] = False  # Disabled during raw characterisation test fixtures
    app_module._composer = None
    app_module._ingest_pipeline = None
    
    with app_module.app.test_client() as client:
        yield client

