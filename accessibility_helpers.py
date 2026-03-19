def generate_aria_label(element_type, context=None, action=None):
    """Generate appropriate aria-label for UI elements"""
    labels = {
        'subscribe_button': f"Subscribe to {context}" if context else "Subscribe to channel",
        'tip_button': f"Tip {context}" if context else "Send tip",
        'upvote_button': f"Upvote comment by {context}" if context else "Upvote comment",
        'downvote_button': f"Downvote comment by {context}" if context else "Downvote comment",
        'play_button': f"Play {context}" if context else "Play video",
        'pause_button': f"Pause {context}" if context else "Pause video",
        'settings_button': "Open video settings",
        'fullscreen_button': "Enter fullscreen mode",
        'volume_button': "Adjust volume",
        'share_button': f"Share {context}" if context else "Share video"
    }
    
    if element_type in labels:
        return labels[element_type]
    
    if action and context:
        return f"{action} {context}"
    
    return element_type.replace('_', ' ').title()

def get_accessible_form_label(field_name, placeholder_text=None):
    """Generate accessible labels for form inputs"""
    label_map = {
        'comment_text': 'Comment text',
        'tip_amount': 'Tip amount in RTC',
        'search_query': 'Search videos',
        'username': 'Username',
        'password': 'Password',
        'email': 'Email address',
        'video_title': 'Video title',
        'video_description': 'Video description',
        'tags': 'Video tags'
    }
    
    if field_name in label_map:
        return label_map[field_name]
    
    if placeholder_text:
        return placeholder_text
        
    return field_name.replace('_', ' ').title()

def generate_video_thumbnail_alt(video_title, channel_name=None, duration=None):
    """Generate descriptive alt text for video thumbnails"""
    alt_parts = []
    
    if video_title:
        alt_parts.append(f"Video: {video_title}")
    
    if channel_name:
        alt_parts.append(f"by {channel_name}")
        
    if duration:
        alt_parts.append(f"Duration: {duration}")
    
    if not alt_parts:
        return "Video thumbnail"
        
    return " ".join(alt_parts)

def check_contrast_ratio(foreground_color, background_color):
    """Basic contrast ratio validation for color combinations"""
    contrast_pairs = {
        '#666666': {'#ffffff': True, '#f5f5f5': True, '#000000': False},
        '#888888': {'#ffffff': True, '#f5f5f5': False, '#000000': False},
        '#999999': {'#ffffff': False, '#f5f5f5': False, '#000000': False},
        '#333333': {'#ffffff': True, '#f5f5f5': True, '#000000': False}
    }
    
    if foreground_color in contrast_pairs:
        return contrast_pairs[foreground_color].get(background_color, False)
    
    return True

def get_semantic_heading_level(page_section):
    """Return appropriate heading level for page sections"""
    heading_levels = {
        'page_title': 'h1',
        'video_title': 'h2', 
        'sidebar_section': 'h3',
        'comment_section': 'h3',
        'related_videos': 'h3',
        'channel_info': 'h4',
        'comment_reply': 'h5'
    }
    
    return heading_levels.get(page_section, 'h3')

def create_skip_link(target_id, link_text="Skip to main content"):
    """Generate skip navigation link for accessibility"""
    return f'<a href="#{target_id}" class="skip-link">{link_text}</a>'

def get_button_role_attributes(button_type):
    """Return appropriate ARIA attributes for button types"""
    button_attrs = {
        'toggle': 'role="button" aria-pressed="false"',
        'menu': 'role="button" aria-haspopup="true" aria-expanded="false"',
        'tab': 'role="tab" aria-selected="false"',
        'submit': 'type="submit"',
        'reset': 'type="reset"'
    }
    
    return button_attrs.get(button_type, 'role="button"')

def format_screen_reader_text(text, hide_visually=True):
    """Format text for screen readers with optional visual hiding"""
    css_class = 'sr-only' if hide_visually else 'sr-text'
    return f'<span class="{css_class}">{text}</span>'

def get_live_region_attributes(politeness='polite'):
    """Generate ARIA live region attributes for dynamic content"""
    return f'aria-live="{politeness}" aria-atomic="true"'