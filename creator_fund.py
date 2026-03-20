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
                   MAX(v.created_at) as last_video_date,
                   MAX(COALESCE(v.created_at, u.created_at)) as last_activity
            FROM users u
            LEFT JOIN subscriptions s ON u.id = s.user_id
            LEFT JOIN videos v ON u.id = v.user_id
            WHERE u.id = ?
            GROUP BY u.id
        ''', (user_id,)).fetchone()

        if not user_stats:
            return False, {"reason": "User not found"}

        stats = dict(user_stats)

        # Check minimum subscribers (10+)
        if stats['subscriber_count'] < 10:
            return False, {
                "reason": "Insufficient subscribers",
                "required": 10,
                "current": stats['subscriber_count']
            }

        # Check minimum videos (10+)
        if stats['video_count'] < 10:
            return False, {
                "reason": "Insufficient videos",
                "required": 10,
                "current": stats['video_count']
            }

        # Check activity in last 30 days
        if stats['last_activity']:
            last_active = datetime.fromisoformat(stats['last_activity'].replace('Z', '+00:00'))
            thirty_days_ago = datetime.now() - timedelta(days=30)

            if last_active < thirty_days_ago:
                return False, {
                    "reason": "Inactive for >30 days",
                    "last_activity": stats['last_activity']
                }

        # Check for spam content (basic flag check)
        spam_count = db.execute('''
            SELECT COUNT(*) as spam_videos
            FROM videos
            WHERE user_id = ? AND is_flagged = 1
        ''', (user_id,)).fetchone()['spam_videos']

        if spam_count > 0:
            return False, {
                "reason": "Flagged content detected",
                "flagged_videos": spam_count
            }

        return True, {
            "subscriber_count": stats['subscriber_count'],
            "video_count": stats['video_count'],
            "last_activity": stats['last_activity']
        }

    def get_eligible_creators(self) -> List[Dict]:
        """Get all creators eligible for the fund"""
        db = get_db()

        all_users = db.execute('SELECT id FROM users').fetchall()
        eligible_creators = []

        for user in all_users:
            is_eligible, stats = self.check_eligibility(user['id'])
            if is_eligible:
                eligible_creators.append({
                    'user_id': user['id'],
                    'stats': stats
                })

                # Cache eligibility
                db.execute('''
                    INSERT OR REPLACE INTO creator_fund_eligibility
                    (user_id, is_eligible, subscriber_count, video_count,
                     last_activity, last_checked)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user['id'], True, stats['subscriber_count'],
                      stats['video_count'], stats['last_activity'],
                      datetime.now()))

        db.commit()
        return eligible_creators

    def calculate_monthly_distribution(self, month: int) -> Dict[int, float]:
        """Calculate RTC distribution for eligible creators"""
        if month not in self.pilot_pools:
            raise ValueError(f"Invalid month: {month}. Must be 1, 2, or 3")

        db = get_db()
        pool_size = self.pilot_pools[month]

        # Get eligible creators and their view counts
        eligible_creators = self.get_eligible_creators()

        if not eligible_creators:
            logger.info(f"No eligible creators for month {month}")
            return {}

        creator_views = {}
        total_eligible_views = 0

        for creator in eligible_creators:
            user_id = creator['user_id']

            # Get total views for this creator's videos
            view_data = db.execute('''
                SELECT COALESCE(SUM(views), 0) as total_views
                FROM videos
                WHERE user_id = ?
            ''', (user_id,)).fetchone()

            views = view_data['total_views'] if view_data else 0
            creator_views[user_id] = views
            total_eligible_views += views

        if total_eligible_views == 0:
            logger.info(f"No views found for eligible creators in month {month}")
            return {}

        # Calculate distribution
        distributions = {}

        for user_id, views in creator_views.items():
            if views > 0:
                # Pro-rata share calculation
                share_percentage = views / total_eligible_views
                raw_amount = pool_size * share_percentage

                # Apply monthly cap
                final_amount = min(raw_amount, self.monthly_cap)
                distributions[user_id] = final_amount

        return distributions

    def execute_distribution(self, month: int, year: int = None) -> Dict[str, any]:
        """Execute monthly fund distribution"""
        if year is None:
            year = datetime.now().year

        db = get_db()

        # Check if distribution already exists
        existing = db.execute('''
            SELECT COUNT(*) as count
            FROM creator_fund_distributions
            WHERE month = ? AND year = ?
        ''', (month, year)).fetchone()

        if existing['count'] > 0:
            raise ValueError(f"Distribution for {month}/{year} already executed")

        distributions = self.calculate_monthly_distribution(month)

        if not distributions:
            return {
                "success": False,
                "message": "No eligible creators found",
                "distributed": 0,
                "recipients": 0
            }

        total_distributed = 0
        recipient_count = 0

        for user_id, amount in distributions.items():
            # Get user's total views for record keeping
            total_views = db.execute('''
                SELECT COALESCE(SUM(views), 0) as total_views
                FROM videos WHERE user_id = ?
            ''', (user_id,)).fetchone()['total_views']

            # Record distribution
            db.execute('''
                INSERT INTO creator_fund_distributions
                (user_id, month, year, amount, total_views, eligible_views)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, month, year, amount, total_views, total_views))

            total_distributed += amount
            recipient_count += 1

        db.commit()

        return {
            "success": True,
            "month": month,
            "year": year,
            "pool_size": self.pilot_pools[month],
            "distributed": total_distributed,
            "recipients": recipient_count,
            "distributions": distributions
        }

    def get_creator_earnings(self, user_id: int) -> List[Dict]:
        """Get earning history for a specific creator"""
        db = get_db()

        earnings = db.execute('''
            SELECT month, year, amount, total_views, created_at
            FROM creator_fund_distributions
            WHERE user_id = ?
            ORDER BY year DESC, month DESC
        ''', (user_id,)).fetchall()

        return [dict(earning) for earning in earnings]

    def get_fund_statistics(self) -> Dict[str, any]:
        """Get overall fund statistics"""
        db = get_db()

        stats = db.execute('''
            SELECT
                COUNT(DISTINCT user_id) as total_recipients,
                SUM(amount) as total_distributed,
                AVG(amount) as avg_distribution,
                COUNT(*) as total_distributions
            FROM creator_fund_distributions
        ''').fetchone()

        monthly_stats = db.execute('''
            SELECT month, year,
                   COUNT(DISTINCT user_id) as recipients,
                   SUM(amount) as distributed,
                   AVG(amount) as avg_amount
            FROM creator_fund_distributions
            GROUP BY month, year
            ORDER BY year, month
        ''').fetchall()

        return {
            "overall": dict(stats) if stats else {},
            "monthly": [dict(row) for row in monthly_stats]
        }
