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
            return False, {'error': 'User not found'}

        # Check eligibility criteria
        subscriber_count = user_data['subscriber_count'] or 0
        video_count = user_data['video_count'] or 0
        last_upload = user_data['last_upload']

        is_eligible = (
            subscriber_count >= 100 and
            video_count >= 3 and
            last_upload and
            datetime.fromisoformat(last_upload.replace('Z', '+00:00')).replace(tzinfo=None) >= thirty_days_ago
        )

        eligibility_data = {
            'subscriber_count': subscriber_count,
            'video_count': video_count,
            'last_upload': last_upload,
            'is_eligible': is_eligible
        }

        # Cache eligibility result
        db.execute('''
            INSERT OR REPLACE INTO creator_fund_eligibility
            (user_id, is_eligible, subscriber_count, video_count, last_activity)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            user_id,
            is_eligible,
            subscriber_count,
            video_count,
            last_upload or datetime.now().date().isoformat()
        ))
        db.commit()

        return is_eligible, eligibility_data

    def get_eligible_creators(self) -> List[Dict]:
        """Get all eligible creators for the current month"""
        db = get_db()
        eligible_creators = []

        # Get all users with recent activity
        cursor = db.execute('''
            SELECT DISTINCT u.id
            FROM users u
            JOIN videos v ON u.id = v.user_id
            WHERE v.uploaded_at >= date('now', '-30 days')
        ''')

        for row in cursor.fetchall():
            is_eligible, data = self.check_eligibility(row['id'])
            if is_eligible:
                eligible_creators.append({
                    'user_id': row['id'],
                    **data
                })

        return eligible_creators

    def calculate_monthly_distribution(self, month: int, year: int) -> Dict:
        """Calculate RTC distribution for eligible creators"""
        eligible_creators = self.get_eligible_creators()

        if not eligible_creators:
            return {'total_distributed': 0, 'distributions': []}

        # Determine month pool (1-indexed)
        month_number = ((year - 2024) * 12 + month - 1) % 3 + 1
        total_pool = self.pilot_pools.get(month_number, 200)

        # Get view counts for eligible creators
        db = get_db()
        distributions = []
        total_views = 0

        for creator in eligible_creators:
            cursor = db.execute('''
                SELECT COALESCE(SUM(views), 0) as views
                FROM video_interactions vi
                JOIN videos v ON vi.video_id = v.id
                WHERE v.user_id = ?
                AND vi.interaction_type = 'view'
                AND DATE(vi.created_at) >= DATE(?, 'start of month')
                AND DATE(vi.created_at) < DATE(?, '+1 month', 'start of month')
            ''', (creator['user_id'], f'{year}-{month:02d}-01', f'{year}-{month:02d}-01'))

            views = cursor.fetchone()['views']
            total_views += views

            distributions.append({
                'user_id': creator['user_id'],
                'views': views,
                'amount': 0  # Will calculate after getting total
            })

        # Calculate proportional distribution
        if total_views > 0:
            for dist in distributions:
                proportion = dist['views'] / total_views
                amount = min(proportion * total_pool, self.monthly_cap)
                dist['amount'] = round(amount, 2)

        total_distributed = sum(d['amount'] for d in distributions)

        return {
            'total_pool': total_pool,
            'total_distributed': total_distributed,
            'total_views': total_views,
            'distributions': distributions
        }

    def process_monthly_distribution(self, month: int, year: int) -> Dict:
        """Process and record monthly RTC distribution"""
        distribution_data = self.calculate_monthly_distribution(month, year)

        if not distribution_data['distributions']:
            return distribution_data

        db = get_db()

        try:
            for dist in distribution_data['distributions']:
                if dist['amount'] > 0:
                    # Record distribution
                    db.execute('''
                        INSERT OR REPLACE INTO creator_fund_distributions
                        (user_id, month, year, amount, total_views, eligible_views)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        dist['user_id'],
                        month,
                        year,
                        dist['amount'],
                        distribution_data['total_views'],
                        dist['views']
                    ))

                    # Add RTC to user balance
                    db.execute('''
                        UPDATE users SET rtc_balance = rtc_balance + ?
                        WHERE id = ?
                    ''', (dist['amount'], dist['user_id']))

            db.commit()
            distribution_data['status'] = 'success'

        except Exception as e:
            db.rollback()
            distribution_data['status'] = 'error'
            distribution_data['error'] = str(e)
            logger.error(f"Distribution processing failed: {e}")

        return distribution_data

    def get_distribution_history(self, user_id: Optional[int] = None) -> List[Dict]:
        """Get distribution history"""
        db = get_db()

        if user_id:
            cursor = db.execute('''
                SELECT cfd.*, u.username
                FROM creator_fund_distributions cfd
                JOIN users u ON cfd.user_id = u.id
                WHERE cfd.user_id = ?
                ORDER BY cfd.year DESC, cfd.month DESC
            ''', (user_id,))
        else:
            cursor = db.execute('''
                SELECT cfd.*, u.username
                FROM creator_fund_distributions cfd
                JOIN users u ON cfd.user_id = u.id
                ORDER BY cfd.year DESC, cfd.month DESC
            ''')

        return [dict(row) for row in cursor.fetchall()]
