"""Regression coverage for payout-wallet field type contracts."""


def test_wallet_update_rejects_non_string_fields_without_mutation(client, registered_agent):
    headers = {"X-API-Key": registered_agent["api_key"]}
    fields = ("rtc_wallet", "rtc", "btc", "eth", "sol", "ltc", "erg", "paypal")

    for field in fields:
        response = client.post(
            "/api/agents/me/wallet",
            headers=headers,
            json={field: {"nested": "address"}},
        )
        assert response.status_code == 400, (field, response.get_json())

    null_response = client.post(
        "/api/agents/me/wallet",
        headers=headers,
        json={"btc": None},
    )
    assert null_response.status_code == 400

    wallet = client.get("/api/agents/me/wallet", headers=headers)
    assert wallet.status_code == 200
    assert all(value == "" for value in wallet.get_json()["wallets"].values())


def test_wallet_update_preserves_valid_partial_string_updates(client, registered_agent):
    headers = {"X-API-Key": registered_agent["api_key"]}
    response = client.post(
        "/api/agents/me/wallet",
        headers=headers,
        json={"btc": "bc1-example", "paypal": "pay@example.com"},
    )

    assert response.status_code == 200
    assert response.get_json()["updated_fields"] == ["btc", "paypal"]
    wallet = client.get("/api/agents/me/wallet", headers=headers).get_json()["wallets"]
    assert wallet["btc"] == "bc1-example"
    assert wallet["paypal"] == "pay@example.com"
