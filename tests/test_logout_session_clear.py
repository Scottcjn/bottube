from pathlib import Path


def test_logout_clears_session_and_expires_cookie():
    src = Path('bottube_server.py').read_text()
    logout_start = src.index('def logout():')
    logout_block = src[logout_start:logout_start + 1200]

    assert 'session.clear()' in logout_block
    assert 'resp.delete_cookie(' in logout_block
    assert 'SESSION_COOKIE_NAME' in logout_block
