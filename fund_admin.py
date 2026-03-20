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
        LEFT JOIN subscriptions s ON u.id = s.user_id
        LEFT JOIN videos v ON u.id = v.user_id
        LEFT JOIN video_interactions vi ON v.id = vi.video_id AND vi.interaction_type = 'view'
        WHERE v.uploaded_at >= ?
        GROUP BY u.id
        HAVING
            subscriber_count >= 100
            AND video_count >= 3
            AND last_upload >= ?
        ORDER BY total_views DESC
    ''', (thirty_days_ago.isoformat(), thirty_days_ago.isoformat()))

    return [dict(row) for row in cursor.fetchall()]


@fund_admin_bp.route('/')
@require_admin
def dashboard():
    """Creator fund admin dashboard"""
    fund_status = get_fund_status()
    eligible_creators = get_eligible_creators()

    return render_template('admin/fund_dashboard.html',
                         fund_status=fund_status,
                         eligible_creators=eligible_creators)


@fund_admin_bp.route('/distribute', methods=['POST'])
@require_admin
def process_distribution():
    """Process monthly distribution"""
    from creator_fund import CreatorFund

    fund = CreatorFund()
    now = datetime.now()
    month = request.form.get('month', now.month, type=int)
    year = request.form.get('year', now.year, type=int)

    try:
        result = fund.process_monthly_distribution(month, year)

        if result['status'] == 'success':
            flash(f'Successfully distributed {result["total_distributed"]} RTC to {len(result["distributions"])} creators', 'success')
        else:
            flash(f'Distribution failed: {result.get("error", "Unknown error")}', 'error')

    except Exception as e:
        flash(f'Distribution error: {str(e)}', 'error')

    return redirect(url_for('fund_admin.dashboard'))


@fund_admin_bp.route('/history')
@require_admin
def distribution_history():
    """View distribution history"""
    from creator_fund import CreatorFund

    fund = CreatorFund()
    history = fund.get_distribution_history()

    return render_template('admin/fund_history.html', history=history)


@fund_admin_bp.route('/eligibility')
@require_admin
def check_eligibility():
    """Check creator eligibility"""
    user_id = request.args.get('user_id', type=int)

    if user_id:
        from creator_fund import CreatorFund
        fund = CreatorFund()
        is_eligible, data = fund.check_eligibility(user_id)

        return jsonify({
            'eligible': is_eligible,
            'data': data
        })

    eligible_creators = get_eligible_creators()
    return render_template('admin/fund_eligibility.html',
                         eligible_creators=eligible_creators)


@fund_admin_bp.route('/stats')
@require_admin
def fund_stats():
    """Fund statistics and analytics"""
    db = get_db()

    # Monthly distribution stats
    cursor = db.execute('''
        SELECT
            year,
            month,
            COUNT(*) as creator_count,
            SUM(amount) as total_amount,
            AVG(amount) as avg_amount,
            SUM(total_views) as total_views
        FROM creator_fund_distributions
        GROUP BY year, month
        ORDER BY year DESC, month DESC
    ''')
    monthly_stats = [dict(row) for row in cursor.fetchall()]

    # Top earning creators
    cursor = db.execute('''
        SELECT
            u.username,
            SUM(cfd.amount) as total_earned,
            COUNT(*) as months_participated,
            AVG(cfd.amount) as avg_monthly
        FROM creator_fund_distributions cfd
        JOIN users u ON cfd.user_id = u.id
        GROUP BY u.id, u.username
        ORDER BY total_earned DESC
        LIMIT 10
    ''')
    top_creators = [dict(row) for row in cursor.fetchall()]

    return render_template('admin/fund_stats.html',
                         monthly_stats=monthly_stats,
                         top_creators=top_creators)
