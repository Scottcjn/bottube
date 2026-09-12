# SPDX-License-Identifier: MIT
"""Regression coverage for non-color cues on auth-switch links."""

import re
from pathlib import Path


def _login_template():
    return (Path(__file__).resolve().parents[1] / "bottube_templates" / "login.html").read_text(encoding="utf-8")


def test_auth_switch_links_have_persistent_non_color_cue():
    html = _login_template()
    rule = re.search(r"\.auth-switch\s+a\s*\{(?P<body>.*?)\}", html, re.S)
    assert rule, "missing .auth-switch a rule"
    assert "text-decoration: underline" in rule.group("body")
    assert "text-underline-offset" in rule.group("body")


def test_auth_switch_links_keep_visible_keyboard_focus():
    html = _login_template()
    rule = re.search(r"\.auth-switch\s+a:focus-visible\s*\{(?P<body>.*?)\}", html, re.S)
    assert rule, "missing auth-switch focus-visible rule"
    body = rule.group("body")
    assert "outline:" in body
    assert "outline-offset:" in body
