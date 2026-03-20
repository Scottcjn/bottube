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
        WHERE u.created_at < ?
        GROUP BY u.id
        HAVING subscriber_count >= 100
            AND video_count >= 5
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
    """Process monthly fund distribution"""
    try:
        month = int(request.form.get('month', datetime.now().month))
        year = int(request.form.get('year', datetime.now().year))

        from creator_fund import CreatorFund
        fund = CreatorFund()

        result = fund.process_monthly_distribution(month, year)

        if 'error' in result:
            flash(f"Distribution failed: {result['error']}", 'error')
        else:
            flash(
                f"Successfully distributed {result['total_distributed']} RTC "
                f"to {result['creator_count']} creators",
                'success'
            )

        return redirect(url_for('fund_admin.dashboard'))

    except Exception as e:
        flash(f"Distribution error: {str(e)}", 'error')
        return redirect(url_for('fund_admin.dashboard'))


@fund_admin_bp.route('/history')
@require_admin
def distribution_history():
    """View fund distribution history"""
    db = get_db()

    cursor = db.execute('''
        SELECT
            cfd.month,
            cfd.year,
            cfd.amount,
            cfd.created_at,
            u.username,
            cfd.eligible_views,
            cfd.total_views
        FROM creator_fund_distributions cfd
        JOIN users u ON cfd.user_id = u.id
        ORDER BY cfd.year DESC, cfd.month DESC, cfd.amount DESC
    ''')

    distributions = [dict(row) for row in cursor.fetchall()]

    return render_template('admin/fund_history.html',
                         distributions=distributions)


@fund_admin_bp.route('/creator/<int:user_id>')
@require_admin
def creator_details(user_id):
    """View detailed creator fund information"""
    from creator_fund import CreatorFund
    fund = CreatorFund()

    # Get creator info
    db = get_db()
    creator = db.execute('''
        SELECT id, username, created_at
        FROM users WHERE id = ?
    ''', (user_id,)).fetchone()

    if not creator:
        flash('Creator not found', 'error')
        return redirect(url_for('fund_admin.dashboard'))

    # Check eligibility
    is_eligible, stats = fund.check_eligibility(user_id)

    # Get earnings history
    earnings = fund.get_creator_earnings(user_id)

    return render_template('admin/creator_details.html',
                         creator=dict(creator),
                         is_eligible=is_eligible,
                         stats=stats,
                         earnings=earnings)


@fund_admin_bp.route('/api/eligibility/<int:user_id>')
@require_admin
def check_eligibility_api(user_id):
    """API endpoint to check creator eligibility"""
    from creator_fund import CreatorFund
    fund = CreatorFund()

    is_eligible, stats = fund.check_eligibility(user_id)

    return jsonify({
        'eligible': is_eligible,
        'stats': stats
    })


@fund_admin_bp.route('/api/simulate')
@require_admin
def simulate_distribution():
    """Simulate fund distribution without processing"""
    month = int(request.args.get('month', datetime.now().month))
    year = int(request.args.get('year', datetime.now().year))

    from creator_fund import CreatorFund
    fund = CreatorFund()

    distributions = fund.calculate_monthly_distribution(month, year)
    total_amount = sum(d['amount'] for d in distributions)

    return jsonify({
        'distributions': distributions,
        'total_amount': round(total_amount, 2),
        'creator_count': len(distributions)
    })
