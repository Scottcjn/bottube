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
        WHERE v.uploaded_at >= ? OR v.uploaded_at IS NULL
        GROUP BY u.id, u.username, u.created_at
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
def distribute_funds():
    """Trigger monthly fund distribution"""
    from creator_fund import CreatorFund

    target_month = request.form.get('month', datetime.now().month)
    target_year = request.form.get('year', datetime.now().year)

    try:
        target_month = int(target_month)
        target_year = int(target_year)
    except ValueError:
        flash('Invalid month or year provided', 'error')
        return redirect(url_for('fund_admin.dashboard'))

    fund = CreatorFund()
    distributions = fund.calculate_monthly_distribution(target_month, target_year)

    if not distributions:
        flash('No eligible creators found for distribution', 'warning')
        return redirect(url_for('fund_admin.dashboard'))

    if fund.process_distribution(distributions):
        total_amount = sum(d['final_amount'] for d in distributions)
        flash(f'Successfully distributed {total_amount:.2f} RTC to {len(distributions)} creators', 'success')
    else:
        flash('Error processing fund distribution', 'error')

    return redirect(url_for('fund_admin.dashboard'))


@fund_admin_bp.route('/preview/<int:month>/<int:year>')
@require_admin
def preview_distribution(month, year):
    """Preview fund distribution without processing"""
    from creator_fund import CreatorFund

    fund = CreatorFund()
    distributions = fund.calculate_monthly_distribution(month, year)

    return jsonify({
        'success': True,
        'distributions': distributions,
        'total_amount': sum(d['final_amount'] for d in distributions),
        'total_creators': len(distributions)
    })


@fund_admin_bp.route('/history')
@require_admin
def distribution_history():
    """View fund distribution history"""
    db = get_db()

    cursor = db.execute('''
        SELECT
            d.*,
            u.username
        FROM creator_fund_distributions d
        JOIN users u ON d.user_id = u.id
        ORDER BY d.year DESC, d.month DESC, d.amount DESC
    ''')

    distributions = [dict(row) for row in cursor.fetchall()]

    return render_template('admin/fund_history.html',
                         distributions=distributions)


@fund_admin_bp.route('/eligibility/refresh')
@require_admin
def refresh_eligibility():
    """Refresh eligibility status for all creators"""
    from creator_fund import CreatorFund

    db = get_db()
    cursor = db.execute('SELECT id FROM users WHERE active = 1')
    user_ids = [row['id'] for row in cursor.fetchall()]

    fund = CreatorFund()
    updated_count = 0

    for user_id in user_ids:
        is_eligible, _ = fund.check_eligibility(user_id)
        if is_eligible:
            updated_count += 1

    flash(f'Refreshed eligibility for {len(user_ids)} users. {updated_count} are currently eligible.', 'success')
    return redirect(url_for('fund_admin.dashboard'))


@fund_admin_bp.route('/stats')
@require_admin
def fund_statistics():
    """View detailed fund statistics"""
    from creator_fund import CreatorFund

    fund = CreatorFund()
    stats = fund.get_fund_statistics()

    return jsonify(stats)
