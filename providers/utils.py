from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Optional

import requests


def download_file(
    url: str,
    output_path: Optional[str] = None,
    *,
    prefix: str = "video_",
    timeout: int = 180,
) -> Path:
    """Download a URL to a local file and return its path."""
    if output_path:
        dest = Path(output_path)
    else:
        fd, temp_name = tempfile.mkstemp(prefix=prefix, suffix=".mp4")
        Path(temp_name).unlink(missing_ok=True)
        dest = Path(temp_name)

    dest.parent.mkdir(parents=True, exist_ok=True)

    with requests.get(url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

    if not dest.exists() or dest.stat().st_size < 1024:
        raise RuntimeError(f"Downloaded file is empty or too small: {dest}")

    return dest
