import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IMG_TAG = re.compile(r"<img\b[^>]*>", re.IGNORECASE)


def _html_files():
    return sorted((ROOT / "bottube_templates").glob("*.html"))


def _img_tag_locations():
    for path in _html_files():
        text = path.read_text(encoding="utf-8")
        for match in IMG_TAG.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            yield path.relative_to(ROOT), line_no, match.group(0)


def test_template_images_include_alt_attributes():
    missing = [
        f"{path}:{line_no}: {tag}"
        for path, line_no, tag in _img_tag_locations()
        if " alt=" not in tag.lower()
    ]

    assert missing == []


def test_template_images_are_lazy_loaded_or_prioritized():
    missing = [
        f"{path}:{line_no}: {tag}"
        for path, line_no, tag in _img_tag_locations()
        if " loading=" not in tag.lower() and " fetchpriority=" not in tag.lower()
    ]

    assert missing == []


def test_template_and_beacon_atlas_assets_have_no_console_log():
    paths = _html_files() + [ROOT / "bottube_static" / "beacon_atlas" / "index.html"]
    offenders = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if "console.log" in line:
                offenders.append(f"{path.relative_to(ROOT)}:{line_no}: {line.strip()}")

    assert offenders == []
