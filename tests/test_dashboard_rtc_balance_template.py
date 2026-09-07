import re
from pathlib import Path

from jinja2 import Template


TEMPLATE = Path(__file__).resolve().parents[1] / "bottube_templates" / "dashboard.html"


def test_dashboard_renders_rtc_balance_instead_of_template_source():
    html = TEMPLATE.read_text(encoding="utf-8")
    match = re.search(
        r'<div class="stat-card green">(.*?)<div class="stat-label">RTC Balance</div>',
        html,
        re.DOTALL,
    )

    assert match, "expected the RTC Balance stat card in dashboard.html"
    rendered = Template(match.group(1)).render(rtc_balance=12.34567)

    assert "12.3457" in rendered
    assert "format(rtc_balance)" not in rendered
