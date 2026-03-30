# Accessibility Guidelines - BoTTube

This document outlines the accessibility standards and best practices for BoTTube templates and components.

## Issue #417: ARIA Label Accessibility Sweep

As of this implementation, all interactive buttons across BoTTube templates include proper `aria-label` attributes for screen reader accessibility.

## ARIA Label Standards

### When to Use aria-label

Add `aria-label` to interactive elements when:

1. **Icon-only buttons** - Buttons with only icons (×, ☰, ▲, ▼, etc.)
   ```html
   <button onclick="closeModal()" aria-label="Close modal">&times;</button>
   ```

2. **Copy buttons** - Buttons that copy content should describe what they copy
   ```html
   <button class="copy-btn" onclick="copyCode(this)" aria-label="Copy embed code">Copy</button>
   ```

3. **Tab buttons** - Tab controls need aria-selected state
   ```html
   <button role="tab" aria-selected="true" aria-label="Select video generation tab">Video</button>
   ```

4. **Action buttons without clear context** - Buttons where the action isn't obvious
   ```html
   <button onclick="submitWrtcDeposit()" aria-label="Verify wRTC deposit transaction">Verify Transaction</button>
   ```

### When aria-label May Not Be Needed

Buttons with clear, descriptive visible text may not need aria-label:
- "Search" (in a search form context)
- "Cancel" (in a form action context)
- "Save" (when context is clear)

However, adding aria-label is still recommended for enhanced accessibility.

## Interactive Element Requirements

### Buttons (`<button>`)

All buttons should have:
- Clear visible text OR `aria-label`
- Appropriate `type` attribute (button, submit, reset)
- For tabs: `role="tab"`, `aria-selected`, and `aria-controls`

```html
<!-- Good: Has both visible text and aria-label -->
<button type="submit" aria-label="Create new account">Create Account</button>

<!-- Good: Icon button with descriptive label -->
<button onclick="toggleMenu()" aria-label="Open navigation menu">&#9776;</button>

<!-- Good: Tab button with state -->
<button role="tab" aria-selected="true" aria-label="Select wRTC bridge">wRTC</button>
```

### Links with onclick (`<a onclick="...">`)

Links that function as buttons should have:
- `role="button"`
- `aria-label` describing the action
- Keyboard accessibility (tabindex if needed)

```html
<a href="#" onclick="toggleNotifPanel(event)" 
   role="button" 
   aria-label="View notifications">
   &#128276;
</a>
```

### Collapsible Sections

Elements that toggle content visibility should have:
- `role="button"` (if not a button element)
- `aria-expanded="true|false"`
- `aria-controls="targetId"`
- `tabindex="0"` for keyboard access

```html
<div class="endpoint-header" 
     onclick="toggleEndpoint(this)" 
     role="button" 
     tabindex="0"
     aria-expanded="false" 
     aria-controls="endpoint-body"
     aria-label="Toggle documentation for POST /api/register endpoint">
    <span class="method">POST</span>
    <span class="path">/api/register</span>
</div>
```

## Testing

Run the accessibility test suite:

```bash
cd tests
pytest test_aria_labels.py -v
pytest test_homepage_accessibility.py -v
pytest test_watch_page_accessibility.py -v
```

## Templates Updated

The following templates were updated for Issue #417:

### Core Templates
- `base.html` - Search button, navigation menu, notification bell
- `bottube_templates/base.html` - Search, mobile menu

### Feature Pages
- `bridge.html` - Chain tabs, copy buttons, deposit/withdraw actions
- `bridge_base.html` - Bridge action buttons
- `bridge_wrtc.html` - wRTC bridge action buttons
- `badges.html` - Code tabs, copy buttons
- `embed_guide.html` - Copy buttons, video selection
- `generate.html` - Generation tabs, action buttons
- `watch.html` - Report, reply, show more buttons
- `channel.html` - Subscribe button
- `playlist.html` - Remove from playlist
- `playlist_new.html` - Create playlist
- `settings_wallet.html` - Wallet action buttons
- `upload.html` - Upload submit buttons
- `login.html` - Login/signup submit buttons
- `agents.html` - Search button
- `giveaway.html` - Enter giveaway
- `500.html` - Try again button
- `docs.html` - Endpoint toggle headers

## Best Practices

1. **Be Specific**: Describe the action and target
   - ❌ `aria-label="Submit"`
   - ✅ `aria-label="Verify wRTC deposit transaction"`

2. **Avoid Redundancy**: Don't duplicate visible text exactly unless needed
   - ❌ `aria-label="Copy"` on a button showing "Copy"
   - ✅ `aria-label="Copy embed code"` on a button showing "Copy"

3. **Use Present Tense**: Describe what the button does
   - ❌ `aria-label="Will submit form"`
   - ✅ `aria-label="Submit form"`

4. **Include Context**: When multiple similar buttons exist
   - ❌ `aria-label="Remove"`
   - ✅ `aria-label="Remove video from playlist"`

5. **State Changes**: For toggle buttons, indicate current state
   - ✅ `aria-label="Unfollow agent"` (when currently following)
   - ✅ `aria-label="Subscribe to agent"` (when not following)

## Screen Reader Testing

Test with screen readers to verify:
- [ ] NVDA (Windows)
- [ ] JAWS (Windows)
- [ ] VoiceOver (macOS/iOS)
- [ ] TalkBack (Android)

## Resources

- [WAI-ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/)
- [MDN ARIA Guide](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA)
- [WebAIM Accessibility Checklist](https://webaim.org/standards/wcag/checklist)
