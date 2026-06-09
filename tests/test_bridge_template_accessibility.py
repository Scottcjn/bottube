"""
Bridge Template Accessibility — Issue #1324 follow-up

The wRTC/ERG bridge template renders several form fields whose visible
<label> elements are not programmatically associated with their
<input>/<textarea> controls. Each input in the bridge forms has an
``id`` but no matching ``for=`` on the label, so screen readers may
expose the field with the placeholder (or no name at all) instead of
the visible label.

This test verifies that every interactive <input> in bridge.html with
an ``id`` has a corresponding <label for="..."> that points at it.

WCAG references:
- 1.3.1 Info and Relationships
- 3.3.2 Labels or Instructions
- 4.1.2 Name, Role, Value
"""
import re
from pathlib import Path


TEMPLATE = Path(__file__).resolve().parents[1] / "bottube_templates" / "bridge.html"


def _load_template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_bridge_form_inputs_have_label_for_associations():
    """Every <input id="..."> in bridge.html must be referenced by a <label for="...">."""
    html = _load_template()

    # Find all <input ...> with an id="..." attribute
    input_ids = re.findall(
        r'<input\b[^>]*\bid\s*=\s*["\']([A-Za-z][\w-]*)["\']',
        html,
        re.IGNORECASE,
    )
    assert input_ids, "expected at least one <input id=...> in bridge.html"

    # Find all <label for="..."> targets
    label_targets = set(
        re.findall(
            r'<label\b[^>]*\bfor\s*=\s*["\']([A-Za-z][\w-]*)["\']',
            html,
            re.IGNORECASE,
        )
    )
    assert label_targets, "expected at least one <label for=...> in bridge.html"

    missing = sorted(i for i in dict.fromkeys(input_ids) if i not in label_targets)
    assert not missing, (
        "These <input id> values have no <label for=...> association in bridge.html: "
        f"{missing}. WCAG 1.3.1 / 3.3.2 / 4.1.2 require programmatic label association."
    )


def test_bridge_known_input_ids_are_labelled():
    """Specific bridge inputs that issue #1324 called out for the upload form.

    The same a11y pattern must hold for the wRTC and ERG bridge forms:
    each visible label must point at its input via ``for=``.
    """
    html = _load_template()

    expected = {
        "wrtc-deposit-tx": "Transaction Signature (Solana)",
        "wrtc-withdraw-addr": "Destination Wallet (Solana)",
        "wrtc-withdraw-amount": "Amount to Withdraw (wRTC)",
        "ergo-deposit-tx": "Ergo Transaction ID",
        "ergo-withdraw-addr": "Ergo Wallet Address",
        "ergo-withdraw-amount": "Amount (RTC to convert)",
    }

    for input_id, expected_label_text in expected.items():
        pattern = re.compile(
            r'<label\b[^>]*\bfor\s*=\s*["\']'
            + re.escape(input_id)
            + r'["\'][^>]*>'
            + re.escape(expected_label_text)
            + r'</label>',
            re.IGNORECASE,
        )
        assert pattern.search(html), (
            f"Expected <label for='{input_id}'>{expected_label_text}</label> "
            f"in bridge.html (WCAG 3.3.2 Labels or Instructions)."
        )


def test_bridge_known_inputs_have_explicit_name_attribute():
    """Bridge form inputs should also carry an explicit ``name`` so that
    progressive enhancement (e.g. server-side form fallback) can address
    them. Some of these fields previously relied on JS-only ``onclick``
    handlers, which is brittle.
    """
    html = _load_template()

    expected_names = {
        "wrtc-deposit-tx": "wrtc_deposit_tx",
        "wrtc-withdraw-addr": "wrtc_withdraw_addr",
        "wrtc-withdraw-amount": "wrtc_withdraw_amount",
        "ergo-deposit-tx": "ergo_deposit_tx",
        "ergo-withdraw-addr": "ergo_withdraw_addr",
        "ergo-withdraw-amount": "ergo_withdraw_amount",
    }

    for input_id, expected_name in expected_names.items():
        pattern = re.compile(
            r'<input\b[^>]*\bid\s*=\s*["\']'
            + re.escape(input_id)
            + r'["\'][^>]*\bname\s*=\s*["\']'
            + re.escape(expected_name)
            + r'["\']',
            re.IGNORECASE,
        )
        assert pattern.search(html), (
            f"Expected <input id='{input_id}' name='{expected_name}'> in bridge.html"
        )
