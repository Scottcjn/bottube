#!/usr/bin/env python3
"""Product Hunt launch fixes - 4 targeted patches.

Task: #1588 - Add type hints to Python functions

Fixes:
    1. Mobile horizontal scroll fix (search bar overflow)
    2. Color contrast improvements (accessibility)
    3. LCP featured image: remove loading=lazy, add fetchpriority=high
    4. Footer badge images: add width/height attributes
"""
from __future__ import annotations
import re
import shutil
import os
from datetime import datetime
from typing import Tuple, List, Dict, Any

TEMPLATES: str = "/root/bottube/bottube_templates"
BASE: str = os.path.join(TEMPLATES, "base.html")
INDEX: str = os.path.join(TEMPLATES, "index.html")


def get_timestamp() -> str:
    """Get current timestamp for backup file names."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def backup_file(file_path: str, timestamp: str) -> str:
    """Create a backup of the file.
    
    Returns:
        Backup file path
    """
    backup: str = file_path + ".bak." + timestamp
    shutil.copy2(file_path, backup)
    print("[backup] {} -> {}".format(file_path, backup))
    return backup


def backup_files(files: List[str], timestamp: str) -> None:
    """Backup multiple files."""
    for f in files:
        backup_file(f, timestamp)


def read_file(file_path: str) -> str:
    """Read file content."""
    with open(file_path, "r", encoding="utf-8") as fh:
        return fh.read()


def write_file(file_path: str, content: str) -> None:
    """Write content to file."""
    with open(file_path, "w", encoding="utf-8") as fh:
        fh.write(content)


def apply_css_fixes(base_content: str) -> Tuple[str, bool]:
    """Apply CSS fixes to base.html.
    
    Returns:
        Tuple of (new_content, success)
    """
    css_additions: str = """
        /* === Product Hunt launch fixes (2026-02-07) === */

        /* Fix 1: Mobile horizontal scroll prevention */
        html, body { overflow-x: hidden; }
        @media (max-width: 768px) {
            .search-bar { max-width: calc(100vw - 120px); }
            .search-bar input { min-width: 0; }
        }

        /* Fix 2: Accessibility - improve color contrast (WCAG AA) */
        .video-stats { color: #9e9eb8 !important; }
        .badge-human-sm { color: #b0b0c8 !important; }
        .footer-featured-label { color: #9e9eb8 !important; }
        .footer-copy { color: #9e9eb8 !important; }
        footer a { color: #b0b0c8 !important; }
        #bottube-counters { color: #9e9eb8 !important; }
"""

    old_close: str = "    </style>"
    new_close: str = css_additions + "\n    </style>"

    if old_close in base_content:
        return base_content.replace(old_close, new_close, 1), True
    return base_content, False


def apply_badge_fixes(base_content: str) -> Tuple[str, Dict[str, bool]]:
    """Add width/height to footer badge images.
    
    Returns:
        Tuple of (new_content, results dict)
    """
    results: Dict[str, bool] = {}

    # Dofollow badge (SVG)
    old_dofollow: str = '<img src="https://dofollow.tools/badge/badge_dark.svg" alt="Dofollow.Tools">'
    new_dofollow: str = '<img src="https://dofollow.tools/badge/badge_dark.svg" alt="Dofollow.Tools" width="120" height="24">'
    if old_dofollow in base_content:
        base_content = base_content.replace(old_dofollow, new_dofollow, 1)
        results["dofollow"] = True
    else:
        results["dofollow"] = False

    # Startup Fame badge (WebP)
    old_startup: str = '<img src="https://startupfa.me/badges/featured-badge-small.webp" alt="Startup Fame">'
    new_startup: str = '<img src="https://startupfa.me/badges/featured-badge-small.webp" alt="Startup Fame" width="120" height="24">'
    if old_startup in base_content:
        base_content = base_content.replace(old_startup, new_startup, 1)
        results["startup"] = True
    else:
        results["startup"] = False

    return base_content, results


def apply_lcp_fix(index_content: str) -> Tuple[str, bool]:
    """Replace loading="lazy" with fetchpriority="high" on first featured image.
    
    Returns:
        Tuple of (new_content, success)
    """
    marker: str = '<div class="featured-row">'
    if marker in index_content:
        parts: List[str] = index_content.split(marker, 1)
        if 'loading="lazy">' in parts[1]:
            parts[1] = parts[1].replace('loading="lazy">', 'fetchpriority="high">', 1)
            return marker.join(parts), True
    return index_content, False


def apply_ph_fixes() -> Dict[str, Any]:
    """Apply all Product Hunt fixes.
    
    Returns:
        Results dictionary
    """
    results: Dict[str, Any] = {
        "timestamp": get_timestamp(),
        "fixes": {}
    }

    # Backup files
    backup_files([BASE, INDEX], results["timestamp"])

    # Apply base.html fixes
    base_content: str = read_file(BASE)
    
    # CSS fixes (1+2)
    base_content, css_success = apply_css_fixes(base_content)
    results["fixes"]["css"] = css_success

    # Badge fixes (4)
    base_content, badge_results = apply_badge_fixes(base_content)
    results["fixes"]["badges"] = badge_results

    # Save base.html
    write_file(BASE, base_content)
    results["files"]["base"] = True

    # Apply index.html fixes (3)
    index_content: str = read_file(INDEX)
    index_content, lcp_success = apply_lcp_fix(index_content)
    results["fixes"]["lcp"] = lcp_success

    # Save index.html
    write_file(INDEX, index_content)
    results["files"]["index"] = True

    return results


def main() -> None:
    """Main entry point."""
    results: Dict[str, Any] = apply_ph_fixes()
    print("\n[done] Product Hunt fixes applied!")
    print(f"  - CSS fixes: {'✓' if results['fixes']['css'] else '✗'}")
    print(f"  - LCP fix: {'✓' if results['fixes']['lcp'] else '✗'}")
    print(f"  - Badge fixes: {results['fixes']['badges']}")


if __name__ == "__main__":
    main()
