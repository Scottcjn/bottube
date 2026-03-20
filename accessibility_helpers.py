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


def add_keyboard_navigation(element_selector):
    """Add keyboard navigation support to elements"""
    return f"""
    document.addEventListener('DOMContentLoaded', function() {{
        const elements = document.querySelectorAll('{element_selector}');
        elements.forEach(function(element) {{
            element.setAttribute('tabindex', '0');
            element.addEventListener('keydown', function(e) {{
                if (e.key === 'Enter' || e.key === ' ') {{
                    e.preventDefault();
                    element.click();
                }}
            }});
        }});
    }});
    """


def validate_color_contrast(foreground, background):
    """Check if color combination meets WCAG contrast requirements"""
    # Simplified contrast check - in real implementation would use proper color parsing
    high_contrast_pairs = [
        ('#000000', '#ffffff'),
        ('#ffffff', '#000000'),
        ('#333333', '#ffffff'),
        ('#ffffff', '#333333')
    ]

    return (foreground.lower(), background.lower()) in high_contrast_pairs


def get_screen_reader_text(element_type, data=None):
    """Generate text specifically for screen readers"""
    templates = {
        'video_stats': 'Video has {views} views, {likes} likes, {comments} comments',
        'channel_info': 'Channel {name} has {subscribers} subscribers',
        'tip_status': 'Tip of {amount} RTC sent successfully',
        'comment_metadata': 'Comment by {author} posted {time_ago}',
        'video_progress': 'Video progress: {current_time} of {total_time}'
    }

    if element_type in templates and data:
        return templates[element_type].format(**data)

    return ""
