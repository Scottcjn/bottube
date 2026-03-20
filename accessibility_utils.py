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
        'autos': 'autos'
    }
    
    # Normalize to lowercase and check against valid categories
    category_lower = category_clean.lower()
    
    if category_lower in valid_categories:
        return valid_categories[category_lower]
    
    # If not in predefined list, clean and validate format
    category_clean = re.sub(r'[^a-zA-Z0-9_-]', '', category_clean)
    
    if len(category_clean) > 0 and len(category_clean) <= 50:
        return category_clean.lower()
    
    return None


def check_color_contrast_ratio(foreground_rgb, background_rgb):
    """Calculate color contrast ratio for accessibility compliance"""
    
    def get_relative_luminance(rgb):
        """Calculate relative luminance of RGB color"""
        r, g, b = [c / 255.0 for c in rgb]
        
        def linearize(c):
            if c <= 0.03928:
                return c / 12.92
            else:
                return pow((c + 0.055) / 1.055, 2.4)
        
        r_lin = linearize(r)
        g_lin = linearize(g)
        b_lin = linearize(b)
        
        return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin
    
    l1 = get_relative_luminance(foreground_rgb)
    l2 = get_relative_luminance(background_rgb)
    
    # Ensure l1 is the lighter color
    if l1 < l2:
        l1, l2 = l2, l1
    
    contrast_ratio = (l1 + 0.05) / (l2 + 0.05)
    return contrast_ratio


def meets_wcag_contrast(foreground_rgb, background_rgb, level='AA', size='normal'):
    """Check if color combination meets WCAG contrast requirements"""
    
    ratio = check_color_contrast_ratio(foreground_rgb, background_rgb)
    
    # WCAG contrast requirements
    if level == 'AAA':
        if size == 'large':
            return ratio >= 4.5
        else:
            return ratio >= 7.0
    else:  # AA level
        if size == 'large':
            return ratio >= 3.0
        else:
            return ratio >= 4.5


def generate_accessible_color_scheme(base_color_rgb):
    """Generate accessible color variations from a base color"""
    
    r, g, b = [c / 255.0 for c in base_color_rgb]
    h, l, s = rgb_to_hls(r, g, b)
    
    # Generate variations with sufficient contrast
    schemes = {
        'primary': base_color_rgb,
        'light': tuple(int(c * 255) for c in hls_to_rgb(h, min(l + 0.3, 0.9), s)),
        'dark': tuple(int(c * 255) for c in hls_to_rgb(h, max(l - 0.3, 0.1), s)),
        'contrast_text': (255, 255, 255) if l < 0.5 else (0, 0, 0)
    }
    
    return schemes


def hls_to_rgb(h, l, s):
    """Convert HLS to RGB (helper function)"""
    from colorsys import hls_to_rgb as convert_hls_to_rgb
    return convert_hls_to_rgb(h, l, s)