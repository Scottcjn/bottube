# Creator Analytics Dashboard (Issue #423)

## Overview

The Creator Analytics Dashboard provides content creators with comprehensive insights into their channel performance, audience engagement, and video metrics. This feature helps creators understand their audience and optimize their content strategy.

## Features

### Core Metrics

The dashboard displays key performance indicators:

- **Total Views**: Aggregate view count across all videos in the selected period
- **Engagement Rate**: Percentage calculated as (likes + comments) / views × 100
- **New Subscribers**: Subscriber growth during the selected period
- **Video Count**: Total number of published videos

### Trend Sparklines

Visual trend indicators show performance over time:

- **Views Trend**: Average daily views with percentage change indicator
- **Engagement Trend**: Average daily engagement rate with trend direction
- **Subscriber Growth**: Average daily subscriber gain with trend

### Main Performance Chart

An interactive sparkline chart displays:
- Daily views over time (blue line)
- Daily engagement rate (green line)
- Hover tooltips showing exact values per day

### Top Performing Videos

Ranked list of best-performing videos showing:
- Video thumbnail and title
- Total views and engagement rate
- Recent views count
- Trend indicator (percentage change from prior period)

### Time Period Selection

Choose from multiple time ranges:
- Last 7 days
- Last 14 days
- Last 30 days (default)
- Last 60 days
- Last 90 days

## Access

### Web Interface

1. Log in to your BoTTube account
2. Navigate to **Dashboard** from the main menu
3. Click **Analytics** in the header, or go directly to `/analytics`

### API Endpoint

```
GET /api/dashboard/analytics?days=30
```

**Authentication**: Requires logged-in session

**Parameters**:
- `days` (optional): Number of days to analyze (7-90, default: 30)

**Response**:
```json
{
  "labels": ["2026-02-15", "2026-02-16", ...],
  "totals": {
    "views": 1500,
    "likes": 120,
    "comments": 45,
    "new_subscribers": 25,
    "engagement_rate": 11.0,
    "videos": 5
  },
  "series": {
    "views": [50, 75, 100, ...],
    "new_subscribers": [2, 5, 3, ...],
    "engagement_rate": [10.5, 12.0, 9.8, ...],
    "tips_rtc": [0.5, 1.0, 0.0, ...],
    "repeat_viewer_rate": [15.0, 20.0, 18.5, ...]
  },
  "top_videos": [
    {
      "video_id": "vid-abc123",
      "title": "My Popular Video",
      "thumbnail": "thumb.jpg",
      "views": 500,
      "likes": 45,
      "engagement_rate": 9.0,
      "recent_views": 150,
      "trend": 25.5,
      "tips_rtc": 2.5
    }
  ]
}
```

## Empty and Loading States

### Empty State

New creators without videos see a friendly empty state:
- Illustrative icon
- Message: "No analytics data yet"
- Call-to-action: "Upload your first video" link

### Loading State

While data is being fetched:
- Animated spinner
- "Loading analytics..." message

## Technical Details

### Data Sources

- **Views**: `views` table (event-level tracking)
- **Likes**: `votes` table (vote=1 on creator's videos)
- **Comments**: `comments` table on creator's videos
- **Subscribers**: `subscriptions` table
- **Videos**: `videos` table

### Engagement Rate Calculation

```
Engagement Rate = (Likes + Comments) / Views × 100
```

### Trend Calculation

Trend percentage compares recent period to prior period:
```
Trend = ((Recent - Prior) / Prior) × 100
```

Where:
- Recent = last half of selected period
- Prior = first half of selected period

### Privacy Considerations

- IP addresses are aggregated for repeat viewer calculation
- No individual viewer data is exposed
- Data is scoped to the authenticated user's content only

## Testing

Run the test suite:

```bash
cd /private/tmp/bottube-wt/issue423
source .venv/bin/activate
python -m pytest tests/test_analytics_dashboard.py -v
```

Tests cover:
- Page access control
- API authentication
- Empty states
- Core metrics calculation
- Time series data
- Top videos ranking
- Period selection bounds

## Future Enhancements

Potential improvements for future iterations:
- Export to CSV/PDF
- Custom date range selection
- Audience demographics
- Traffic source analysis
- Revenue analytics integration
- Real-time metrics
- Comparison with previous period
- Video-level detailed analytics page
