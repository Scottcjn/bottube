from pathlib import Path

from flask import Response

from bottube_server import _language_switch_href, app, set_security_headers


def test_language_switch_href_preserves_search_query():
    with app.test_request_context("/search?q=rustchain&page=2"):
        assert _language_switch_href("es") == "?q=rustchain&page=2&lang=es"


def test_language_switch_href_adds_lang_when_no_existing_query():
    with app.test_request_context("/"):
        assert _language_switch_href("fr") == "?lang=fr"


def test_security_header_allows_google_collect_endpoint():
    with app.test_request_context("/", base_url="https://bottube.ai/"):
        response = set_security_headers(Response(""))

    csp = response.headers["Content-Security-Policy"]
    assert "connect-src" in csp
    assert "https://www.google.com" in csp


def test_template_meta_csp_allows_google_collect_endpoint():
    template = Path("bottube_templates/base.html").read_text(encoding="utf-8")

    assert "https://www.google.com" in template
    assert "https://www.google-analytics.com" in template
