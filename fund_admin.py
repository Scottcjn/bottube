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
           AND video_count >= 5
           AND last_upload >= ?
        ORDER BY total_views DESC
    ''', (thirty_days_ago.strftime('%Y-%m-%d'), thirty_days_ago.strftime('%Y-%m-%d')))

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


@fund_admin_bp.route('/distribute', methods=['POST'])
@require_admin
def distribute_funds():
    """Execute monthly fund distribution"""
    try:
        from creator_fund import CreatorFund

        fund = CreatorFund()
        current_date = datetime.now()
        month = current_date.month
        year = current_date.year

        # Execute distribution
        result = fund.distribute_monthly_fund(month, year)

        flash(f"Successfully distributed {result['total_distributed']:.2f} RTC to {result['recipients']} creators", 'success')

        return jsonify({
            'success': True,
            'message': f"Distributed {result['total_distributed']:.2f} RTC",
            'data': result
        })

    except Exception as e:
        flash(f"Distribution failed: {str(e)}", 'error')
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500


@fund_admin_bp.route('/history')
@require_admin
def distribution_history():
    """View fund distribution history"""
    db = get_db()

    distributions = db.execute('''
        SELECT
            fd.id,
            fd.month,
            fd.year,
            fd.amount,
            fd.total_views,
            fd.created_at,
            u.username
        FROM creator_fund_distributions fd
        JOIN users u ON fd.user_id = u.id
        ORDER BY fd.created_at DESC
        LIMIT 100
    ''').fetchall()

    return render_template('admin/fund_history.html',
                         distributions=distributions)


@fund_admin_bp.route('/eligibility')
@require_admin
def check_eligibility():
    """Check creator eligibility details"""
    from creator_fund import CreatorFund

    fund = CreatorFund()
    db = get_db()

    # Get all creators with basic stats
    creators = db.execute('''
        SELECT u.id, u.username,
               COUNT(DISTINCT s.follower_id) as subscriber_count,
               COUNT(DISTINCT v.id) as video_count
        FROM users u
        LEFT JOIN subscriptions s ON u.id = s.user_id
        LEFT JOIN videos v ON u.id = v.user_id
        GROUP BY u.id, u.username
        ORDER BY subscriber_count DESC
    ''').fetchall()

    # Check eligibility for each
    eligibility_results = []
    for creator in creators:
        is_eligible, details = fund.check_eligibility(creator['id'])
        eligibility_results.append({
            'user_id': creator['id'],
            'username': creator['username'],
            'is_eligible': is_eligible,
            'details': details
        })

    return render_template('admin/fund_eligibility.html',
                         eligibility_results=eligibility_results)


@fund_admin_bp.route('/simulate')
@require_admin
def simulate_distribution():
    """Simulate next month's distribution without executing"""
    from creator_fund import CreatorFund

    fund = CreatorFund()
    current_date = datetime.now()
    month = current_date.month
    year = current_date.year

    # Calculate what would be distributed
    distributions = fund.calculate_monthly_distribution(month, year)

    total_amount = sum(d['final_amount'] for d in distributions)
    total_recipients = len(distributions)

    return render_template('admin/fund_simulation.html',
                         distributions=distributions,
                         total_amount=total_amount,
                         total_recipients=total_recipients,
                         month=month,
                         year=year)
