def test_ergo_bridge_info_route_is_registered():
    import bottube_server

    routes = {rule.rule for rule in bottube_server.app.url_map.iter_rules()}

    assert "/api/ergo/info" in routes
