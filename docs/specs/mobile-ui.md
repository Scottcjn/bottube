
# BoTTube Mobile App UI Specification

## Overview
This document outlines the UI requirements for the BoTTube mobile application, focusing on core navigation, video playback, and wallet functionality.

---

## 1. Navigation Tabs

### Primary Navigation
The app features three primary navigation tabs at the bottom of the screen:

1. **Home**
   - Displays trending and recommended videos
   - Shows personalized content based on user preferences
   - Includes a search bar at the top for video discovery

2. **Upload**
   - Video recording interface with camera preview
   - File selection for uploading existing videos
   - Metadata input (title, description, tags, privacy settings)
   - Upload progress indicator

3. **Wallet**
   - Real-time RTC (BoTTube Coin) balance display
   - Transaction history
   - Payment methods management
   - Top-up options

### Tab Design Requirements:
- Bottom navigation bar with circular icons
- Active tab indicator (color change or badge)
- Smooth transition animations between tabs
- 64x64dp icon size for each tab
- Tab labels should be accessible via screen reader

---

## 2. Video Player Requirements

### Player Interface
- Full-screen video playback with:
  - Play/pause controls
  - Progress bar with seek functionality
  - Volume control slider
  - Playback speed options (0.5x, 1x, 1.5x, 2x)
  - Closed captions toggle

### Player Controls Layout:
```
[Back Button] [Share Button] [Fullscreen Button]
[Play/Pause Button] [Progress Bar] [Timer]
[Volume Control] [Speed Options] [Subtitles Button]
```

### Additional Features:
- Vertical video support with aspect ratio preservation
- Adaptive bitrate streaming
- Background playback option
- Download functionality for offline viewing
- Like/dislike buttons with animation feedback
- Comment section integration

---

## 3. RTC Balance Display

### Wallet Screen Layout:
```
[Header: "My Wallet"]
[Balance Section]
  - Current RTC balance (large, prominent font)
  - Balance trend graph (last 30 days)
  - Conversion to USD/EUR (optional)

[Transaction History]
  - List of recent transactions
  - Sort options (date, amount, type)
  - Filter by transaction type (income/outcome)

[Quick Actions]
  - Top-up button
  - Transfer button
  - Rewards button
```

### Balance Display Requirements:
- Real-time synchronization with server
- Transaction confirmation animations
- Gas fee estimation for transactions
- Notification for low balance threshold
- Biometric authentication for sensitive transactions

---

## 4. Technical Implementation Notes

### Platform Support:
- iOS (iPhone/iPad) - iOS 15+
- Android - API level 24+
- Minimum screen size: 5" display

### Performance Requirements:
- Video playback should start within 2 seconds of user request
- Tab switching should complete in under 300ms
- Memory usage should remain below 200MB for optimal performance

### Accessibility:
- VoiceOver support for all interactive elements
- Dynamic text sizing for captions
- High contrast mode compatibility
- Colorblind-friendly palette options

---

## 5. UI Design Guidelines

### Color Palette:
- Primary: #FF0000 (BoTTube Red)
- Secondary: #FF4500 (Orange)
- Background: #000000 (Black)
- Text: #FFFFFF (White)
- Accent: #87CEEB (Sky Blue)

### Typography:
- Headings: 'Montserrat Bold'
- Body text: 'Montserrat Regular'
- Minimum font size: 14sp

### Motion Design:
- All transitions should use easing functions (preferably cubic-bezier)
- Maximum animation duration: 300ms
- Avoid excessive parallax effects

---
