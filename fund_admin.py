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
        LEFT JOIN video_interactions vi ON v.id = vi.video_id
        WHERE v.uploaded_at >= ?
        GROUP BY u.id, u.username, u.created_at
        HAVING subscriber_count >= 100
           AND video_count >= 3
           AND last_upload >= ?
        ORDER BY total_views DESC
    ''', (thirty_days_ago.isoformat(), thirty_days_ago.isoformat()))

    return cursor.fetchall()


@fund_admin_bp.route('/')
@require_admin
def dashboard():
    """Creator fund admin dashboard"""
    fund_status = get_fund_status()
    eligible_creators = get_eligible_creators()

    return render_template('admin/fund_dashboard.html',
                         fund_status=fund_status,
                         eligible_creators=eligible_creators)


@fund_admin_bp.route('/preview/<int:month>/<int:year>')
@require_admin
def preview_distribution(month, year):
    """Preview monthly distribution without executing"""
    from creator_fund import CreatorFund

    fund = CreatorFund()
    preview = fund.calculate_monthly_distribution(month, year)

    return jsonify(preview)


@fund_admin_bp.route('/distribute', methods=['POST'])
@require_admin
def execute_distribution():
    """Execute monthly fund distribution"""
    from creator_fund import CreatorFund

    month = request.form.get('month', type=int)
    year = request.form.get('year', type=int)

    if not month or not year:
        flash('Month and year are required', 'error')
        return redirect(url_for('fund_admin.dashboard'))

    fund = CreatorFund()
    result = fund.distribute_funds(month, year)

    if 'error' in result:
        flash(f'Distribution failed: {result["error"]}', 'error')
    else:
        flash(f'Successfully distributed {result["total_distributed"]} RTC to {len(result["distributions"])} creators', 'success')

    return redirect(url_for('fund_admin.dashboard'))


@fund_admin_bp.route('/creators/<int:user_id>/earnings')
@require_admin
def creator_earnings(user_id):
    """View specific creator's earnings history"""
    from creator_fund import CreatorFund

    fund = CreatorFund()
    earnings = fund.get_creator_earnings(user_id)
    is_eligible, eligibility = fund.check_eligibility(user_id)

    db = get_db()
    user = db.execute('SELECT username FROM users WHERE id = ?', (user_id,)).fetchone()

    return render_template('admin/creator_earnings.html',
                         user=user,
                         earnings=earnings,
                         is_eligible=is_eligible,
                         eligibility=eligibility)


@fund_admin_bp.route('/history')
@require_admin
def distribution_history():
    """View historical distributions"""
    db = get_db()

    distributions = db.execute('''
        SELECT
            d.month,
            d.year,
            d.amount,
            d.created_at,
            u.username
        FROM creator_fund_distributions d
        JOIN users u ON d.user_id = u.id
        ORDER BY d.year DESC, d.month DESC, d.amount DESC
    ''').fetchall()

    # Group by month/year
    grouped_distributions = {}
    for dist in distributions:
        month_key = f"{dist['year']}-{dist['month']:02d}"
        if month_key not in grouped_distributions:
            grouped_distributions[month_key] = {
                'month': dist['month'],
                'year': dist['year'],
                'created_at': dist['created_at'],
                'distributions': [],
                'total_amount': 0
            }

        grouped_distributions[month_key]['distributions'].append(dist)
        grouped_distributions[month_key]['total_amount'] += dist['amount']

    return render_template('admin/fund_history.html',
                         grouped_distributions=grouped_distributions)


@fund_admin_bp.route('/eligibility/refresh', methods=['POST'])
@require_admin
def refresh_eligibility():
    """Refresh eligibility cache for all creators"""
    from creator_fund import CreatorFund

    db = get_db()
    users = db.execute('SELECT id FROM users').fetchall()

    fund = CreatorFund()
    updated_count = 0

    for user in users:
        is_eligible, details = fund.check_eligibility(user['id'])
        updated_count += 1

    flash(f'Updated eligibility for {updated_count} creators', 'success')
    return redirect(url_for('fund_admin.dashboard'))
