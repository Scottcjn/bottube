# SPDX-License-Identifier: MIT
"""Regression tests for /credits page localization (issue #1796)."""

from bottube_server import app


def test_credits_page_localizes_body_in_spanish():
    client = app.test_client()
    response = client.get("/credits?lang=es")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert 'lang="es"' in html
    assert "Créditos y Precios" in html
    assert "Generación de video" in html
    assert "Comprar créditos RTC" in html
    assert "Recargas con tarjeta" in html
    assert "Credits & Pricing" not in html
    assert "Video generation" not in html
    assert "Buy RTC credits" not in html


def test_credits_page_defaults_to_english_without_lang_override():
    client = app.test_client()
    response = client.get("/credits")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Credits &amp; Pricing" in html or "Credits & Pricing" in html
    assert "Video generation" in html
    assert "Buy RTC credits" in html
