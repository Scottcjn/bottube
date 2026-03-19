from flask import request, jsonify, g
import json
import re


def validate_category_parameter(category_param):
    """Validate and clean category URL parameters"""
    if not category_param:
        return None
    
    # Remove malformed JSON brackets
    cleaned = re.sub(r'[{}]', '', category_param)
    
    # Valid categories based on typical video platforms
    valid_categories = [
        'music', 'gaming', 'sports', 'tech', 'education', 
        'entertainment', 'news', 'comedy', 'how-to', 'travel'
    ]
    
    if cleaned.lower() in valid_categories:
        return cleaned.lower()
    
    return None


def inject_aria_labels(html_content):
    """Inject ARIA labels into icon-only buttons"""
    aria_mappings = {
        'fa-filter': 'Filter content',
        'fa-search': 'Search',
        'fa-menu': 'Open menu',
        'fa-heart': 'Like video',
        'fa-share': 'Share video',
        'fa-bookmark': 'Save video',
        'fa-play': 'Play video',
        'fa-pause': 'Pause video',
        'fa-volume': 'Volume control',
        'fa-fullscreen': 'Enter fullscreen',
        'fa-settings': 'Video settings'
    }
    
    for icon_class, aria_label in aria_mappings.items():
        # Add aria-label to buttons containing these icons
        pattern = f'<button([^>]*class="[^"]*{icon_class}[^"]*"[^>]*)>'
        replacement = f'<button\\1 aria-label="{aria_label}">'
        html_content = re.sub(pattern, replacement, html_content)
        
        # Handle anchor tags as well
        pattern = f'<a([^>]*class="[^"]*{icon_class}[^"]*"[^>]*)>'
        replacement = f'<a\\1 aria-label="{aria_label}">'
        html_content = re.sub(pattern, replacement, html_content)
    
    return html_content


def check_contrast_compliance(color_hex, bg_hex='#ffffff'):
    """Check if color combination meets WCAG AA contrast requirements"""
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    def luminance(rgb):
        r, g, b = [x/255.0 for x in rgb]
        rgb_vals = []
        for val in [r, g, b]:
            if val <= 0.03928:
                rgb_vals.append(val/12.92)
            else:
                rgb_vals.append(((val + 0.055)/1.055) ** 2.4)
        return 0.2126 * rgb_vals[0] + 0.7152 * rgb_vals[1] + 0.0722 * rgb_vals[2]
    
    fg_rgb = hex_to_rgb(color_hex)
    bg_rgb = hex_to_rgb(bg_hex)
    
    fg_lum = luminance(fg_rgb)
    bg_lum = luminance(bg_rgb)
    
    ratio = (max(fg_lum, bg_lum) + 0.05) / (min(fg_lum, bg_lum) + 0.05)
    
    return {
        'ratio': ratio,
        'aa_compliant': ratio >= 4.5,
        'aaa_compliant': ratio >= 7.0
    }


def get_high_contrast_alternative(color_hex, bg_hex='#ffffff'):
    """Suggest high contrast alternative color"""
    contrast_check = check_contrast_compliance(color_hex, bg_hex)
    
    if contrast_check['aa_compliant']:
        return color_hex
    
    # Return darker alternative for light backgrounds
    if bg_hex.lower() in ['#ffffff', '#fff', 'white']:
        return '#2c2c2c'  # Dark gray that meets AA standards
    else:
        return '#ffffff'  # White for dark backgrounds


def accessibility_middleware(response):
    """Middleware to apply accessibility fixes to HTML responses"""
    if response.content_type and 'text/html' in response.content_type:
        html_content = response.get_data(as_text=True)
        
        # Apply ARIA label injection
        html_content = inject_aria_labels(html_content)
        
        response.set_data(html_content)
    
    return response


def validate_accessibility_params():
    """Validate accessibility-related URL parameters"""
    category = request.args.get('category')
    if category:
        validated_category = validate_category_parameter(category)
        if not validated_category:
            return jsonify({
                'error': 'Invalid category parameter',
                'valid_categories': [
                    'music', 'gaming', 'sports', 'tech', 'education',
                    'entertainment', 'news', 'comedy', 'how-to', 'travel'
                ]
            }), 400
    
    return None


def get_accessibility_status():
    """Get current accessibility configuration"""
    return {
        'aria_labels_enabled': True,
        'contrast_checking_enabled': True,
        'category_validation_enabled': True,
        'wcag_level': 'AA'
    }