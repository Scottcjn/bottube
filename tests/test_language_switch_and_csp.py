# SPDX-License-Identifier: MIT
from pathlib import Path

from flask import Response

from bottube_server import _language_switch_href, app, set_security_headers


def test_language_switch_href_preserves_search_query():
    """Verify the language switcher preserves existing query string params.

    When a user is on /search?q=rustchain&page=2 and clicks the Spanish
    language toggle, the resulting URL must keep the search query and
    pagination intact while appending `lang=es`. Otherwise switching
    language would dump the user back to a blank first page and lose their
    current search context.
    """
    with app.test_request_context("/search?q=rustchain&page=2"):
        assert _language_switch_href("es") == "?q=rustchain&page=2&lang=es"


def test_language_switch_href_adds_lang_when_no_existing_query():
    """Verify the language switcher emits a clean lang-only URL on the home page.

    When the user has no other query params (e.g. on `/`), the toggle must
    produce `?lang=fr` exactly, with no stray ampersand or empty key.
    This guards against a regression where the implementation appended
    `&lang=` unconditionally and produced an invalid query string.
    """
    with app.test_request_context("/"):
        assert _language_switch_href("fr") == "?lang=fr"


def test_security_header_allows_google_collect_endpoint():
    """Verify the CSP connect-src directive whitelists google.com.

    The base CSP must include https://www.google.com in `connect-src` so
    the page can reach Google's analytics collect endpoint from the
    browser. Without it, the CSP would block the analytics request and
    silently break all conversion / page-view tracking on the site.
    """
    with app.test_request_context("/", base_url="https://bottube.ai/"):
        response = set_security_headers(Response(""))

    csp = response.headers["Content-Security-Policy"]
    assert "connect-src" in csp
    assert "https://www.google.com" in csp


def test_template_meta_csp_allows_google_collect_endpoint():
    """Verify the base template's <meta> CSP also whitelists Google endpoints.

    Beyond the header-level CSP, the base template carries a <meta http-equiv>
    CSP fallback. That meta tag must allow the same Google domains as the
    header so analytics work consistently regardless of which CSP the
    browser uses (header wins when both are present, but the meta is the
    fallback for static file contexts).
    """
    template = Path("bottube_templates/base.html").read_text(encoding="utf-8")

    assert "https://www.google.com" in template
    assert "https://www.google-analytics.com" in template
