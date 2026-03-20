import sqlite3
import os
import re
from collections import defaultdict
from bs4 import BeautifulSoup
from colorsys import rgb_to_hls
import math

class AccessibilityAuditor:
    def __init__(self):
        self.issues = []
        self.templates_dir = 'templates'
        self.static_dir = 'static'

    def audit_templates(self):
        """Scan all HTML templates for accessibility issues"""
        template_files = []

        if os.path.exists(self.templates_dir):
            for root, dirs, files in os.walk(self.templates_dir):
                for file in files:
                    if file.endswith('.html'):
                        template_files.append(os.path.join(root, file))

        for template_file in template_files:
            self._audit_template_file(template_file)

        return self.issues

    def _audit_template_file(self, file_path):
        """Audit a single template file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            soup = BeautifulSoup(content, 'html.parser')
            template_name = os.path.relpath(file_path, self.templates_dir)

            self._check_images_alt_text(soup, template_name)
            self._check_form_labels(soup, template_name)
            self._check_heading_structure(soup, template_name)
            self._check_color_contrast(soup, template_name)
            self._check_keyboard_navigation(soup, template_name)
            self._check_aria_labels(soup, template_name)
            self._check_semantic_html(soup, template_name)
            self._check_focus_management(soup, template_name)

        except Exception as e:
            self.issues.append({
                'type': 'file_error',
                'severity': 'high',
                'file': file_path,
                'message': f'Error reading template: {str(e)}'
            })

    def _check_images_alt_text(self, soup, template_name):
        """Check for missing alt text on images"""
        images = soup.find_all('img')

        for img in images:
            if not img.get('alt') and img.get('alt') != '':
                self.issues.append({
                    'type': 'missing_alt_text',
                    'severity': 'high',
                    'file': template_name,
                    'element': str(img)[:100] + '...' if len(str(img)) > 100 else str(img),
                    'message': 'Image missing alt attribute for screen readers'
                })
            elif img.get('alt') == '':
                # Empty alt is OK for decorative images
                pass
            elif img.get('alt') and len(img.get('alt').strip()) < 3:
                self.issues.append({
                    'type': 'poor_alt_text',
                    'severity': 'medium',
                    'file': template_name,
                    'element': str(img)[:100] + '...' if len(str(img)) > 100 else str(img),
                    'message': f'Alt text too short or vague: "{img.get("alt")}"'
                })

    def _check_form_labels(self, soup, template_name):
        """Check form inputs have proper labels"""
        inputs = soup.find_all(['input', 'textarea', 'select'])

        for input_elem in inputs:
            input_type = input_elem.get('type', 'text')

            # Skip hidden inputs and buttons
            if input_type in ['hidden', 'submit', 'button']:
                continue

            input_id = input_elem.get('id')
            input_name = input_elem.get('name')

            # Check for associated label
            has_label = False
            if input_id:
                label = soup.find('label', {'for': input_id})
                if label:
                    has_label = True

            # Check for aria-label or aria-labelledby
            if not has_label and not input_elem.get('aria-label') and not input_elem.get('aria-labelledby'):
                self.issues.append({
                    'type': 'missing_form_label',
                    'severity': 'high',
                    'file': template_name,
                    'element': str(input_elem)[:100] + '...' if len(str(input_elem)) > 100 else str(input_elem),
                    'message': f'Form input missing label or aria-label (name: {input_name})'
                })

    def _check_heading_structure(self, soup, template_name):
        """Check heading hierarchy (h1, h2, h3, etc.)"""
        headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])

        if not headings:
            self.issues.append({
                'type': 'no_headings',
                'severity': 'medium',
                'file': template_name,
                'message': 'Page has no heading structure for navigation'
            })
            return

        prev_level = 0
        h1_count = 0

        for heading in headings:
            current_level = int(heading.name[1])

            if heading.name == 'h1':
                h1_count += 1

            if current_level - prev_level > 1:
                self.issues.append({
                    'type': 'heading_skip',
                    'severity': 'medium',
                    'file': template_name,
                    'element': str(heading)[:100] + '...' if len(str(heading)) > 100 else str(heading),
                    'message': f'Heading level jumps from h{prev_level} to h{current_level}'
                })

            prev_level = current_level

        if h1_count > 1:
            self.issues.append({
                'type': 'multiple_h1',
                'severity': 'medium',
                'file': template_name,
                'message': f'Page has {h1_count} h1 elements (should have only one)'
            })

    def _check_color_contrast(self, soup, template_name):
        """Basic color contrast checking for inline styles"""
        elements_with_style = soup.find_all(attrs={'style': True})

        for elem in elements_with_style:
            style = elem.get('style', '')

            # Extract color and background-color from inline styles
            color_match = re.search(r'color\s*:\s*([^;]+)', style)
            bg_color_match = re.search(r'background-color\s*:\s*([^;]+)', style)

            if color_match and bg_color_match:
                text_color = color_match.group(1).strip()
                bg_color = bg_color_match.group(1).strip()

                ratio = self._calculate_contrast_ratio(text_color, bg_color)
                if ratio and ratio < 4.5:  # WCAG AA standard
                    self.issues.append({
                        'type': 'low_color_contrast',
                        'severity': 'high',
                        'file': template_name,
                        'element': str(elem)[:100] + '...' if len(str(elem)) > 100 else str(elem),
                        'message': f'Low color contrast ratio: {ratio:.2f} (should be >= 4.5)',
                        'colors': f'text: {text_color}, background: {bg_color}'
                    })

    def _check_keyboard_navigation(self, soup, template_name):
        """Check for keyboard navigation issues"""
        interactive_elements = soup.find_all(['a', 'button', 'input', 'textarea', 'select'])

        for elem in interactive_elements:
            # Check for missing href on links
            if elem.name == 'a' and not elem.get('href'):
                self.issues.append({
                    'type': 'missing_href',
                    'severity': 'medium',
                    'file': template_name,
                    'element': str(elem)[:100] + '...' if len(str(elem)) > 100 else str(elem),
                    'message': 'Link element missing href attribute'
                })

            # Check for tabindex issues
            tabindex = elem.get('tabindex')
            if tabindex and int(tabindex) > 0:
                self.issues.append({
                    'type': 'positive_tabindex',
                    'severity': 'medium',
                    'file': template_name,
                    'element': str(elem)[:100] + '...' if len(str(elem)) > 100 else str(elem),
                    'message': f'Positive tabindex ({tabindex}) disrupts natural tab order'
                })

    def _check_aria_labels(self, soup, template_name):
        """Check ARIA label usage"""
        elements_with_aria = soup.find_all(attrs={'aria-label': True})

        for elem in elements_with_aria:
            aria_label = elem.get('aria-label', '').strip()
            if not aria_label or len(aria_label) < 2:
                self.issues.append({
                    'type': 'empty_aria_label',
                    'severity': 'medium',
                    'file': template_name,
                    'element': str(elem)[:100] + '...' if len(str(elem)) > 100 else str(elem),
                    'message': 'Empty or very short aria-label attribute'
                })

        # Check for buttons without accessible names
        buttons = soup.find_all('button')
        for button in buttons:
            has_text = button.get_text(strip=True)
            has_aria_label = button.get('aria-label')
            has_aria_labelledby = button.get('aria-labelledby')

            if not has_text and not has_aria_label and not has_aria_labelledby:
                self.issues.append({
                    'type': 'button_no_accessible_name',
                    'severity': 'high',
                    'file': template_name,
                    'element': str(button)[:100] + '...' if len(str(button)) > 100 else str(button),
                    'message': 'Button has no accessible name for screen readers'
                })

    def _check_semantic_html(self, soup, template_name):
        """Check for proper semantic HTML usage"""
        # Check for generic div/span usage where semantic elements would be better
        divs_with_click = soup.find_all('div', attrs={'onclick': True})
        spans_with_click = soup.find_all('span', attrs={'onclick': True})

        for elem in divs_with_click + spans_with_click:
            self.issues.append({
                'type': 'clickable_non_interactive',
                'severity': 'high',
                'file': template_name,
                'element': str(elem)[:100] + '...' if len(str(elem)) > 100 else str(elem),
                'message': f'Clickable {elem.name} should be a button or link for accessibility'
            })

        # Check for missing main landmark
        main_elem = soup.find('main')
        if not main_elem and soup.find('body'):
            self.issues.append({
                'type': 'missing_main_landmark',
                'severity': 'medium',
                'file': template_name,
                'message': 'Page missing <main> landmark for screen reader navigation'
            })

    def _check_focus_management(self, soup, template_name):
        """Check focus management issues"""
        # Check for elements that should not receive focus
        elements_with_tabindex_negative = soup.find_all(attrs={'tabindex': '-1'})

        for elem in elements_with_tabindex_negative:
            if elem.name not in ['div', 'span', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                self.issues.append({
                    'type': 'unnecessary_negative_tabindex',
                    'severity': 'low',
                    'file': template_name,
                    'element': str(elem)[:100] + '...' if len(str(elem)) > 100 else str(elem),
                    'message': 'Interactive element has tabindex="-1" which may prevent keyboard access'
                })

    def _calculate_contrast_ratio(self, color1, color2):
        """Calculate contrast ratio between two colors"""
        try:
            rgb1 = self._parse_color(color1)
            rgb2 = self._parse_color(color2)

            if not rgb1 or not rgb2:
                return None

            lum1 = self._get_luminance(rgb1)
            lum2 = self._get_luminance(rgb2)

            lighter = max(lum1, lum2)
            darker = min(lum1, lum2)

            return (lighter + 0.05) / (darker + 0.05)
        except:
            return None

    def _parse_color(self, color_str):
        """Parse color string to RGB values"""
        color_str = color_str.strip().lower()

        # Handle hex colors
        if color_str.startswith('#'):
            if len(color_str) == 4:  # #rgb
                r = int(color_str[1], 16) * 17
                g = int(color_str[2], 16) * 17
                b = int(color_str[3], 16) * 17
            elif len(color_str) == 7:  # #rrggbb
                r = int(color_str[1:3], 16)
                g = int(color_str[3:5], 16)
                b = int(color_str[5:7], 16)
            else:
                return None
            return (r, g, b)

        # Handle rgb() format
        rgb_match = re.match(r'rgb\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', color_str)
        if rgb_match:
            return tuple(int(x) for x in rgb_match.groups())

        # Handle basic color names
        color_map = {
            'black': (0, 0, 0),
            'white': (255, 255, 255),
            'red': (255, 0, 0),
            'green': (0, 128, 0),
            'blue': (0, 0, 255),
            'gray': (128, 128, 128),
            'grey': (128, 128, 128)
        }

        return color_map.get(color_str)

    def _get_luminance(self, rgb):
        """Calculate relative luminance of RGB color"""
        def gamma_correct(c):
            c = c / 255.0
            if c <= 0.03928:
                return c / 12.92
            else:
                return pow((c + 0.055) / 1.055, 2.4)

        r, g, b = rgb
        return 0.2126 * gamma_correct(r) + 0.7152 * gamma_correct(g) + 0.0722 * gamma_correct(b)

    def generate_report(self):
        """Generate accessibility audit report"""
        if not self.issues:
            return "No accessibility issues found!"

        issues_by_severity = defaultdict(list)
        issues_by_type = defaultdict(int)

        for issue in self.issues:
            issues_by_severity[issue['severity']].append(issue)
            issues_by_type[issue['type']] += 1

        report = []
        report.append("ACCESSIBILITY AUDIT REPORT")
        report.append("=" * 50)
        report.append(f"Total issues found: {len(self.issues)}\n")

        # Summary by severity
        report.append("ISSUES BY SEVERITY:")
        for severity in ['high', 'medium', 'low']:
            count = len(issues_by_severity[severity])
            if count > 0:
                report.append(f"  {severity.upper()}: {count}")
        report.append("")

        # Summary by type
        report.append("ISSUES BY TYPE:")
        for issue_type, count in sorted(issues_by_type.items()):
            report.append(f"  {issue_type.replace('_', ' ').title()}: {count}")
        report.append("")

        # Detailed issues
        report.append("DETAILED ISSUES:")
        report.append("-" * 30)

        for severity in ['high', 'medium', 'low']:
            if issues_by_severity[severity]:
                report.append(f"\n{severity.upper()} PRIORITY:")
                for issue in issues_by_severity[severity]:
                    report.append(f"  File: {issue['file']}")
                    report.append(f"  Type: {issue['type'].replace('_', ' ').title()}")
                    report.append(f"  Message: {issue['message']}")
                    if 'element' in issue:
                        report.append(f"  Element: {issue['element']}")
                    if 'colors' in issue:
                        report.append(f"  Colors: {issue['colors']}")
                    report.append("")

        return "\n".join(report)

    def save_report(self, filename='accessibility_report.txt'):
        """Save accessibility report to file"""
        report = self.generate_report()
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(report)
        return filename

def run_accessibility_audit():
    """Run accessibility audit and return results"""
    auditor = AccessibilityAuditor()
    auditor.audit_templates()
    return auditor.generate_report(), auditor.issues

if __name__ == '__main__':
    auditor = AccessibilityAuditor()
    auditor.audit_templates()

    report_file = auditor.save_report()
    print(f"Accessibility audit complete! Report saved to {report_file}")
    print("\n" + auditor.generate_report())
