# SPDX-License-Identifier: MIT
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_studio_results_render_api_urls_with_dom_api():
    source = (ROOT / "bottube_templates" / "studio.html").read_text(encoding="utf-8")

    assert "resultEl.innerHTML" not in source
    assert 'src="\' + res.d.media_url + \'"' not in source
    assert 'src="\' + d.model_url + \'"' not in source
    assert "function safeHttpUrl(value)" in source
    assert "function safeSameOriginUrl(value)" in source
    assert "resultEl.replaceChildren(img, renderDownloadLink(mediaUrl, \"Download image →\"));" in source
    assert "resultEl.replaceChildren(audio, renderDownloadLink(mediaUrl, \"Download audio →\"));" in source
    assert "resultEl.replaceChildren(viewer, wrap);" in source


def test_studio_generated_images_are_lazy_decoded_and_sized():
    source = (ROOT / "bottube_templates" / "studio.html").read_text(encoding="utf-8")

    assert 'img.alt = "generated image";' in source
    assert 'img.loading = "lazy";' in source
    assert 'img.decoding = "async";' in source
    assert "img.width = 720;" in source
    assert "img.height = 720;" in source


def test_studio_status_messages_default_to_text_content():
    source = (ROOT / "bottube_templates" / "studio.html").read_text(encoding="utf-8")

    assert "function say(m){ statusEl.textContent = m == null ? \"\" : String(m); }" in source
    assert "Done! <a href=" not in source
    assert "statusEl.replaceChildren(\"🎬 Done! \", link);" in source
