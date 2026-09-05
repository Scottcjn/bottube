def test_ergo_bridge_info_route_is_registered():
    """Verify the /api/ergo/info route is registered in the Flask URL map.

    The Ergo bridge info endpoint exposes chain metadata (network id, tip
    height, last block hash) to clients integrating with the platform. This
    test confirms the route is wired into the app at startup, which is a
    precondition for any HTTP request to the endpoint to succeed end-to-end.
    """
    import bottube_server

    routes = {rule.rule for rule in bottube_server.app.url_map.iter_rules()}

    assert "/api/ergo/info" in routes
