# SPDX-License-Identifier: MIT
"""Regression coverage: RTC service endpoints must reject non-object JSON bodies.

``request.get_json(...) or {}`` is not a body-shape guard: a JSON array, string or
number is truthy, so it survives the ``or`` and the next ``data.get(...)`` raises
``AttributeError`` -> HTTP 500.

``/api/rtc/redeem`` and ``/api/rtc/use`` parse the body *before* any auth check, so
that 500 was reachable without credentials and returned an unhandled exception from
a payment-service endpoint instead of a bounded client error.
"""

import pytest

RTC_POST_ENDPOINTS = ["/api/rtc/pay", "/api/rtc/redeem", "/api/rtc/use"]

# Truthy non-object JSON values — the ones that slip past `or {}`.
NON_OBJECT_BODIES = ["[1, 2, 3]", '"just-a-string"', "42", "3.5", "true"]


@pytest.mark.parametrize("path", RTC_POST_ENDPOINTS)
@pytest.mark.parametrize("body", NON_OBJECT_BODIES)
def test_rtc_endpoints_reject_non_object_json(client, registered_agent, path, body):
    """A non-object JSON body must yield a bounded 400, never an unhandled 500."""
    resp = client.post(
        path,
        headers={"X-API-Key": registered_agent["api_key"]},
        data=body,
        content_type="application/json",
    )
    assert resp.status_code == 400, (
        f"{path} returned {resp.status_code} for body {body!r}"
    )
    assert resp.get_json()["error"] == "JSON body must be an object"


@pytest.mark.parametrize("path", ["/api/rtc/redeem", "/api/rtc/use"])
@pytest.mark.parametrize("body", NON_OBJECT_BODIES)
def test_redeem_and_use_do_not_500_without_credentials(client, path, body):
    """These two parse the body before auth, so the 500 was reachable unauthenticated."""
    resp = client.post(path, data=body, content_type="application/json")
    assert resp.status_code != 500, (
        f"{path} returned 500 unauthenticated for body {body!r}"
    )
    assert resp.status_code == 400, resp.status_code


@pytest.mark.parametrize("path", RTC_POST_ENDPOINTS)
def test_object_bodies_still_reach_business_logic(client, registered_agent, path):
    """The guard must not change behaviour for well-formed object bodies."""
    resp = client.post(
        path,
        headers={"X-API-Key": registered_agent["api_key"]},
        json={"service_token": "not-a-real-token"},
    )
    assert resp.status_code != 500, resp.status_code
    assert resp.status_code in (400, 401, 402, 404), resp.status_code


@pytest.mark.parametrize("path", RTC_POST_ENDPOINTS)
def test_empty_body_is_treated_as_empty_object(client, registered_agent, path):
    """A missing/empty body keeps the previous lenient behaviour (no 500)."""
    resp = client.post(path, headers={"X-API-Key": registered_agent["api_key"]})
    assert resp.status_code != 500, resp.status_code
