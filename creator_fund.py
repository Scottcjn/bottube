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
        thirty_days_ago = datetime.now() - timedelta(days=30)

        # Get user stats
        cursor = db.execute('''
            SELECT
                u.id,
                u.username,
                COUNT(DISTINCT s.follower_id) as subscriber_count,
                COUNT(DISTINCT v.id) as video_count,
                MAX(v.uploaded_at) as last_upload
            FROM users u
            LEFT JOIN subscriptions s ON u.id = s.user_id
            LEFT JOIN videos v ON u.id = v.user_id
            WHERE u.id = ?
            GROUP BY u.id
        ''', (user_id,))

        user_data = cursor.fetchone()
        if not user_data:
            return False, {"error": "User not found"}

        # Check eligibility criteria
        subscriber_count = user_data['subscriber_count'] or 0
        video_count = user_data['video_count'] or 0
        last_upload = user_data['last_upload']

        criteria = {
            "has_min_subscribers": subscriber_count >= 100,
            "has_min_videos": video_count >= 3,
            "recent_activity": last_upload and datetime.fromisoformat(last_upload) >= thirty_days_ago
        }

        is_eligible = all(criteria.values())

        # Cache eligibility status
        db.execute('''
            INSERT OR REPLACE INTO creator_fund_eligibility
            (user_id, is_eligible, subscriber_count, video_count, last_activity)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, is_eligible, subscriber_count, video_count, last_upload))
        db.commit()

        return is_eligible, {
            "subscriber_count": subscriber_count,
            "video_count": video_count,
            "last_upload": last_upload,
            "criteria": criteria
        }

    def calculate_monthly_distribution(self, month: int, year: int) -> List[Dict]:
        """Calculate monthly fund distribution for eligible creators"""
        db = get_db()

        # Get eligible creators with their view counts
        cursor = db.execute('''
            SELECT
                u.id,
                u.username,
                COALESCE(SUM(vi.views), 0) as total_views
            FROM creator_fund_eligibility e
            JOIN users u ON e.user_id = u.id
            LEFT JOIN videos v ON u.id = v.user_id
            LEFT JOIN video_interactions vi ON v.id = vi.video_id
            WHERE e.is_eligible = 1
            AND strftime('%m', v.uploaded_at) = printf('%02d', ?)
            AND strftime('%Y', v.uploaded_at) = ?
            GROUP BY u.id, u.username
            HAVING total_views > 0
            ORDER BY total_views DESC
        ''', (month, str(year)))

        eligible_creators = cursor.fetchall()

        if not eligible_creators:
            return []

        # Determine month number for pilot pool
        pilot_month = self._get_pilot_month(month, year)
        available_pool = self.pilot_pools.get(pilot_month, 200)

        # Calculate total eligible views
        total_eligible_views = sum(creator['total_views'] for creator in eligible_creators)

        distributions = []
        for creator in eligible_creators:
            if total_eligible_views > 0:
                share_ratio = creator['total_views'] / total_eligible_views
                raw_amount = available_pool * share_ratio
                capped_amount = min(raw_amount, self.monthly_cap)

                distributions.append({
                    'user_id': creator['id'],
                    'username': creator['username'],
                    'total_views': creator['total_views'],
                    'share_ratio': share_ratio,
                    'raw_amount': raw_amount,
                    'final_amount': capped_amount,
                    'month': month,
                    'year': year
                })

        return distributions

    def _get_pilot_month(self, month: int, year: int) -> int:
        """Determine which pilot month this represents"""
        # This is a simplified version - in practice you'd track pilot start date
        current_date = datetime(year, month, 1)
        pilot_start = datetime(2024, 1, 1)  # Adjust based on actual pilot start

        months_since_start = (current_date.year - pilot_start.year) * 12 + (current_date.month - pilot_start.month)
        return min(months_since_start + 1, 3)  # Cap at month 3

    def process_distribution(self, distributions: List[Dict]) -> bool:
        """Process and record fund distributions"""
        if not distributions:
            return False

        db = get_db()
        try:
            for dist in distributions:
                # Record distribution
                db.execute('''
                    INSERT OR REPLACE INTO creator_fund_distributions
                    (user_id, month, year, amount, total_views, eligible_views)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    dist['user_id'],
                    dist['month'],
                    dist['year'],
                    dist['final_amount'],
                    dist['total_views'],
                    dist['total_views']  # For now, eligible_views = total_views
                ))

                # Update user's RTC balance
                db.execute('''
                    UPDATE users
                    SET rtc_balance = rtc_balance + ?
                    WHERE id = ?
                ''', (dist['final_amount'], dist['user_id']))

            db.commit()
            logger.info(f"Processed {len(distributions)} creator fund distributions")
            return True

        except Exception as e:
            db.rollback()
            logger.error(f"Error processing distributions: {e}")
            return False

    def get_user_fund_history(self, user_id: int) -> List[Dict]:
        """Get fund distribution history for a specific user"""
        db = get_db()
        cursor = db.execute('''
            SELECT
                month,
                year,
                amount,
                total_views,
                eligible_views,
                created_at
            FROM creator_fund_distributions
            WHERE user_id = ?
            ORDER BY year DESC, month DESC
        ''', (user_id,))

        return [dict(row) for row in cursor.fetchall()]

    def get_fund_statistics(self) -> Dict:
        """Get overall fund statistics"""
        db = get_db()

        cursor = db.execute('''
            SELECT
                COUNT(DISTINCT user_id) as total_recipients,
                SUM(amount) as total_distributed,
                AVG(amount) as avg_distribution,
                COUNT(*) as total_distributions
            FROM creator_fund_distributions
        ''')

        stats = dict(cursor.fetchone())

        # Calculate remaining pilot pool
        total_pilot_pool = sum(self.pilot_pools.values())
        stats['remaining_pool'] = total_pilot_pool - (stats['total_distributed'] or 0)
        stats['total_pilot_pool'] = total_pilot_pool

        return stats
