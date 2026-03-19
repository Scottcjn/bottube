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
    
    # Normalize to lowercase for matching
    category_lower = category_clean.lower()
    
    if category_lower in valid_categories:
        return valid_categories[category_lower]
    
    # If not a standard category, return sanitized version
    category_clean = re.sub(r'[^a-zA-Z0-9\s_-]', '', category_clean)
    category_clean = re.sub(r'\s+', '_', category_clean)
    
    return category_clean if len(category_clean) > 0 else None


def check_color_contrast(foreground, background):
    """Check if color contrast meets WCAG guidelines"""
    
    def hex_to_rgb(hex_color):
        """Convert hex color to RGB values"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    def get_luminance(rgb):
        """Calculate relative luminance of RGB color"""
        rgb_norm = [c/255.0 for c in rgb]
        rgb_linear = []
        
        for c in rgb_norm:
            if c <= 0.03928:
                rgb_linear.append(c / 12.92)
            else:
                rgb_linear.append(((c + 0.055) / 1.055) ** 2.4)
        
        return 0.2126 * rgb_linear[0] + 0.7152 * rgb_linear[1] + 0.0722 * rgb_linear[2]
    
    try:
        fg_rgb = hex_to_rgb(foreground)
        bg_rgb = hex_to_rgb(background)
        
        fg_lum = get_luminance(fg_rgb)
        bg_lum = get_luminance(bg_rgb)
        
        # Calculate contrast ratio
        lighter = max(fg_lum, bg_lum)
        darker = min(fg_lum, bg_lum)
        
        contrast_ratio = (lighter + 0.05) / (darker + 0.05)
        
        return {
            'ratio': contrast_ratio,
            'aa_normal': contrast_ratio >= 4.5,
            'aa_large': contrast_ratio >= 3.0,
            'aaa_normal': contrast_ratio >= 7.0,
            'aaa_large': contrast_ratio >= 4.5
        }
    
    except (ValueError, TypeError):
        return None


def validate_aria_attributes(element_dict):
    """Validate ARIA attributes for accessibility compliance"""
    
    validation_results = {
        'valid': True,
        'warnings': [],
        'errors': []
    }
    
    # Check for required ARIA attributes
    if element_dict.get('role') == 'button' and not element_dict.get('aria-label') and not element_dict.get('aria-labelledby'):
        validation_results['warnings'].append('Button should have aria-label or aria-labelledby')
    
    if element_dict.get('role') == 'link' and not element_dict.get('aria-label') and not element_dict.get('text_content'):
        validation_results['errors'].append('Link must have accessible name')
        validation_results['valid'] = False
    
    # Check for conflicting ARIA attributes
    if element_dict.get('aria-label') and element_dict.get('aria-labelledby'):
        validation_results['warnings'].append('Both aria-label and aria-labelledby present - aria-labelledby takes precedence')
    
    return validation_results