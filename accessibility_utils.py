import re
import json
from urllib.parse import quote, unquote
from colorsys import rgb_to_hls


def generate_aria_label(element_type, context=None, action=None):
    """Generate appropriate ARIA labels for different UI elements"""
    
    if element_type == 'category_filter':
        if context:
            return f"Filter videos by {context} category"
        return "Filter videos by category"
    
    elif element_type == 'trending_link':
        if context:
            return f"View trending {context} videos"
        return "View trending videos"
    
    elif element_type == 'video_thumbnail':
        if context:
            return f"Watch video: {context}"
        return "Watch video"
    
    elif element_type == 'channel_link':
        if context:
            return f"Visit {context} channel"
        return "Visit channel"
    
    elif element_type == 'action_button':
        if action and context:
            return f"{action} {context}"
        elif action:
            return action
        return "Perform action"
    
    elif element_type == 'navigation':
        if context:
            return f"Navigate to {context}"
        return "Navigate"
    
    return "Interactive element"


def sanitize_category_param(category_value):
    """Clean and validate category parameters for URLs"""
    
    if not category_value:
        return None
    
    # Remove any JSON-like formatting artifacts
    category_clean = str(category_value).strip()
    
    # Remove curly braces and other JSON artifacts
    category_clean = re.sub(r'[{}"\[\]]', '', category_clean)
    
    # Handle common category names
    valid_categories = {
        'music': 'music',
        'gaming': 'gaming', 
        'news': 'news',
        'sports': 'sports',
        'entertainment': 'entertainment',
        'education': 'education',
        'technology': 'technology',
        'science': 'science',
        'comedy': 'comedy',
        'film': 'film',
        'animation': 'animation',
        'pets': 'pets',
        'travel': 'travel',
        'howto': 'howto',
        'style': 'style',
        'nonprofits': 'nonprofits'
    }
    
    # Convert to lowercase and check if valid
    category_lower = category_clean.lower()
    if category_lower in valid_categories:
        return valid_categories[category_lower]
    
    # If not in predefined list, sanitize manually
    category_clean = re.sub(r'[^a-zA-Z0-9_-]', '', category_clean)
    
    return category_clean if len(category_clean) > 0 else None


def build_category_url(base_path, category):
    """Build properly formatted category URL"""
    
    clean_category = sanitize_category_param(category)
    if not clean_category:
        return base_path
    
    # URL encode the category parameter
    encoded_category = quote(clean_category)
    
    separator = '&' if '?' in base_path else '?'
    return f"{base_path}{separator}category={encoded_category}"


def hex_to_rgb(hex_color):
    """Convert hex color to RGB tuple"""
    
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        return None
    
    try:
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def calculate_relative_luminance(rgb):
    """Calculate relative luminance for contrast checking"""
    
    def linearize(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    
    r, g, b = [linearize(c) for c in rgb]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def check_color_contrast(foreground_hex, background_hex):
    """Check if color combination meets WCAG contrast requirements"""
    
    fg_rgb = hex_to_rgb(foreground_hex)
    bg_rgb = hex_to_rgb(background_hex)
    
    if not fg_rgb or not bg_rgb:
        return None
    
    fg_lum = calculate_relative_luminance(fg_rgb)
    bg_lum = calculate_relative_luminance(bg_rgb)
    
    # Ensure lighter color is in numerator
    lighter = max(fg_lum, bg_lum)
    darker = min(fg_lum, bg_lum)
    
    contrast_ratio = (lighter + 0.05) / (darker + 0.05)
    
    # WCAG 2.1 requirements
    aa_normal = contrast_ratio >= 4.5  # Normal text AA
    aa_large = contrast_ratio >= 3.0   # Large text AA
    aaa_normal = contrast_ratio >= 7.0  # Normal text AAA
    
    return {
        'ratio': round(contrast_ratio, 2),
        'aa_normal': aa_normal,
        'aa_large': aa_large, 
        'aaa_normal': aaa_normal,
        'passes_aa': aa_normal
    }


def get_accessible_color_suggestions(base_color_hex, background_hex='#ffffff'):
    """Suggest accessible color variations"""
    
    base_rgb = hex_to_rgb(base_color_hex)
    if not base_rgb:
        return []
    
    suggestions = []
    
    # Convert to HLS for easier manipulation
    r, g, b = [c/255.0 for c in base_rgb]
    h, l, s = rgb_to_hls(r, g, b)
    
    # Try different lightness values
    lightness_values = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    
    for new_l in lightness_values:
        new_r, new_g, new_b = [int(c * 255) for c in rgb_to_hls(h, new_l, s)]
        new_hex = f"#{new_r:02x}{new_g:02x}{new_b:02x}"
        
        contrast_check = check_color_contrast(new_hex, background_hex)
        if contrast_check and contrast_check['passes_aa']:
            suggestions.append({
                'hex': new_hex,
                'contrast_ratio': contrast_check['ratio']
            })
    
    # Sort by contrast ratio descending
    suggestions.sort(key=lambda x: x['contrast_ratio'], reverse=True)
    
    return suggestions[:5]  # Return top 5 suggestions


def validate_accessibility_attributes(element_data):
    """Validate that UI elements have proper accessibility attributes"""
    
    issues = []
    
    # Check for missing alt text on images
    if element_data.get('type') == 'image' and not element_data.get('alt'):
        issues.append("Missing alt text for image")
    
    # Check for missing ARIA labels on interactive elements
    interactive_types = ['button', 'link', 'input', 'select']
    if element_data.get('type') in interactive_types:
        has_label = any([
            element_data.get('aria_label'),
            element_data.get('aria_labelledby'), 
            element_data.get('title'),
            element_data.get('text_content')
        ])
        if not has_label:
            issues.append(f"Missing accessible label for {element_data.get('type')}")
    
    # Check for proper heading hierarchy
    if element_data.get('type', '').startswith('h') and element_data.get('type')[1:].isdigit():
        level = int(element_data.get('type')[1:])
        parent_level = element_data.get('parent_heading_level', 0)
        if level > parent_level + 1:
            issues.append(f"Heading level {level} skips levels in hierarchy")
    
    return issues


def format_accessibility_report(page_issues):
    """Format accessibility issues into a readable report"""
    
    if not page_issues:
        return "No accessibility issues found."
    
    report_lines = ["Accessibility Issues Found:", ""]
    
    issue_categories = {}
    for issue in page_issues:
        category = issue.get('category', 'General')
        if category not in issue_categories:
            issue_categories[category] = []
        issue_categories[category].append(issue)
    
    for category, issues in issue_categories.items():
        report_lines.append(f"## {category}")
        for i, issue in enumerate(issues, 1):
            report_lines.append(f"{i}. {issue.get('description', 'Unknown issue')}")
            if issue.get('element'):
                report_lines.append(f"   Element: {issue['element']}")
            if issue.get('suggestion'):
                report_lines.append(f"   Suggestion: {issue['suggestion']}")
        report_lines.append("")
    
    return "\n".join(report_lines)