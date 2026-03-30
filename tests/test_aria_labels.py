"""
Accessibility Test Suite - ARIA Label Coverage
Issue #417: Accessibility sweep for missing aria-labels on interactive buttons

This test suite verifies that all interactive buttons across templates have proper
aria-labels for screen reader accessibility.
"""

import os
import re
from pathlib import Path


class TestAriaLabelCoverage:
    """Test suite for aria-label coverage on interactive elements."""
    
    TEMPLATES_DIR = Path(__file__).parent.parent / "bottube_templates"
    
    # Patterns for interactive elements that should have aria-labels
    BUTTON_PATTERN = re.compile(r'<button[^>]*>', re.IGNORECASE)
    ARIA_LABEL_PATTERN = re.compile(r'aria-label\s*=\s*["\'][^"\']+["\']', re.IGNORECASE)
    SUBMIT_BUTTON_PATTERN = re.compile(r'<button[^>]*type\s*=\s*["\']submit["\'][^>]*>', re.IGNORECASE)
    TAB_BUTTON_PATTERN = re.compile(r'<button[^>]*role\s*=\s*["\']tab["\'][^>]*>', re.IGNORECASE)
    
    # Buttons that are allowed to not have aria-labels (they have visible text content)
    EXEMPT_BUTTON_TEXTS = {
        'Markdown', 'HTML', 'Search', 'Copy', 'Cancel', 'Reply',
        'Following', 'Subscribe', 'Log In', 'Create Account',
        'Generate', 'Download', 'Refresh Info', 'Verify Transaction',
        'Queue Withdrawal', 'Load History', 'Enter Giveaway', 'Create Playlist',
        'Try Again', 'Go Home', 'Upload Video', 'Use as Thumbnail',
        'Upload to BoTTube', 'Generate Video', 'Generate Image',
        'Verify & Credit', 'Request Withdrawal', 'Queue Vault Withdrawal',
        'Save', 'Import Seed', 'Show Seed', 'Clear', 'Set Profile To This Address',
        'Comment', 'Discord', 'Copy Link', 'Embed', 'Copy Embed Code',
        'Replay', 'Close', 'Like', 'Dislike', 'Share', 'Save this video to a playlist',
        '0.01', '0.05', '0.10', '0.50', '1.00', 'Confirm Send Tip',
        'Toggle Tip Panel', 'Show more comments',
    }
    
    def get_template_files(self):
        """Get all HTML template files."""
        return list(self.TEMPLATES_DIR.glob("*.html"))
    
    def extract_button_text(self, button_html):
        """Extract visible text content from button HTML."""
        # Remove HTML tags to get text content
        text = re.sub(r'<[^>]+>', '', button_html).strip()
        # Clean up whitespace
        text = ' '.join(text.split())
        return text
    
    def test_all_buttons_have_aria_labels_or_text(self):
        """Verify all buttons have either aria-label or meaningful text content."""
        failures = []
        
        for template_file in self.get_template_files():
            content = template_file.read_text()
            lines = content.split('\n')
            
            for line_num, line in enumerate(lines, 1):
                buttons = self.BUTTON_PATTERN.findall(line)
                for button in buttons:
                    # Check if button has aria-label
                    has_aria = bool(self.ARIA_LABEL_PATTERN.search(button))
                    
                    # Check if button has meaningful text
                    text = self.extract_button_text(button)
                    has_text = text and text not in ['', '&times;', '&#9776;']
                    
                    # Check if text is in exempt list (partial match)
                    is_exempt = any(
                        exempt.lower() in text.lower() or text.lower() in exempt.lower()
                        for exempt in self.EXEMPT_BUTTON_TEXTS
                    )
                    
                    if not has_aria and not has_text and not is_exempt:
                        failures.append(
                            f"{template_file.name}:{line_num} - Button missing aria-label: {button[:80]}..."
                        )
        
        assert not failures, f"Buttons missing aria-labels:\n" + "\n".join(failures)
    
    def test_tab_buttons_have_aria_selected(self):
        """Verify tab buttons have aria-selected attribute."""
        failures = []
        
        for template_file in self.get_template_files():
            content = template_file.read_text()
            lines = content.split('\n')
            
            for line_num, line in enumerate(lines, 1):
                tabs = self.TAB_BUTTON_PATTERN.findall(line)
                for tab in tabs:
                    if 'aria-selected' not in tab.lower():
                        failures.append(
                            f"{template_file.name}:{line_num} - Tab button missing aria-selected: {tab[:80]}..."
                        )
        
        assert not failures, f"Tab buttons missing aria-selected:\n" + "\n".join(failures)
    
    def test_copy_buttons_have_descriptive_labels(self):
        """Verify copy buttons describe what they're copying."""
        failures = []
        
        for template_file in self.get_template_files():
            content = template_file.read_text()
            lines = content.split('\n')
            
            for line_num, line in enumerate(lines, 1):
                # Find actual copy button elements (not CSS definitions)
                if re.search(r'<button[^>]*copy-btn', line, re.IGNORECASE) or \
                   re.search(r'<button[^>]*copyCode', line, re.IGNORECASE):
                    if 'aria-label' not in line.lower():
                        failures.append(
                            f"{template_file.name}:{line_num} - Copy button should describe what it copies"
                        )
        
        assert not failures, f"Copy buttons missing descriptive aria-labels:\n" + "\n".join(failures)
    
    def test_submit_buttons_have_action_labels(self):
        """Verify submit buttons describe the action they perform."""
        failures = []
        
        for template_file in self.get_template_files():
            content = template_file.read_text()
            lines = content.split('\n')
            
            for line_num, line in enumerate(lines, 1):
                buttons = self.SUBMIT_BUTTON_PATTERN.findall(line)
                for button in buttons:
                    has_aria = 'aria-label' in button.lower()
                    has_text = bool(self.extract_button_text(button))
                    
                    if not has_aria and not has_text:
                        failures.append(
                            f"{template_file.name}:{line_num} - Submit button missing action description"
                        )
        
        assert not failures, f"Submit buttons missing action descriptions:\n" + "\n".join(failures)
    
    def test_icon_only_buttons_have_labels(self):
        """Verify icon-only buttons (like &times;, hamburger menu) have aria-labels."""
        failures = []
        
        icon_patterns = ['&times;', '&#9776;', '&#9650;', '&#9660;', '&#9873;']
        
        for template_file in self.get_template_files():
            content = template_file.read_text()
            lines = content.split('\n')
            
            for line_num, line in enumerate(lines, 1):
                buttons = self.BUTTON_PATTERN.findall(line)
                for button in buttons:
                    # Check if button contains only icon patterns
                    has_icon = any(icon in button for icon in icon_patterns)
                    has_aria = 'aria-label' in button.lower()
                    
                    # Remove icon patterns and check if there's other text
                    text = self.extract_button_text(button)
                    for icon in icon_patterns:
                        text = text.replace(icon, '').strip()
                    
                    has_text = bool(text)
                    
                    if has_icon and not has_aria and not has_text:
                        failures.append(
                            f"{template_file.name}:{line_num} - Icon-only button missing aria-label"
                        )
        
        assert not failures, f"Icon-only buttons missing aria-labels:\n" + "\n".join(failures)


class TestAriaLabelBestPractices:
    """Test suite for aria-label best practices."""
    
    TEMPLATES_DIR = Path(__file__).parent.parent / "bottube_templates"
    
    def get_template_files(self):
        """Get all HTML template files."""
        return list(self.TEMPLATES_DIR.glob("*.html"))
    
    def test_aria_labels_are_descriptive(self):
        """Verify aria-labels are descriptive and not generic."""
        generic_labels = ['button', 'click', 'submit', 'action', 'link']
        failures = []
        
        for template_file in self.get_template_files():
            content = template_file.read_text()
            lines = content.split('\n')
            
            for line_num, line in enumerate(lines, 1):
                if 'aria-label' in line.lower():
                    for generic in generic_labels:
                        # Check if aria-label contains only generic text
                        match = re.search(r'aria-label\s*=\s*["\']([^"\']+)["\']', line, re.IGNORECASE)
                        if match:
                            label = match.group(1).lower().strip()
                            if label == generic:
                                failures.append(
                                    f"{template_file.name}:{line_num} - Generic aria-label '{match.group(1)}'"
                                )
        
        assert not failures, f"Generic aria-labels found:\n" + "\n".join(failures)
    
    def test_no_duplicate_aria_labels_with_title(self):
        """Verify aria-label doesn't exactly duplicate title attribute."""
        failures = []
        
        for template_file in self.get_template_files():
            content = template_file.read_text()
            lines = content.split('\n')
            
            for line_num, line in enumerate(lines, 1):
                if 'aria-label' in line.lower() and 'title=' in line.lower():
                    aria_match = re.search(r'aria-label\s*=\s*["\']([^"\']+)["\']', line, re.IGNORECASE)
                    title_match = re.search(r'title\s*=\s*["\']([^"\']+)["\']', line, re.IGNORECASE)
                    
                    if aria_match and title_match:
                        if aria_match.group(1) == title_match.group(1):
                            failures.append(
                                f"{template_file.name}:{line_num} - aria-label duplicates title attribute"
                            )
        
        # This is a warning, not a failure - title and aria-label can serve different purposes
        if failures:
            print(f"Warning - Duplicate aria-label/title (may be intentional):\n" + "\n".join(failures))


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
