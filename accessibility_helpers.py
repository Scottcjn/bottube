# SPDX-License-Identifier: MIT

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


def get_skip_link_html():
    """Generate skip navigation link HTML"""
    return '<a href="#main-content" class="skip-link">Skip to main content</a>'


def add_form_accessibility_attrs(field_type, field_name, placeholder_text=None):
    """Generate accessibility attributes for form fields"""
    attrs = {
        'aria-label': get_accessible_form_label(field_name, placeholder_text),
        'id': f"field_{field_name}"
    }

    if field_type in ['email', 'password', 'search']:
        attrs['aria-describedby'] = f"{field_name}_help"

    return attrs
