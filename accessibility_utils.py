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
        'people': 'people',
        'pets': 'pets',
        'travel': 'travel',
        'autos': 'autos',
        'howto': 'howto'
    }
    
    # Normalize and validate
    category_lower = category_clean.lower().strip()
    
    if category_lower in valid_categories:
        return valid_categories[category_lower]
    
    # Return None for invalid categories
    return None


def check_color_contrast(foreground, background):
    """Check if color combination meets WCAG contrast requirements"""
    
    def hex_to_rgb(hex_color):
        """Convert hex color to RGB tuple"""
        hex_color = hex_color.lstrip('#')
        if len(hex_color) == 3:
            hex_color = ''.join([c*2 for c in hex_color])
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    def get_luminance(rgb):
        """Calculate relative luminance of RGB color"""
        rgb_linear = []
        for c in rgb:
            c = c / 255.0
            if c <= 0.03928:
                rgb_linear.append(c / 12.92)
            else:
                rgb_linear.append(pow((c + 0.055) / 1.055, 2.4))
        return 0.2126 * rgb_linear[0] + 0.7152 * rgb_linear[1] + 0.0722 * rgb_linear[2]
    
    try:
        fg_rgb = hex_to_rgb(foreground)
        bg_rgb = hex_to_rgb(background)
        
        fg_lum = get_luminance(fg_rgb)
        bg_lum = get_luminance(bg_rgb)
        
        # Calculate contrast ratio
        if fg_lum > bg_lum:
            contrast = (fg_lum + 0.05) / (bg_lum + 0.05)
        else:
            contrast = (bg_lum + 0.05) / (fg_lum + 0.05)
        
        return {
            'ratio': round(contrast, 2),
            'aa_normal': contrast >= 4.5,
            'aa_large': contrast >= 3.0,
            'aaa_normal': contrast >= 7.0,
            'aaa_large': contrast >= 4.5
        }
    except (ValueError, TypeError):
        return None


def validate_heading_structure(html_content):
    """Validate heading hierarchy in HTML content"""
    
    headings = re.findall(r'<h([1-6])[^>]*>', html_content, re.IGNORECASE)
    
    if not headings:
        return {'valid': True, 'issues': []}
    
    issues = []
    heading_levels = [int(h) for h in headings]
    
    # Check if starts with h1
    if heading_levels and heading_levels[0] != 1:
        issues.append('Document should start with h1')
    
    # Check for level skipping
    for i in range(1, len(heading_levels)):
        current = heading_levels[i]
        previous = heading_levels[i-1]
        
        if current > previous + 1:
            issues.append(f'Heading level skipped: h{previous} to h{current}')
    
    return {
        'valid': len(issues) == 0,
        'issues': issues,
        'levels': heading_levels
    }