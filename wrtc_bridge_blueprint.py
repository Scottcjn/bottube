@wrtc_bp.route("/bridge")
def wrtc_bridge_landing():
    user_balance = g.session.get('user_balance', 0)
    swap_url = WRTC_BUY_URL
    reserve_wallet = WRTC_RESERVE_WALLET
    user_sol_address = g.session.get('sol_address', '')
    return render_template(
        "bridge.html",
        wrtc_mint=WRTC_MINT,
        wrtc_reserve_wallet=WRTC_RESERVE_WALLET,
        wrtc_buy_url=WRTC_BUY_URL,
        user_balance=user_balance,
        swap_url=swap_url,
        reserve_wallet=reserve_wallet,
        user_sol_address=user_sol_address,
    )