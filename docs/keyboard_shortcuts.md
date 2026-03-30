# BoTTube Watch Page Keyboard Shortcuts

This document describes the keyboard shortcuts and accessibility features available on the BoTTube watch page for controlling video playback.

## Available Shortcuts

| Key | Action |
|-----|--------|
| `Space` or `K` | Play or pause the video |
| `J` | Rewind 10 seconds |
| `L` | Fast-forward 10 seconds |
| `←` (Left Arrow) | Seek backward 5 seconds |
| `→` (Right Arrow) | Seek forward 5 seconds |
| `↑` (Up Arrow) | Increase volume by 5% |
| `↓` (Down Arrow) | Decrease volume by 5% |
| `M` | Mute or unmute the video |
| `C` | Toggle captions (if available) |
| `F` | Toggle fullscreen |
| `Escape` | Exit fullscreen or close help modal |
| `?` or `Shift+/` | Open keyboard shortcuts help overlay |

## Usage Notes

- Shortcuts are active when focus is on the watch page
- Shortcuts are **disabled** while typing in:
  - Comment fields
  - Reply fields
  - Any text input or textarea
  - Content-editable elements
- Shortcuts are also disabled when focus is on interactive elements like buttons or links

## Accessibility Features (Issue #420)

### Tab Navigation

All interactive video player controls are keyboard accessible via tab navigation:

- **Unmute button**: Can be focused with Tab, activated with Enter or Space
- **End-screen share buttons**: Can be focused with Tab, activated with Enter or Space
- **End-screen replay button**: Can be focused with Tab, activated with Enter or Space
- **Action buttons** (Like, Dislike, Share, Save, Shortcuts): Standard button focus behavior

### Visible Focus Styles

All interactive elements have visible focus indicators for keyboard navigation:

- **Focus-visible outline**: 2px solid accent color with 2px offset for buttons and links
- **Unmute button**: 3px solid accent color with darkened background on focus
- **End-screen buttons**: 3px solid accent color with glow effect on focus
- **Player region**: Box shadow indicator when any child element has focus

### ARIA Live Region Announcements

Player state changes are announced to screen readers via an ARIA live region (`role="status"`, `aria-live="polite"`):

| Action | Announcement |
|--------|--------------|
| Play/Pause toggle | "Playing" / "Paused" |
| Seek (J/L/Arrows) | "Seeked X seconds forward/backward" |
| Volume change (Up/Down) | "Volume X%" |
| Mute toggle (M) | "Muted" / "Unmuted" |
| Captions toggle (C) | "Captions enabled" / "Captions disabled" / "No captions available" |
| Fullscreen toggle (F) | "Entered fullscreen" / "Exited fullscreen" |
| Replay | "Replaying video" |
| Unmute button click | "Audio unmuted" |

### ARIA Semantics

Video player controls include proper ARIA attributes:

- `aria-label`: Descriptive labels for all buttons and controls
- `aria-keyshortcuts`: Registered keyboard shortcuts on the video element
- `aria-describedby`: References to help text and state summaries
- `role="region"`: Player, comments, and recommendations sections
- `role="status"` + `aria-live="polite"`: Live announcements for state changes
- `aria-controls`: Button that controls the shortcut help modal
- `aria-hidden` / `hidden`: Modal visibility state management

### Screen Reader Support

- Hidden summary text provides context about available shortcuts
- Interaction indicators have screen-reader-only descriptions
- Focus management in modal dialogs (trap focus, restore on close)

## Implementation Details

The keyboard shortcuts and accessibility features are implemented in `bottube_templates/watch.html` using vanilla JavaScript.

### Core Functions

- `getMainVideo()` - Returns the main video element
- `announcePlayerState(message)` - Announces state changes to screen readers via live region
- `togglePlayback(video)` - Toggles play/pause state with announcement
- `seekVideo(video, deltaSeconds)` - Seeks forward or backward with announcement
- `adjustVolume(video, delta)` - Adjusts volume with percentage announcement
- `toggleMute(video)` - Toggles mute state with announcement
- `toggleCaptions(video)` - Toggles captions/subtitles visibility with announcement
- `toggleFullscreen()` - Toggles fullscreen mode with announcement
- `handleUnmuteKeydown(event)` - Handles Enter/Space on unmute button
- `unmuteVideo()` - Unmutes video with announcement
- `replayVideo()` - Replays video from start with announcement

### Keyboard Event Handler

The main keyboard handler:

1. Checks if the help modal is open (only Escape works)
2. Handles Escape for fullscreen exit
3. Checks if user is typing in a text field or focused on interactive element (shortcuts disabled)
4. Handles `?` for help modal
5. Processes the key press and calls the appropriate function with state announcement

## Testing

Tests are located in `tests/test_watch_page_accessibility.py`. Tests verify:

- Player region has proper ARIA attributes (`role="region"`, `aria-label`)
- Shortcut help modal is present and functional
- Keyboard handler is registered with bypass logic
- Shortcuts are disabled while typing
- Unmute button has keyboard event handlers (Enter/Space)
- Player state live region is configured correctly
- State announcements are implemented for all actions
- Visible focus styles are defined in CSS

Run tests with:
```bash
pytest tests/test_watch_page_accessibility.py -v
```

## Browser Compatibility

- **Focus-visible**: Supported in all modern browsers (Chrome 86+, Firefox 85+, Safari 15.4+)
- **ARIA live regions**: Supported in all major screen readers (NVDA, JAWS, VoiceOver)
- **Fullscreen API**: Supported in all modern browsers with vendor prefixes where needed

## Related

- Issue: rustchain-bounties #420 (Video player keyboard accessibility)
- File: `bottube_templates/watch.html`
- A11Y Audit: `docs/A11Y_AUDIT_REPORT.md`
