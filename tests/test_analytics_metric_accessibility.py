import re
from pathlib import Path


TEMPLATE = Path(__file__).resolve().parents[1] / "bottube_templates" / "analytics.html"


def test_analytics_metric_controls_synchronize_pressed_state():
    html = TEMPLATE.read_text(encoding="utf-8")

    assert re.search(
        r'class="metric-tabs"[^>]*role="group"[^>]*aria-label="Rank top videos by"',
        html,
    )
    buttons = re.findall(r'<button[^>]*class="metric-tab[^>]*>', html)
    assert len(buttons) == 3
    assert sum('aria-pressed="true"' in button for button in buttons) == 1
    assert sum('aria-pressed="false"' in button for button in buttons) == 2
    assert all('type="button"' in button for button in buttons)

    assert "const selected = t === this;" in html
    assert "t.classList.toggle('active', selected);" in html
    assert "t.setAttribute('aria-pressed', String(selected));" in html
