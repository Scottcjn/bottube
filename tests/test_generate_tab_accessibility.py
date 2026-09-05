import re
from pathlib import Path


TEMPLATE = Path(__file__).resolve().parents[1] / "bottube_templates" / "generate.html"


def test_generator_tabs_synchronize_accessible_and_visible_state():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert re.search(
        r'class="gen-tabs"[^>]*role="tablist"[^>]*aria-label="Generation type"',
        html,
    )
    for mode in ("video", "image", "history"):
        tab = re.search(rf'<button[^>]*id="tab-{mode}"[^>]*>', html)
        assert tab
        assert 'role="tab"' in tab.group(0)
        assert f'aria-controls="panel-{mode}"' in tab.group(0)
        assert 'aria-selected=' in tab.group(0)
        assert 'tabindex=' in tab.group(0)

        panel = re.search(rf'<div[^>]*id="panel-{mode}"[^>]*>', html)
        assert panel
        assert 'role="tabpanel"' in panel.group(0)
        assert f'aria-labelledby="tab-{mode}"' in panel.group(0)

    assert "t.setAttribute('aria-selected', String(selected));" in html
    assert 't.tabIndex = selected ? 0 : -1;' in html
    assert 'p.hidden = !selected;' in html
