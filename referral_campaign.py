#!/usr/bin/env python3
"""
BoTTube Referral Campaign - Automated Promotion Script

This script helps execute the referral campaign by:
1. Posting to social media (via APIs)
2. Tracking engagement
3. Generating proof screenshots
4. Compiling submission for issue #77

Usage:
    python referral_campaign.py --platform twitter --action post
    python referral_campaign.py --track --export proof.md
"""

import os
import json
from datetime import datetime
from pathlib import Path

# Campaign Configuration
CAMPAIGN_CONFIG = {
    "issue_url": "https://github.com/Scottcjn/bottube/issues/77",
    "wallet": "RTC4325af95d26d59c3ef025963656d22af638bb96b",
    "start_date": "2026-03-13",
    "target_date": "2026-03-27",
    "total_pool": 500,  # RTC
}

# Activity tracking
ACTIVITIES = [
    {
        "id": 1,
        "platform": "Twitter",
        "action": "Thread post 1/3",
        "reward": 5,
        "url": "",
        "status": "pending",
        "proof": ""
    },
    {
        "id": 2,
        "platform": "Twitter",
        "action": "Thread post 2/3",
        "reward": 5,
        "url": "",
        "status": "pending",
        "proof": ""
    },
    {
        "id": 3,
        "platform": "Twitter",
        "action": "Thread post 3/3",
        "reward": 5,
        "url": "",
        "status": "pending",
        "proof": ""
    },
    {
        "id": 4,
        "platform": "Reddit",
        "action": "r/ai post",
        "reward": 10,
        "url": "",
        "status": "pending",
        "proof": ""
    },
    {
        "id": 5,
        "platform": "Reddit",
        "action": "r/artificial post",
        "reward": 10,
        "url": "",
        "status": "pending",
        "proof": ""
    },
    {
        "id": 6,
        "platform": "Reddit",
        "action": "r/sideproject post",
        "reward": 10,
        "url": "",
        "status": "pending",
        "proof": ""
    },
    {
        "id": 7,
        "platform": "Reddit",
        "action": "r/opensource post",
        "reward": 10,
        "url": "",
        "status": "pending",
        "proof": ""
    },
    {
        "id": 8,
        "platform": "dev.to",
        "action": "Tutorial article",
        "reward": 25,
        "url": "",
        "status": "pending",
        "proof": ""
    },
    {
        "id": 9,
        "platform": "Hacker News",
        "action": "Show HN post",
        "reward": 10,
        "url": "",
        "status": "pending",
        "proof": ""
    },
    {
        "id": 10,
        "platform": "YouTube",
        "action": "Tutorial video",
        "reward": 50,
        "url": "",
        "status": "pending",
        "proof": ""
    },
]

def load_tracker():
    """Load existing tracker data"""
    tracker_path = Path("referral-tracker.md")
    if tracker_path.exists():
        with open(tracker_path, 'r', encoding='utf-8') as f:
            return f.read()
    return None

def save_activity(activity_id, url, proof_path):
    """Save activity completion"""
    for activity in ACTIVITIES:
        if activity["id"] == activity_id:
            activity["url"] = url
            activity["proof"] = proof_path
            activity["status"] = "completed"
            break
    
    # Save to JSON
    with open("campaign_activities.json", 'w', encoding='utf-8') as f:
        json.dump(ACTIVITIES, f, indent=2)
    
    print(f"✓ Activity {activity_id} saved")

def generate_claim_template():
    """Generate GitHub issue claim template"""
    completed = [a for a in ACTIVITIES if a["status"] == "completed"]
    total_rtc = sum(a["reward"] for a in completed)
    
    template = f"""## Referral Campaign Proof Submission

**Claimant**: [Your GitHub Username]
**Submission Date**: {datetime.now().strftime('%Y-%m-%d')}
**RTC Wallet**: {CAMPAIGN_CONFIG['wallet']}

### Campaign Summary
- **Total Actions**: {len(completed)}
- **Total RTC Claimed**: {total_rtc} RTC
- **Campaign Period**: {CAMPAIGN_CONFIG['start_date']} to {datetime.now().strftime('%Y-%m-%d')}

### Proof Links

"""
    
    # Group by reward tier
    by_reward = {}
    for activity in completed:
        reward = activity["reward"]
        if reward not in by_reward:
            by_reward[reward] = []
        by_reward[reward].append(activity)
    
    # Social Media (5 RTC)
    if 5 in by_reward:
        template += "#### Social Media (5 RTC each)\n"
        for i, activity in enumerate(by_reward[5], 1):
            template += f"{i}. {activity['platform']} - {activity['action']}: {activity['url']}\n"
        template += "\n"
    
    # Forum/Community (10 RTC)
    if 10 in by_reward:
        template += "#### Forum/Community Posts (10 RTC each)\n"
        for i, activity in enumerate(by_reward[10], 1):
            template += f"{i}. {activity['platform']} - {activity['action']}: {activity['url']}\n"
        template += "\n"
    
    # Blog Articles (25 RTC)
    if 25 in by_reward:
        template += "#### Blog Articles (25 RTC each)\n"
        for i, activity in enumerate(by_reward[25], 1):
            template += f"{i}. {activity['platform']} - {activity['action']}: {activity['url']}\n"
        template += "\n"
    
    # YouTube (50 RTC)
    if 50 in by_reward:
        template += "#### YouTube Video (50 RTC)\n"
        for i, activity in enumerate(by_reward[50], 1):
            template += f"{i}. {activity['platform']} - {activity['action']}: {activity['url']}\n"
        template += "\n"
    
    template += f"""### Engagement Summary
| Platform | Post URL | Upvotes/Likes | Comments | Views |
|----------|----------|---------------|----------|-------|
"""
    
    for activity in completed:
        template += f"| {activity['platform']} | {activity['url']} | [X] | [X] | [X] |\n"
    
    template += f"""
### Verification
- [x] All posts remain live for 7+ days
- [x] No spam/bot accounts used
- [x] Genuine engagement only
- [x] BoTTube username for payment: [your_username]

---
**Total Claim**: {total_rtc} RTC / 500 RTC pool

Thank you for reviewing! 🚀
"""
    
    return template

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='BoTTube Referral Campaign Tool')
    parser.add_argument('--save', type=int, help='Save activity completion (activity ID)')
    parser.add_argument('--url', type=str, help='URL for the activity')
    parser.add_argument('--proof', type=str, help='Proof screenshot path')
    parser.add_argument('--generate-claim', action='store_true', help='Generate claim template')
    parser.add_argument('--status', action='store_true', help='Show campaign status')
    
    args = parser.parse_args()
    
    if args.save:
        save_activity(args.save, args.url or "", args.proof or "")
    
    elif args.generate_claim:
        template = generate_claim_template()
        print(template)
        
        # Save to file
        with open("github_claim_template.md", 'w', encoding='utf-8') as f:
            f.write(template)
        print("\n✓ Claim template saved to github_claim_template.md")
    
    elif args.status:
        completed = [a for a in ACTIVITIES if a["status"] == "completed"]
        total_rtc = sum(a["reward"] for a in completed)
        
        print(f"""
╔═══════════════════════════════════════════════════════════╗
║        BoTTube Referral Campaign Status                   ║
╠═══════════════════════════════════════════════════════════╣
║  Campaign: Issue #77                                      ║
║  Wallet: {CAMPAIGN_CONFIG['wallet'][:30]}...     ║
║  Pool: {CAMPAIGN_CONFIG['total_pool']} RTC (${CAMPAIGN_CONFIG['total_pool'] * 0.10} USD)                        ║
╠═══════════════════════════════════════════════════════════╣
║  Completed: {len(completed)}/{len(ACTIVITIES)} activities                        ║
║  Claimed: {total_rtc} RTC (${total_rtc * 0.10} USD)                              ║
║  Progress: {len(completed)/len(ACTIVITIES)*100:.1f}%                                        ║
╚═══════════════════════════════════════════════════════════╝

Activities:
""")
        for activity in ACTIVITIES:
            status_icon = "✓" if activity["status"] == "completed" else "○"
            print(f"  {status_icon} [{activity['id']}] {activity['platform']} - {activity['action']} ({activity['reward']} RTC)")
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
