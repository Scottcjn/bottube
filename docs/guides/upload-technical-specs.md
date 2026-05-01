
# Video Upload Technical Specifications for Scottcjn/bottube

## Overview
This document outlines the technical constraints and requirements for video uploads to the [Scottcjn/bottube] platform.

## Upload Constraints

### 1. Maximum File Size
- **Limit:** 500MB per video file
- **Note:** Files exceeding this limit will be rejected during upload

### 2. Supported Video Formats
The platform accepts the following video formats:
- **MP4** (MPEG-4 Part 14)
- **WebM** (WebM container with VP8 or VP9 codecs)

### 3. Required Bitrate Settings for PPA Verification
For proper playback and PPA (Platform Playback Authorization) verification, videos must meet the following bitrate requirements:

| Video Resolution | Minimum Bitrate | Recommended Bitrate |
|------------------|-----------------|---------------------|
| 240p             | 500 kbps        | 800 kbps            |
| 360p             | 1 Mbps          | 1.5 Mbps            |
| 480p             | 1.5 Mbps        | 2 Mbps              |
| 720p             | 2 Mbps          | 3 Mbps              |
| 1080p            | 3 Mbps          | 4.5 Mbps            |
| 1440p            | 5 Mbps          | 6 Mbps              |
| 4K (2160p)       | 8 Mbps          | 10 Mbps             |

### 4. Additional Requirements
- **Aspect Ratio:** Must be between 16:9 and 2.39:1 (letterboxing allowed)
- **Frame Rate:** 24-60 fps (30 fps recommended)
- **Audio Codec:** AAC or Opus (stereo or mono)
- **Container:** Must be compatible with the specified formats

## Technical Notes
- Videos should be encoded with H.264 (AVC) or VP9 codec for optimal compatibility
- For WebM files, ensure proper VP8/VP9 configuration with appropriate bitrate settings
- All videos must pass platform validation before being processed for PPA verification

## Compliance
All uploaded videos must comply with these specifications to ensure proper playback, processing, and PPA verification on the platform.

---
**Completed upload specs for [Scottcjn/bottube]**
