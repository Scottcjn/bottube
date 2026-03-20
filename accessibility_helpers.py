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

    return ", ".join(alt_parts) if alt_parts else "Video thumbnail"


def get_keyboard_navigation_hint(element_type):
    """Get keyboard navigation hints for screen readers"""
    hints = {
        'video_player': "Use space to play/pause, arrow keys to seek",
        'comment_section': "Use tab to navigate comments, enter to reply",
        'search_results': "Use arrow keys to navigate, enter to select",
        'navigation_menu': "Use arrow keys to navigate menu items",
        'video_grid': "Use arrow keys to browse videos, enter to play"
    }

    return hints.get(element_type, "Use tab to navigate, enter to activate")


def create_skip_link(target_id, text="Skip to main content"):
    """Create skip navigation link for keyboard users"""
    return f'<a class="skip-link" href="#{target_id}">{text}</a>'


def get_aria_live_region_text(action, context=None):
    """Generate text for aria-live regions to announce dynamic changes"""
    announcements = {
        'video_loaded': f"Video {context} loaded" if context else "Video loaded",
        'comment_posted': "Comment posted successfully",
        'tip_sent': f"Tip sent to {context}" if context else "Tip sent",
        'subscribed': f"Subscribed to {context}" if context else "Subscription updated",
        'error': f"Error: {context}" if context else "An error occurred",
        'loading': "Loading content",
        'search_results': f"{context} results found" if context else "Search completed"
    }

    return announcements.get(action, f"{action} completed")
