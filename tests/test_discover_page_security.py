from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_agent_cards_escape_profile_fields_before_inner_html_render():
    template = (ROOT / "bottube_templates" / "discover.html").read_text(encoding="utf-8")

    assert 'onclick="window.location=\'/agent/${agent.name}\'' not in template
    assert 'src="${agent.avatar || \'/static/default-avatar.png\'}"' not in template
    assert 'alt="${agent.display_name}"' not in template
    assert "${agent.bio || ''}" not in template

    assert "${encodeURIComponent(agent.name || '')}" in template
    assert "${escapeAttribute(agent.avatar || '/static/default-avatar.png')}" in template
    assert "${escapeAttribute(agent.display_name)}" in template
    assert "${escapeHtml(agent.bio || '')}" in template
    assert "function escapeAttribute" in template
