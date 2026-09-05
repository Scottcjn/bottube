from pathlib import Path


TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "bottube_templates"
    / "collaboration_pending_invites.html"
)


def test_pending_invite_actions_lock_during_request_and_recover_on_failure():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert html.count('class="btn btn-primary invite-response-btn"') == 1
    assert html.count('class="btn btn-danger invite-response-btn"') == 1
    assert "respondToInvite(this, '{{ invite.invite_id }}', 'accept')" in html
    assert "respondToInvite(this, '{{ invite.invite_id }}', 'decline')" in html
    assert "function setInviteResponsePending(button, pending)" in html
    assert "actions.setAttribute('aria-busy', String(pending));" in html
    assert "control.disabled = pending;" in html
    assert "setInviteResponsePending(button, true);" in html
    assert html.count("setInviteResponsePending(button, false);") == 2
