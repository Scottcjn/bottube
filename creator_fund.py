from sqlite3 import Row
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from bottube_server import get_db
import logging

logger = logging.getLogger(__name__)


class CreatorFund:
    def __init__(self):
        self.monthly_cap = 75  # RTC per creator per month
        self.pilot_pools = {
            1: 150,  # Month 1
            2: 150,  # Month 2
            3: 200   # Month 3
        }

    def initialize_tables(self) -> None:
        """Initialize creator fund related database tables"""
        db = get_db()

        # Creator fund distributions table
        db.execute('''
            CREATE TABLE IF NOT EXISTS creator_fund_distributions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                month INTEGER NOT NULL,
                year INTEGER NOT NULL,
                amount REAL NOT NULL,
                total_views INTEGER NOT NULL,
                eligible_views INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id, month, year)
            )
        ''')

        # Creator fund eligibility cache
        db.execute('''
            CREATE TABLE IF NOT EXISTS creator_fund_eligibility (
                user_id INTEGER PRIMARY KEY,
                is_eligible BOOLEAN NOT NULL,
                subscriber_count INTEGER NOT NULL,
                video_count INTEGER NOT NULL,
                last_activity DATE NOT NULL,
                last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        db.commit()

    def check_eligibility(self, user_id: int) -> Tuple[bool, Dict[str, any]]:
        """Check if creator meets fund eligibility requirements"""
        db = get_db()

        # Get user stats
        user_stats = db.execute('''
            SELECT u.id, u.username,
                   COUNT(DISTINCT s.follower_id) as subscriber_count,
                   COUNT(DISTINCT v.id) as video_count,
                   MAX(v.uploaded_at) as last_upload
            FROM users u
            LEFT JOIN subscriptions s ON u.id = s.user_id
            LEFT JOIN videos v ON u.id = v.user_id
            WHERE u.id = ?
            GROUP BY u.id, u.username
        ''', (user_id,)).fetchone()

        if not user_stats:
            return False, {'reason': 'User not found'}

        # Eligibility criteria
        min_subscribers = 100
        min_videos = 5
        max_days_inactive = 30

        subscriber_count = user_stats['subscriber_count'] or 0
        video_count = user_stats['video_count'] or 0
        last_upload = user_stats['last_upload']

        # Check activity
        if last_upload:
            last_upload_date = datetime.strptime(last_upload, '%Y-%m-%d %H:%M:%S')
            days_inactive = (datetime.now() - last_upload_date).days
        else:
            days_inactive = float('inf')

        eligibility_details = {
            'subscriber_count': subscriber_count,
            'video_count': video_count,
            'days_inactive': days_inactive,
            'requirements': {
                'min_subscribers': min_subscribers,
                'min_videos': min_videos,
                'max_days_inactive': max_days_inactive
            }
        }

        is_eligible = (
            subscriber_count >= min_subscribers and
            video_count >= min_videos and
            days_inactive <= max_days_inactive
        )

        return is_eligible, eligibility_details

    def calculate_monthly_distribution(self, month: int, year: int) -> List[Dict]:
        """Calculate RTC distribution for eligible creators"""
        db = get_db()
        month_key = ((year - 2024) * 12) + month
        monthly_pool = self.pilot_pools.get(month_key, 200)

        # Get eligible creators with view counts
        eligible_creators = db.execute('''
            SELECT u.id, u.username,
                   COALESCE(SUM(vi.views), 0) as total_views
            FROM users u
            JOIN videos v ON u.id = v.user_id
            LEFT JOIN video_interactions vi ON v.id = vi.video_id
            WHERE v.uploaded_at >= ? AND v.uploaded_at < ?
            GROUP BY u.id, u.username
            HAVING total_views > 0
        ''', (
            f'{year}-{month:02d}-01',
            f'{year}-{month+1:02d}-01' if month < 12 else f'{year+1}-01-01'
        )).fetchall()

        # Filter by eligibility
        distributions = []
        total_eligible_views = 0

        for creator in eligible_creators:
            is_eligible, _ = self.check_eligibility(creator['id'])
            if is_eligible:
                total_eligible_views += creator['total_views']

        # Calculate distributions
        for creator in eligible_creators:
            is_eligible, _ = self.check_eligibility(creator['id'])
            if is_eligible and total_eligible_views > 0:
                view_share = creator['total_views'] / total_eligible_views
                raw_amount = monthly_pool * view_share
                capped_amount = min(raw_amount, self.monthly_cap)

                distributions.append({
                    'user_id': creator['id'],
                    'username': creator['username'],
                    'total_views': creator['total_views'],
                    'view_share': view_share,
                    'raw_amount': raw_amount,
                    'final_amount': capped_amount
                })

        return distributions

    def distribute_monthly_fund(self, month: int, year: int) -> Dict:
        """Execute monthly fund distribution"""
        distributions = self.calculate_monthly_distribution(month, year)
        db = get_db()

        total_distributed = 0
        successful_distributions = 0

        for dist in distributions:
            try:
                # Record distribution
                db.execute('''
                    INSERT INTO creator_fund_distributions
                    (user_id, month, year, amount, total_views, eligible_views)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    dist['user_id'],
                    month,
                    year,
                    dist['final_amount'],
                    dist['total_views'],
                    dist['total_views']
                ))

                # Add RTC to user balance
                db.execute('''
                    UPDATE users SET rtc_balance = rtc_balance + ?
                    WHERE id = ?
                ''', (dist['final_amount'], dist['user_id']))

                total_distributed += dist['final_amount']
                successful_distributions += 1

            except Exception as e:
                logger.error(f"Failed to distribute to user {dist['user_id']}: {e}")
                continue

        db.commit()

        return {
            'month': month,
            'year': year,
            'total_distributed': total_distributed,
            'recipients': successful_distributions,
            'distributions': distributions
        }
