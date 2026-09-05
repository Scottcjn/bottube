# SPDX-License-Identifier: MIT
from pathlib import Path


def _template() -> str:
    template = Path(__file__).resolve().parents[1] / "templates" / "chat.html"
    return template.read_text(encoding="utf-8")


def test_live_chat_exposes_appended_messages_as_a_polite_log():
    html = _template()

    assert (
        'id="messages" role="log" aria-live="polite" '
        'aria-relevant="additions text"'
    ) in html
    assert "messagesEl.appendChild(div);" in html


def test_live_chat_composer_has_a_persistent_accessible_name():
    html = _template()

    assert 'id="msg-input" placeholder="Send a message..." maxlength="500" aria-label="Chat message"' in html
