import pytest
import os
import tempfile
import sqlite3
from bottube_server import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['DEBUG'] = False
    # Mocking the DB path for the duration of the test
    db_fd, temp_db_path = tempfile.mkstemp()
    app.config['DATABASE'] = temp_db_path
    
    with app.test_client() as client:
        yield client

    os.close(db_fd)
    if os.path.exists(temp_db_path):
        os.unlink(temp_db_path)

@pytest.fixture
def mock_db():
    # Simple fixture to indicate DB interaction is needed
    return True
