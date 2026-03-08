import pytest
import os
import tempfile

# Create a temporary DB *before* importing the server module so that
# module-level sqlite3.connect() calls don't fail with a missing path.
_conftest_db_fd, _conftest_db_path = tempfile.mkstemp(suffix=".db")
os.environ.setdefault("BOTTUBE_DB", _conftest_db_path)
os.environ.setdefault("BOTTUBE_DB_PATH", _conftest_db_path)

from bottube_server import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    db_fd, temp_db_path = tempfile.mkstemp()
    app.config['DATABASE'] = temp_db_path
    with app.test_client() as client:
        yield client
    os.close(db_fd)
    if os.path.exists(temp_db_path):
        os.unlink(temp_db_path)
