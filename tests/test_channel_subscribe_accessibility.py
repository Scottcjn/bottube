from pathlib import Path


TEMPLATE = Path(__file__).resolve().parents[1] / "bottube_templates" / "channel.html"


def test_channel_subscribe_toggle_synchronizes_accessible_state():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert 'id="subscribe-btn"' in html
    assert 'data-agent-label="{{ agent.display_name or agent.agent_name }}"' in html
    assert 'aria-pressed="{{ \'true\' if is_following else \'false\' }}"' in html
    assert 'btn.setAttribute("aria-pressed", String(d.following));' in html
    assert '(d.following ? "Unfollow " : "Subscribe to ") + btn.dataset.agentLabel' in html
