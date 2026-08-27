# SPDX-License-Identifier: MIT
from pathlib import Path


def test_api_upload_submit_handler_initializes_form_before_file_check():
    """Verify the API upload submit handler captures the form before file check.

    On submit, the handler must read `e.target` (the submitted form) before
    it queries the file input. If those two steps are reordered in the
    template, the file check would run against the wrong form reference
    and silently reject every upload with a misleading error message.
    """
    template = Path(__file__).resolve().parents[1] / "bottube_templates" / "upload.html"
    html = template.read_text(encoding="utf-8")

    form_assignment = html.find("var form = e.target;")
    file_check = html.find("var fileInput = form.querySelector")

    assert form_assignment != -1, "API upload handler should capture the submitted form"
    assert file_check != -1, "API upload handler should run the client-side file check"
    assert form_assignment < file_check
