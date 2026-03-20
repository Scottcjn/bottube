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
                u.created_at,
                COUNT(DISTINCT s.follower_id) as subscriber_count,
                COUNT(DISTINCT v.id) as video_count,
                COALESCE(SUM(vi.views), 0) as total_views,
                MAX(v.uploaded_at) as last_upload
            FROM users u
            LEFT JOIN subscriptions s ON u.id = s.user_id
            LEFT JOIN videos v ON u.id = v.user_id
            LEFT JOIN video_interactions vi ON v.id = vi.video_id
            WHERE u.id = ?
            GROUP BY u.id
        ''', (user_id,))

        user_stats = cursor.fetchone()
        if not user_stats:
            return False, {"reason": "User not found"}

        stats_dict = dict(user_stats)

        # Check eligibility criteria
        is_eligible = (
            stats_dict['subscriber_count'] >= 100 and
            stats_dict['video_count'] >= 5 and
            stats_dict['last_upload'] and
            datetime.fromisoformat(stats_dict['last_upload'].replace('Z', '+00:00')) >= thirty_days_ago
        )

        return is_eligible, stats_dict

    def calculate_monthly_distribution(self, month: int, year: int) -> List[Dict]:
        """Calculate fund distribution for eligible creators"""
        db = get_db()

        # Get all eligible creators for the month
        eligible_creators = self._get_eligible_creators_for_month(month, year)
        if not eligible_creators:
            return []

        # Calculate total eligible views
        total_eligible_views = sum(creator['eligible_views'] for creator in eligible_creators)
        if total_eligible_views == 0:
            return []

        # Determine pool size based on pilot month
        pilot_month = self._get_pilot_month(month, year)
        pool_size = self.pilot_pools.get(pilot_month, 150)

        distributions = []
        for creator in eligible_creators:
            # Calculate share based on eligible views
            view_share = creator['eligible_views'] / total_eligible_views
            raw_amount = pool_size * view_share

            # Apply monthly cap
            final_amount = min(raw_amount, self.monthly_cap)

            distributions.append({
                'user_id': creator['user_id'],
                'username': creator['username'],
                'amount': round(final_amount, 2),
                'eligible_views': creator['eligible_views'],
                'total_views': creator['total_views'],
                'view_share': round(view_share * 100, 2)
            })

        return distributions

    def _get_eligible_creators_for_month(self, month: int, year: int) -> List[Dict]:
        """Get eligible creators and their stats for a specific month"""
        db = get_db()

        # Calculate date range for the month
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1)
        else:
            end_date = datetime(year, month + 1, 1)

        cursor = db.execute('''
            SELECT
                u.id as user_id,
                u.username,
                COUNT(DISTINCT s.follower_id) as subscriber_count,
                COUNT(DISTINCT v.id) as video_count,
                COALESCE(SUM(
                    CASE WHEN vi.created_at >= ? AND vi.created_at < ?
                    THEN vi.views ELSE 0 END
                ), 0) as eligible_views,
                COALESCE(SUM(vi.views), 0) as total_views
            FROM users u
            LEFT JOIN subscriptions s ON u.id = s.user_id
            LEFT JOIN videos v ON u.id = v.user_id
            LEFT JOIN video_interactions vi ON v.id = vi.video_id
            WHERE u.created_at < ?
            GROUP BY u.id
            HAVING subscriber_count >= 100
                AND video_count >= 5
                AND eligible_views > 0
        ''', (start_date.isoformat(), end_date.isoformat(), end_date.isoformat()))

        return [dict(row) for row in cursor.fetchall()]

    def _get_pilot_month(self, month: int, year: int) -> int:
        """Determine which pilot month this is (1-3)"""
        # This would need to be adjusted based on pilot start date
        # For now, assuming pilot started in current year
        current_year = datetime.now().year
        if year == current_year:
            return min(month, 3)
        return 3

    def process_monthly_distribution(self, month: int, year: int) -> Dict:
        """Process and record monthly fund distribution"""
        db = get_db()

        # Check if distribution already exists
        existing = db.execute('''
            SELECT id FROM creator_fund_distributions
            WHERE month = ? AND year = ?
            LIMIT 1
        ''', (month, year)).fetchone()

        if existing:
            return {"error": "Distribution already processed for this month"}

        # Calculate distributions
        distributions = self.calculate_monthly_distribution(month, year)
        if not distributions:
            return {"error": "No eligible creators found"}

        # Record distributions
        total_distributed = 0
        for dist in distributions:
            db.execute('''
                INSERT INTO creator_fund_distributions
                (user_id, month, year, amount, total_views, eligible_views)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                dist['user_id'], month, year, dist['amount'],
                dist['total_views'], dist['eligible_views']
            ))
            total_distributed += dist['amount']

        db.commit()

        return {
            "success": True,
            "total_distributed": round(total_distributed, 2),
            "creator_count": len(distributions),
            "distributions": distributions
        }

    def get_creator_earnings(self, user_id: int) -> List[Dict]:
        """Get earning history for a creator"""
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
