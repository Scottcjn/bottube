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
        'people': 'people'
    }
    
    # Normalize to lowercase and check against valid categories
    category_normalized = category_clean.lower().strip()
    
    if category_normalized in valid_categories:
        return valid_categories[category_normalized]
    
    # If not in predefined list, sanitize and return
    # Remove any non-alphanumeric characters except spaces and hyphens
    category_safe = re.sub(r'[^a-zA-Z0-9\s\-]', '', category_clean)
    category_safe = re.sub(r'\s+', ' ', category_safe).strip()
    
    if len(category_safe) > 0:
        return category_safe
    
    return None


def check_color_contrast(foreground_rgb, background_rgb):
    """Check if color combination meets WCAG contrast requirements"""
    
    def get_luminance(rgb):
        # Convert RGB values to relative luminance
        def normalize(c):
            c = c / 255.0
            if c <= 0.03928:
                return c / 12.92
            else:
                return pow((c + 0.055) / 1.055, 2.4)
        
        r, g, b = [normalize(c) for c in rgb]
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    
    l1 = get_luminance(foreground_rgb)
    l2 = get_luminance(background_rgb)
    
    # Ensure l1 is the lighter color
    if l1 < l2:
        l1, l2 = l2, l1
    
    contrast_ratio = (l1 + 0.05) / (l2 + 0.05)
    
    return {
        'ratio': contrast_ratio,
        'aa_normal': contrast_ratio >= 4.5,
        'aa_large': contrast_ratio >= 3.0,
        'aaa_normal': contrast_ratio >= 7.0,
        'aaa_large': contrast_ratio >= 4.5
    }


def validate_aria_attributes(element_dict):
    """Validate ARIA attributes for accessibility compliance"""
    
    valid_roles = {
        'button', 'link', 'tab', 'tabpanel', 'dialog', 'alert', 'status',
        'menu', 'menuitem', 'navigation', 'main', 'banner', 'contentinfo',
        'complementary', 'search', 'form', 'article', 'section', 'heading'
    }
    
    valid_properties = {
        'aria-label', 'aria-labelledby', 'aria-describedby', 'aria-hidden',
        'aria-expanded', 'aria-current', 'aria-selected', 'aria-checked',
        'aria-disabled', 'aria-required', 'aria-invalid', 'aria-live',
        'aria-atomic', 'aria-relevant', 'aria-busy', 'aria-controls',
        'aria-owns', 'aria-activedescendant', 'aria-haspopup', 'aria-level',
        'aria-posinset', 'aria-setsize'
    }
    
    issues = []
    
    # Check role validity
    if 'role' in element_dict:
        if element_dict['role'] not in valid_roles:
            issues.append(f"Invalid role: {element_dict['role']}")
    
    # Check ARIA properties
    for attr, value in element_dict.items():
        if attr.startswith('aria-'):
            if attr not in valid_properties:
                issues.append(f"Invalid ARIA attribute: {attr}")
            elif attr == 'aria-hidden' and value not in ['true', 'false']:
                issues.append(f"Invalid aria-hidden value: {value}")
            elif attr == 'aria-expanded' and value not in ['true', 'false']:
                issues.append(f"Invalid aria-expanded value: {value}")
    
    return {
        'valid': len(issues) == 0,
        'issues': issues
    }