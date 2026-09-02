import re
from pathlib import Path


TEMPLATE = Path(__file__).resolve().parents[1] / "bottube_templates" / "studio.html"


def test_studio_modes_expose_and_synchronize_tab_state():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert re.search(
        r'class="st-modes"[^>]*role="tablist"[^>]*aria-label="Generation mode"',
        html,
    )
    for mode in ("video", "image", "voice", "model", "i2v"):
        tab = re.search(rf'<button[^>]*id="tab-{mode}"[^>]*>', html)
        assert tab
        assert f'data-mode="{mode}"' in tab.group(0)
        assert 'role="tab"' in tab.group(0)
        assert f'aria-controls="mode-{mode}"' in tab.group(0)
        assert 'aria-selected=' in tab.group(0)

        panel = re.search(rf'<div[^>]*id="mode-{mode}"[^>]*>', html)
        assert panel
        assert 'role="tabpanel"' in panel.group(0)
        assert f'aria-labelledby="tab-{mode}"' in panel.group(0)

    assert 'b.setAttribute("aria-selected", String(selected));' in html
    assert 'b.tabIndex = selected ? 0 : -1;' in html
    assert 'panel.hidden = !selected;' in html
