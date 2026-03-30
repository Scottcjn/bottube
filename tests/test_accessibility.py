"""
Accessibility Tests for BoTTube Templates
Issue #2139 - Accessibility bugs: missing aria-labels and keyboard accessibility

These tests verify that interactive elements have proper ARIA attributes
and keyboard navigation support as required by WCAG 2.1 Level AA.
"""

import os
import re
import unittest
from pathlib import Path


class TestAccessibilityAttributes(unittest.TestCase):
    """Test suite for accessibility attributes in HTML templates."""
    
    TEMPLATE_DIR = Path(__file__).parent.parent / 'bottube_templates'
    STATIC_DIR = Path(__file__).parent.parent / 'bottube_static'
    
    def read_file(self, path):
        """Read file content."""
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def test_mobile_menu_button_has_aria_label(self):
        """Test that mobile menu button has aria-label attribute."""
        content = self.read_file(self.TEMPLATE_DIR / 'base.html')
        # Mobile menu button should have aria-label="Menu"
        match = re.search(r'<button[^>]*class="mobile-menu-btn"[^>]*>', content)
        self.assertIsNotNone(match, "Mobile menu button not found")
        self.assertIn('aria-label', match.group(0), 
                      "Mobile menu button missing aria-label")
        self.assertIn('aria-expanded', match.group(0),
                      "Mobile menu button missing aria-expanded")
    
    def test_notification_bell_has_aria_attributes(self):
        """Test that notification bell has proper ARIA attributes."""
        content = self.read_file(self.TEMPLATE_DIR / 'base.html')
        # Notification bell should have aria-label and role
        match = re.search(r'id="bell-btn"[^>]*>', content)
        if match:
            # Check context around bell-btn
            start = max(0, match.start() - 200)
            context = content[start:match.end()]
            self.assertIn('aria-label', context,
                          "Notification bell missing aria-label")
            self.assertIn('role="button"', context,
                          "Notification bell should have role='button'")
    
    def test_subscribe_button_has_aria_label(self):
        """Test that subscribe button has aria-label attribute."""
        content = self.read_file(self.TEMPLATE_DIR / 'channel.html')
        match = re.search(r'<button[^>]*id="subscribe-btn"[^>]*>', content)
        if match:
            self.assertIn('aria-label', match.group(0),
                          "Subscribe button missing aria-label")
            self.assertIn('aria-pressed', match.group(0),
                          "Subscribe button missing aria-pressed state")
            self.assertIn('type="button"', match.group(0),
                          "Subscribe button should have type='button'")
    
    def test_hero_action_buttons_have_aria_labels(self):
        """Test that hero action buttons have aria-labels."""
        content = self.read_file(self.TEMPLATE_DIR / 'index.html')
        # Check hero-actions container has role="group"
        match = re.search(r'<div[^>]*class="hero-actions"[^>]*>', content)
        self.assertIsNotNone(match, "Hero actions container not found")
        self.assertIn('role="group"', match.group(0),
                      "Hero actions should have role='group'")
        self.assertIn('aria-label', match.group(0),
                      "Hero actions container missing aria-label")
    
    def test_search_form_has_aria_label(self):
        """Test that search form has proper accessibility attributes."""
        content = self.read_file(self.TEMPLATE_DIR / 'base.html')
        match = re.search(r'<form[^>]*class="search-bar"[^>]*>', content)
        self.assertIsNotNone(match, "Search form not found")
        self.assertIn('role="search"', match.group(0),
                      "Search form should have role='search'")
        self.assertIn('aria-label', match.group(0),
                      "Search form missing aria-label")
    
    def test_skip_link_present(self):
        """Test that skip link for keyboard navigation is present."""
        content = self.read_file(self.TEMPLATE_DIR / 'base.html')
        self.assertIn('skip-link', content,
                      "Skip link for keyboard navigation not found")
        self.assertIn('.sr-only', content,
                      "Screen reader only class not found")
    
    def test_focus_visible_styles_present(self):
        """Test that focus-visible styles are defined."""
        content = self.read_file(self.TEMPLATE_DIR / 'base.html')
        self.assertIn(':focus-visible', content,
                      "Focus-visible styles not found")
        self.assertIn('outline', content,
                      "Focus outline styles not found")


class TestKeyboardAccessibility(unittest.TestCase):
    """Test suite for keyboard accessibility in JavaScript."""
    
    STATIC_DIR = Path(__file__).parent.parent / 'bottube_static'
    
    def read_file(self, path):
        """Read file content."""
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def test_mobile_menu_keyboard_handler(self):
        """Test that mobile menu has keyboard event handler."""
        content = self.read_file(self.STATIC_DIR / 'base.js')
        self.assertIn('keydown', content,
                      "Keyboard event handler not found")
        self.assertIn('"Enter"', content,
                      "Enter key handler not found")
        self.assertIn('" "', content,
                      "Space key handler not found")
    
    def test_notification_bell_keyboard_handler(self):
        """Test that notification bell has keyboard handler."""
        content = self.read_file(self.STATIC_DIR / 'base.js')
        # Check for keyboard handler in notification context
        notif_section = content[content.find('initNotifications'):content.find('initPipBannerCopy')]
        self.assertIn('keydown', notif_section,
                      "Notification bell keyboard handler not found")
    
    def test_prevent_default_on_keyboard_events(self):
        """Test that keyboard events have preventDefault."""
        content = self.read_file(self.STATIC_DIR / 'base.js')
        # Find keydown handlers and check for preventDefault
        keydown_matches = re.finditer(r'keydown.*?function\s*\([^)]*\)\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', 
                                      content, re.DOTALL)
        has_prevent_default = False
        for match in keydown_matches:
            if 'preventDefault' in match.group(0):
                has_prevent_default = True
                break
        self.assertTrue(has_prevent_default,
                        "Keyboard handlers should call preventDefault")


class TestARIAPatterns(unittest.TestCase):
    """Test suite for ARIA design patterns."""
    
    TEMPLATE_DIR = Path(__file__).parent.parent / 'bottube_templates'
    
    def read_file(self, path):
        """Read file content."""
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def test_video_cards_have_aria_labels(self):
        """Test that video cards have aria-labels."""
        content = self.read_file(self.TEMPLATE_DIR / 'search.html')
        # Video cards should have aria-label for screen readers
        self.assertIn('aria-label="Watch', content,
                      "Video cards should have aria-label for watch action")
    
    def test_main_landmark_present(self):
        """Test that main landmark is present."""
        content = self.read_file(self.TEMPLATE_DIR / 'base.html')
        self.assertIn('id="main-content"', content,
                      "Main content landmark not found")
    
    def test_banner_landmark_present(self):
        """Test that banner landmark is present."""
        content = self.read_file(self.TEMPLATE_DIR / 'base.html')
        self.assertIn('role="banner"', content,
                      "Header banner landmark not found")
    
    def test_contentinfo_landmark_present(self):
        """Test that contentinfo landmark is present."""
        content = self.read_file(self.TEMPLATE_DIR / 'base.html')
        self.assertIn('role="contentinfo"', content,
                      "Footer contentinfo landmark not found")


class TestAccessibilityDocumentation(unittest.TestCase):
    """Test that accessibility documentation exists."""
    
    ROOT_DIR = Path(__file__).parent.parent
    
    def test_accessibility_fixes_doc_exists(self):
        """Test that ACCESSIBILITY_FIXES.md documentation exists."""
        doc_path = self.ROOT_DIR / 'ACCESSIBILITY_FIXES.md'
        self.assertTrue(doc_path.exists(),
                        "ACCESSIBILITY_FIXES.md documentation not found")
    
    def test_accessibility_fixes_doc_has_content(self):
        """Test that documentation has required sections."""
        doc_path = self.ROOT_DIR / 'ACCESSIBILITY_FIXES.md'
        if doc_path.exists():
            content = doc_path.read_text(encoding='utf-8')
            self.assertIn('Issue #2139', content,
                          "Documentation should reference Issue #2139")
            self.assertIn('aria-label', content.lower(),
                          "Documentation should mention aria-label fixes")
            self.assertIn('keyboard', content.lower(),
                          "Documentation should mention keyboard accessibility")


if __name__ == '__main__':
    unittest.main()
