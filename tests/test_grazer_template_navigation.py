# SPDX-License-Identifier: MIT
from pathlib import Path


def test_grazer_external_resources_isolate_new_tab_context():
    template = Path(__file__).resolve().parents[1] / "bottube_templates" / "grazer.html"
    html = template.read_text(encoding="utf-8")

    resources = (
        "https://github.com/Scottcjn/grazer-skill",
        "https://www.npmjs.com/package/grazer-skill",
        "https://pypi.org/project/grazer-skill",
    )
    assert html.count('target="_blank" rel="noopener noreferrer"') == len(resources)
    for url in resources:
        assert f'href="{url}" target="_blank" rel="noopener noreferrer"' in html
