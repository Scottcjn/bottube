from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_TEMPLATE = ROOT / "bottube_templates" / "report.html"


def test_report_errors_do_not_remove_success_reference_node():
    html = REPORT_TEMPLATE.read_text(encoding="utf-8")

    assert 'id="r-toast-message"' in html
    assert "document.getElementById('r-toast-message')" in html
    assert "toast.textContent =" not in html
    assert "ref.textContent = resp.body.report_id" in html
