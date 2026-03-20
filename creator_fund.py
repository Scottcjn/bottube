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
        user_stats = db.execute('''
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
            GROUP BY u.id, u.username
        ''', (user_id,)).fetchone()

        if not user_stats:
            return False, {"error": "User not found"}

        # Check eligibility criteria
        is_eligible = (
            user_stats['subscriber_count'] >= 100 and
            user_stats['video_count'] >= 3 and
            user_stats['last_upload'] and
            datetime.fromisoformat(user_stats['last_upload']) >= thirty_days_ago
        )

        eligibility_details = {
            "subscriber_count": user_stats['subscriber_count'],
            "video_count": user_stats['video_count'],
            "last_upload": user_stats['last_upload'],
            "meets_subscriber_req": user_stats['subscriber_count'] >= 100,
            "meets_video_req": user_stats['video_count'] >= 3,
            "meets_activity_req": (
                user_stats['last_upload'] and
                datetime.fromisoformat(user_stats['last_upload']) >= thirty_days_ago
            )
        }

        # Update eligibility cache
        db.execute('''
            INSERT OR REPLACE INTO creator_fund_eligibility
            (user_id, is_eligible, subscriber_count, video_count, last_activity)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            user_id,
            is_eligible,
            user_stats['subscriber_count'],
            user_stats['video_count'],
            user_stats['last_upload'] or ''
        ))
        db.commit()

        return is_eligible, eligibility_details

    def get_eligible_creators(self) -> List[Dict]:
        """Get all eligible creators for the current month"""
        db = get_db()
        thirty_days_ago = datetime.now() - timedelta(days=30)

        creators = db.execute('''
            SELECT
                u.id,
                u.username,
                COUNT(DISTINCT s.follower_id) as subscriber_count,
                COUNT(DISTINCT v.id) as video_count,
                COALESCE(SUM(vi.views), 0) as total_views,
                MAX(v.uploaded_at) as last_upload
            FROM users u
            LEFT JOIN subscriptions s ON u.id = s.user_id
            LEFT JOIN videos v ON u.id = v.user_id
            LEFT JOIN video_interactions vi ON v.id = vi.video_id
            WHERE v.uploaded_at >= ?
            GROUP BY u.id, u.username
            HAVING subscriber_count >= 100
               AND video_count >= 3
               AND last_upload >= ?
        ''', (thirty_days_ago.isoformat(), thirty_days_ago.isoformat())).fetchall()

        eligible_creators = []
        for creator in creators:
            eligible_creators.append({
                "user_id": creator['id'],
                "username": creator['username'],
                "subscriber_count": creator['subscriber_count'],
                "video_count": creator['video_count'],
                "total_views": creator['total_views'],
                "last_upload": creator['last_upload']
            })

        return eligible_creators

    def calculate_monthly_distribution(self, month: int, year: int) -> Dict:
        """Calculate RTC distribution for eligible creators"""
        eligible_creators = self.get_eligible_creators()

        if not eligible_creators:
            return {"total_distributed": 0, "distributions": []}

        # Determine month number for pilot (1-3)
        pilot_month = self._get_pilot_month(month, year)
        if pilot_month > 3:
            return {"error": "Pilot program ended"}

        monthly_pool = self.pilot_pools.get(pilot_month, 0)
        total_views = sum(creator['total_views'] for creator in eligible_creators)

        if total_views == 0:
            return {"total_distributed": 0, "distributions": []}

        distributions = []
        total_distributed = 0

        for creator in eligible_creators:
            # Calculate share based on views
            view_share = creator['total_views'] / total_views
            base_amount = monthly_pool * view_share

            # Apply individual cap
            capped_amount = min(base_amount, self.monthly_cap)
            total_distributed += capped_amount

            distributions.append({
                "user_id": creator['user_id'],
                "username": creator['username'],
                "amount": round(capped_amount, 2),
                "views": creator['total_views'],
                "view_share": round(view_share * 100, 2)
            })

        return {
            "total_distributed": round(total_distributed, 2),
            "monthly_pool": monthly_pool,
            "distributions": distributions
        }

    def _get_pilot_month(self, month: int, year: int) -> int:
        """Calculate which pilot month this is (1-3)"""
        pilot_start = datetime(2024, 1, 1)  # Adjust as needed
        target_date = datetime(year, month, 1)

        months_diff = (target_date.year - pilot_start.year) * 12 + target_date.month - pilot_start.month
        return months_diff + 1

    def distribute_funds(self, month: int, year: int) -> Dict:
        """Execute monthly fund distribution"""
        db = get_db()

        # Check if already distributed for this month
        existing = db.execute('''
            SELECT id FROM creator_fund_distributions
            WHERE month = ? AND year = ?
            LIMIT 1
        ''', (month, year)).fetchone()

        if existing:
            return {"error": "Already distributed for this month"}

        distribution_result = self.calculate_monthly_distribution(month, year)

        if "error" in distribution_result:
            return distribution_result

        # Record distributions
        for dist in distribution_result['distributions']:
            db.execute('''
                INSERT INTO creator_fund_distributions
                (user_id, month, year, amount, total_views, eligible_views)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                dist['user_id'],
                month,
                year,
                dist['amount'],
                dist['views'],
                dist['views']  # For now, all views are eligible
            ))

        db.commit()
        return distribution_result

    def get_creator_earnings(self, user_id: int) -> List[Dict]:
        """Get creator's fund earnings history"""
        db = get_db()

        earnings = db.execute('''
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
        ''', (user_id,)).fetchall()

        return [dict(row) for row in earnings]
