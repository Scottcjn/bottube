import pytest
import os
import tempfile
import sqlite3
from bottube_server import app, DB_PATH

@pytest.fixture
def client():
    app.config['TESTING'] = True
    # Create a temporary database for testing
    db_fd, temp_db_path = tempfile.mkstemp()
    app.config['DATABASE'] = temp_db_path
    
    with app.test_client() as client:
        with app.app_context():
            # Initialize the database schema here if needed
            # For this simple mock, we just ensure it exists
            pass
        yield client

    os.close(db_fd)
    os.unlink(temp_db_path)

@pytest.fixture
def mock_db(monkeypatch):
    """Fixture to mock database interactions if needed"""
    pass
