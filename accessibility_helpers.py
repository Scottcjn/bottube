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


def generate_status_announcement(message_type, details=None):
    """Generate screen reader announcements for status changes"""
    announcements = {
        'subscribed': f"Successfully subscribed to {details}" if details else "Successfully subscribed",
        'unsubscribed': f"Unsubscribed from {details}" if details else "Successfully unsubscribed",
        'tip_sent': f"Tip of {details} RTC sent successfully" if details else "Tip sent successfully",
        'comment_posted': "Comment posted successfully",
        'upvoted': "Comment upvoted",
        'downvoted': "Comment downvoted",
        'error': f"Error: {details}" if details else "An error occurred",
        'loading': f"Loading {details}" if details else "Loading content"
    }

    return announcements.get(message_type, message_type)


def get_keyboard_shortcuts():
    """Return keyboard shortcuts for video player accessibility"""
    return {
        'spacebar': 'Play/Pause video',
        'k': 'Play/Pause video',
        'f': 'Toggle fullscreen',
        'escape': 'Exit fullscreen',
        'm': 'Mute/Unmute',
        'up_arrow': 'Increase volume',
        'down_arrow': 'Decrease volume',
        'left_arrow': 'Seek backward 10 seconds',
        'right_arrow': 'Seek forward 10 seconds',
        'j': 'Seek backward 10 seconds',
        'l': 'Seek forward 10 seconds',
        'comma': 'Previous frame (when paused)',
        'period': 'Next frame (when paused)',
        'home': 'Go to beginning',
        'end': 'Go to end'
    }
