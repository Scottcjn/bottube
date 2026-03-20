from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, g
from bottube_server import get_db, require_admin
from datetime import datetime, timedelta
import sqlite3

fund_admin_bp = Blueprint('fund_admin', __name__, url_prefix='/admin/fund')

def get_fund_status():
    db = get_db()

    # Get current fund pool status
    cursor = db.execute('''
        SELECT
            COALESCE(SUM(amount), 0) as total_pool,
            COUNT(DISTINCT month_year) as months_active,
            MAX(created_at) as last_distribution
        FROM fund_distributions
    ''')
    fund_data = cursor.fetchone()

    # Calculate remaining pool (500 RTC total pilot)
    total_pilot_pool = 500
    distributed = fund_data['total_pool'] if fund_data['total_pool'] else 0
    remaining_pool = total_pilot_pool - distributed

    # Get current month's allocation
    current_month = datetime.now().strftime('%Y-%m')
    months_elapsed = fund_data['months_active'] if fund_data['months_active'] else 0

    if months_elapsed == 0:
        current_allocation = 150  # Month 1
    elif months_elapsed == 1:
        current_allocation = 150  # Month 2
    else:
        current_allocation = 200  # Month 3

    return {
        'total_pilot_pool': total_pilot_pool,
        'distributed_amount': distributed,
        'remaining_pool': remaining_pool,
        'months_active': months_elapsed,
        'current_month': current_month,
        'current_allocation': current_allocation,
        'last_distribution': fund_data['last_distribution']
    }

def get_eligible_creators():
    db = get_db()
    thirty_days_ago = datetime.now() - timedelta(days=30)

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
        LEFT JOIN subscriptions s ON u.id = s.following_id
        LEFT JOIN videos v ON u.id = v.user_id
        LEFT JOIN video_interactions vi ON v.id = vi.video_id AND vi.interaction_type = 'view'
        WHERE v.uploaded_at >= ? AND u.is_bot = 1
        GROUP BY u.id, u.username, u.created_at
        HAVING subscriber_count >= 10
            AND video_count >= 10
            AND last_upload >= ?
        ORDER BY total_views DESC
    ''', (thirty_days_ago, thirty_days_ago))

    return cursor.fetchall()

def calculate_fund_distribution(eligible_creators, pool_amount, month_number):
    if not eligible_creators:
        return []

    total_views = sum(creator['total_views'] for creator in eligible_creators)
    if total_views == 0:
        return []

    distributions = []
    max_per_creator = 75  # Monthly cap

    for creator in eligible_creators:
        if month_number <= 2:
            # Months 1-2: Pro-rata by views only
            share_ratio = creator['total_views'] / total_views
        else:
            # Month 3: Views + engagement bonus
            engagement_bonus = min(creator['subscriber_count'] / 100, 0.2)  # Max 20% bonus
            base_ratio = creator['total_views'] / total_views
            share_ratio = base_ratio * (1 + engagement_bonus)

        calculated_amount = share_ratio * pool_amount
        final_amount = min(calculated_amount, max_per_creator)

        distributions.append({
            'creator_id': creator['id'],
            'username': creator['username'],
            'views': creator['total_views'],
            'subscribers': creator['subscriber_count'],
            'calculated_amount': calculated_amount,
            'final_amount': final_amount,
            'share_percentage': (share_ratio * 100)
        })

    return sorted(distributions, key=lambda x: x['final_amount'], reverse=True)

@fund_admin_bp.route('/')
@require_admin
def dashboard():
    fund_status = get_fund_status()
    eligible_creators = get_eligible_creators()

    # Get recent distributions
    db = get_db()
    cursor = db.execute('''
        SELECT
            fd.month_year,
            fd.amount,
            fd.created_at,
            u.username,
            fd.creator_views,
            fd.total_views
        FROM fund_distributions fd
        JOIN users u ON fd.creator_id = u.id
        ORDER BY fd.created_at DESC
        LIMIT 20
    ''')
    recent_distributions = cursor.fetchall()

    return render_template('admin/fund_dashboard.html',
                         fund_status=fund_status,
                         eligible_creators=eligible_creators,
                         recent_distributions=recent_distributions)

@fund_admin_bp.route('/preview_distribution')
@require_admin
def preview_distribution():
    fund_status = get_fund_status()
    eligible_creators = get_eligible_creators()

    month_number = fund_status['months_active'] + 1
    pool_amount = fund_status['current_allocation']

    distributions = calculate_fund_distribution(eligible_creators, pool_amount, month_number)

    return render_template('admin/fund_preview.html',
                         distributions=distributions,
                         fund_status=fund_status,
                         month_number=month_number)

@fund_admin_bp.route('/execute_distribution', methods=['POST'])
@require_admin
def execute_distribution():
    db = get_db()
    fund_status = get_fund_status()

    if fund_status['remaining_pool'] <= 0:
        flash('Fund pool is exhausted', 'error')
        return redirect(url_for('fund_admin.dashboard'))

    eligible_creators = get_eligible_creators()
    month_number = fund_status['months_active'] + 1
    pool_amount = fund_status['current_allocation']

    if pool_amount > fund_status['remaining_pool']:
        pool_amount = fund_status['remaining_pool']

    distributions = calculate_fund_distribution(eligible_creators, pool_amount, month_number)

    if not distributions:
        flash('No eligible creators found', 'warning')
        return redirect(url_for('fund_admin.dashboard'))

    current_month = datetime.now().strftime('%Y-%m')
    total_views = sum(creator['total_views'] for creator in eligible_creators)

    try:
        for dist in distributions:
            db.execute('''
                INSERT INTO fund_distributions
                (creator_id, month_year, amount, creator_views, total_views, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (dist['creator_id'], current_month, dist['final_amount'],
                  dist['views'], total_views, datetime.now()))

        db.commit()
        flash(f'Successfully distributed {sum(d["final_amount"] for d in distributions):.2f} RTC to {len(distributions)} creators', 'success')

    except sqlite3.Error as e:
        db.rollback()
        flash(f'Distribution failed: {str(e)}', 'error')

    return redirect(url_for('fund_admin.dashboard'))

@fund_admin_bp.route('/metrics')
@require_admin
def pilot_metrics():
    db = get_db()

    # Get pilot start date (first distribution)
    cursor = db.execute('SELECT MIN(created_at) as pilot_start FROM fund_distributions')
    pilot_start = cursor.fetchone()['pilot_start']

    if not pilot_start:
        return render_template('admin/fund_metrics.html', metrics=None)

    pilot_start_date = datetime.fromisoformat(pilot_start)

    # Before vs after pilot metrics
    cursor = db.execute('''
        SELECT
            COUNT(*) as total_uploads_before,
            COUNT(DISTINCT user_id) as active_creators_before
        FROM videos
        WHERE uploaded_at < ?
    ''', (pilot_start,))
    before_metrics = cursor.fetchone()

    cursor = db.execute('''
        SELECT
            COUNT(*) as total_uploads_after,
            COUNT(DISTINCT user_id) as active_creators_after
        FROM videos
        WHERE uploaded_at >= ?
    ''', (pilot_start,))
    after_metrics = cursor.fetchone()

    # Retention metrics
    cursor = db.execute('''
        SELECT
            COUNT(DISTINCT vi.user_id) as returning_viewers
        FROM video_interactions vi
        JOIN videos v ON vi.video_id = v.id
        WHERE v.uploaded_at >= ? AND vi.interaction_type = 'view'
        GROUP BY vi.user_id
        HAVING COUNT(DISTINCT DATE(vi.created_at)) >= 7
    ''', (pilot_start,))
    retention_data = cursor.fetchall()

    # Fund distribution summary
    cursor = db.execute('''
        SELECT
            COUNT(DISTINCT creator_id) as unique_recipients,
            SUM(amount) as total_distributed,
            AVG(amount) as avg_distribution,
            COUNT(*) as total_distributions
        FROM fund_distributions
    ''')
    distribution_summary = cursor.fetchone()

    metrics = {
        'pilot_start': pilot_start_date,
        'uploads_before': before_metrics['total_uploads_before'],
        'uploads_after': after_metrics['total_uploads_after'],
        'creators_before': before_metrics['active_creators_before'],
        'creators_after': after_metrics['active_creators_after'],
        'returning_viewers': len(retention_data),
        'unique_recipients': distribution_summary['unique_recipients'],
        'total_distributed': distribution_summary['total_distributed'],
        'avg_distribution': distribution_summary['avg_distribution'],
        'total_distributions': distribution_summary['total_distributions']
    }

    # Calculate growth rates
    if metrics['uploads_before'] > 0:
        metrics['upload_growth'] = ((metrics['uploads_after'] - metrics['uploads_before']) / metrics['uploads_before']) * 100
    else:
        metrics['upload_growth'] = 0

    if metrics['creators_before'] > 0:
        metrics['creator_growth'] = ((metrics['creators_after'] - metrics['creators_before']) / metrics['creators_before']) * 100
    else:
        metrics['creator_growth'] = 0

    return render_template('admin/fund_metrics.html', metrics=metrics)

@fund_admin_bp.route('/api/fund_status')
@require_admin
def api_fund_status():
    return jsonify(get_fund_status())
