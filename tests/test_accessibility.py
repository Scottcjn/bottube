"""
Accessibility Tests for BoTTube Templates
Issue #2139 - Accessibility bugs: missing aria-labels and keyboard accessibility

These tests verify that interactive elements have proper ARIA attributes
and keyboard navigation support as required by WCAG 2.1 Level AA.
"""

import os
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path


class _NestedAnchorParser(HTMLParser):
    """Count nested anchors in server-rendered template markup."""

    def __init__(self):
        super().__init__()
        self.anchor_depth = 0
        self.nested_anchors = 0

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            if self.anchor_depth:
                self.nested_anchors += 1
            self.anchor_depth += 1

    def handle_endtag(self, tag):
        if tag == "a" and self.anchor_depth:
            self.anchor_depth -= 1


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
        self.assertIn('aria-controls="site-nav"', match.group(0),
                      "Mobile menu button missing aria-controls")

    def test_mobile_menu_controls_named_nav(self):
        """Test that the mobile menu button references the header nav."""
        content = self.read_file(self.TEMPLATE_DIR / 'base.html')
        self.assertIn('id="site-nav"', content,
                      "Header navigation missing id referenced by aria-controls")
    
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

    def test_video_cards_do_not_nest_links(self):
        """Video cards must not put channel or category links inside watch links."""
        for template_name in ('index.html', 'category.html', 'search.html'):
            with self.subTest(template=template_name):
                content = self.read_file(self.TEMPLATE_DIR / template_name)
                parser = _NestedAnchorParser()
                parser.feed(content)
                self.assertEqual(
                    parser.nested_anchors,
                    0,
                    f"{template_name} contains invalid nested anchor elements",
                )

        content = self.read_file(self.TEMPLATE_DIR / 'index.html')
        hybrid_card = re.search(
            r"return ''(?P<markup>.*?)\+ '</div>';",
            content,
            re.DOTALL,
        )
        self.assertIsNotNone(hybrid_card, "Hybrid recommendation card renderer not found")
        markup = hybrid_card.group("markup")
        thumbnail_close = markup.find("+   '</a>'")
        video_info = markup.find("'<div class=\"video-info\">'")
        channel_link = markup.find("'<a href=\"/agent/")
        self.assertGreaterEqual(thumbnail_close, 0)
        self.assertGreater(video_info, thumbnail_close)
        self.assertGreater(channel_link, video_info)
    
    def test_search_form_has_aria_label(self):
        """Test that search form has proper accessibility attributes."""
        content = self.read_file(self.TEMPLATE_DIR / 'base.html')
        match = re.search(r'<form[^>]*class="search-bar"[^>]*>', content)
        self.assertIsNotNone(match, "Search form not found")
        self.assertIn('role="search"', match.group(0),
                      "Search form should have role='search'")
        self.assertIn('aria-label', match.group(0),
                      "Search form missing aria-label")

        input_match = re.search(r'<input[^>]*name="q"[^>]*>', content)
        self.assertIsNotNone(input_match, "Header search input not found")
        self.assertIn('aria-label', input_match.group(0),
                      "Header search input missing accessible name")

    def test_agents_page_search_input_has_accessible_name(self):
        """Test that the agents page filter input has a programmatic label."""
        content = self.read_file(self.TEMPLATE_DIR / 'agents.html')
        input_match = re.search(r'<input[^>]*name="q"[^>]*>', content)
        self.assertIsNotNone(input_match, "Agents page search input not found")
        input_markup = input_match.group(0)
        self.assertIn('id="agent-search"', input_markup,
                      "Agents page search input should expose a stable id")
        self.assertIn('aria-label="Search agents"', input_markup,
                      "Agents page search input missing aria-label")
        self.assertRegex(
            content,
            r'<label[^>]*for="agent-search"[^>]*>Search agents</label>',
            "Agents page search input missing associated label",
        )

    def test_authenticated_form_inputs_have_associated_labels(self):
        """Collaboration and wallet text inputs need programmatic labels."""
        controls = (
            ('collaboration_new.html', 'participantInput', 'Invite Creators'),
            ('settings_wallet.html', 'linked-rtc-wallet', 'Linked RTC wallet address'),
        )
        for template_name, control_id, label_text in controls:
            with self.subTest(template=template_name, control=control_id):
                content = self.read_file(self.TEMPLATE_DIR / template_name)
                self.assertRegex(
                    content,
                    rf'<label[^>]*for="{re.escape(control_id)}"[^>]*>'
                    rf'[^<]*{re.escape(label_text)}',
                    f"{control_id} missing associated label",
                )

    def test_collaboration_type_cards_expose_keyboard_radio_group(self):
        """Collaboration type cards should expose radio semantics and keyboard support."""
        content = self.read_file(self.TEMPLATE_DIR / 'collaboration_new.html')

        self.assertRegex(
            content,
            r'<div[^>]*class="collab-type-selector"[^>]*role="radiogroup"[^>]*aria-labelledby="collab-type-label"',
            "Collaboration type selector should expose a named radio group",
        )
        self.assertIn('id="collab-type-label"', content,
                      "Collaboration type selector missing visible label id")

        expected_states = {
            "duet": ('aria-checked="true"', 'tabindex="0"'),
            "co-upload": ('aria-checked="false"', 'tabindex="-1"'),
            "remix": ('aria-checked="false"', 'tabindex="-1"'),
        }
        for collab_type, (checked_state, tab_index) in expected_states.items():
            with self.subTest(option=collab_type):
                self.assertRegex(
                    content,
                    rf'data-type="{re.escape(collab_type)}"[^>]*role="radio"[^>]*{checked_state}[^>]*{tab_index}',
                    f"{collab_type} option should expose the expected radio state",
                )

        self.assertIn('function handleTypeOptionKeydown', content,
                      "Collaboration type cards missing keyboard handler")
        for key in ('ArrowRight', 'ArrowDown', 'ArrowLeft', 'ArrowUp'):
            self.assertIn(f"'{key}'", content,
                          f"Collaboration type cards should handle {key}")
        self.assertIn("getTypeOption(type).focus()", content,
                      "Keyboard activation should keep focus on the selected radio")
    def test_bridge_history_limit_inputs_have_accessible_names(self):
        """Bridge history limits must identify what their numeric value controls."""
        for template_name in ('bridge_base.html', 'bridge_wrtc.html'):
            with self.subTest(template=template_name):
                content = self.read_file(self.TEMPLATE_DIR / template_name)
                self.assertRegex(
                    content,
                    r'<label[^>]*class="sr-only"[^>]*for="historyLimitInput"[^>]*>'
                    r'History entries to load</label>',
                    f"{template_name} history limit is missing its label",
                )
                self.assertRegex(
                    content,
                    r'<input[^>]*id="historyLimitInput"[^>]*>',
                    f"{template_name} history limit input not found",
                )
    
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

    def test_bridge_result_panels_are_live_regions(self):
        """Bridge operation results should be announced by screen readers."""
        panel_ids = ("infoPanel", "depositPanel", "withdrawPanel", "historyPanel")

        for template_name in ("bridge_wrtc.html", "bridge_base.html"):
            content = self.read_file(self.TEMPLATE_DIR / template_name)
            for panel_id in panel_ids:
                match = re.search(
                    rf'<div[^>]*id="{panel_id}"[^>]*>',
                    content,
                )
                self.assertIsNotNone(
                    match,
                    f"{template_name} is missing #{panel_id}",
                )
                panel = match.group(0)
                self.assertIn('role="status"', panel)
                self.assertIn('aria-live="polite"', panel)
                self.assertIn('aria-atomic="true"', panel)


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
