import time

from generation.reliability import RetryPolicy, classify_error, provider_metrics_snapshot, run_with_retries


def test_classify_error_categories():
    """`classify_error` must sort errors into their retry-policy bucket.

    The category drives `run_with_retries`' retry decision downstream, so
    getting e.g. auth misclassified as transient would make the retry loop
    burn attempts hammering a key that will never work.
    """
    assert classify_error("401 unauthorized api key") == "auth"
    assert classify_error("429 rate limit exceeded") == "throttled"
    assert classify_error(TimeoutError("request timed out")) == "transient"
    assert classify_error("validation failed: bad prompt") == "permanent"


def test_run_with_retries_retries_transient_then_succeeds():
    """A transient error on attempt 1 should be retried and then succeed.

    Confirms both the outward result (ok, value, attempts) and that a
    successful retry still lands in `provider_metrics_snapshot()`, since a
    retry path that recovers the call but forgets to record it would hide
    real flakiness from provider health dashboards.
    """
    calls = {"count": 0}

    def flaky():
        """Fail with a transient timeout once, then return a fake job id."""
        calls["count"] += 1
        if calls["count"] < 2:
            raise TimeoutError("temporary provider timeout")
        return (True, "job-123")

    ok, value, category, latency_s, attempts = run_with_retries(
        "unit_provider_retry",
        "submit",
        flaky,
        RetryPolicy(attempts=3, base_delay_s=0.0, max_delay_s=0.0, jitter_s=0.0),
    )

    assert ok is True
    assert value == (True, "job-123")
    assert category == "ok"
    assert attempts == 2
    assert latency_s >= 0
    metrics = provider_metrics_snapshot()["unit_provider_retry"]
    assert metrics["attempts"] >= 1
    assert metrics["successes"] >= 1


def test_run_with_retries_does_not_retry_auth_errors():
    """Auth failures must fail fast instead of burning the retry budget.

    Asserts `calls["count"] == 1` specifically because a bad API key will
    never succeed on a second try -- retrying it just multiplies wasted
    provider requests (and, on some providers, lockout risk) for zero gain.
    """
    calls = {"count": 0}

    def auth_failure():
        """Always raise a 403, simulating a permanently invalid API key."""
        calls["count"] += 1
        raise RuntimeError("403 forbidden: invalid API key")

    ok, value, category, latency_s, attempts = run_with_retries(
        "unit_provider_auth",
        "submit",
        auth_failure,
        RetryPolicy(attempts=3, base_delay_s=0.0, max_delay_s=0.0, jitter_s=0.0),
    )

    assert ok is False
    assert value is None
    assert category == "auth"
    assert attempts == 1
    assert calls["count"] == 1
    assert latency_s >= 0
    metrics = provider_metrics_snapshot()["unit_provider_auth"]
    assert metrics["failures"] >= 1
    assert metrics["error_categories"]["auth"] >= 1


def test_run_with_retries_records_semantic_false_result_as_failure():
    """A call that returns cleanly but fails its `success_predicate` is a failure.

    Providers can return `(False, "quota exhausted")` without raising, so
    the retry harness needs a semantic check on top of exception handling
    -- otherwise a call that "succeeds" at the transport level while
    failing at the business level would be misreported as a success.
    """
    ok, value, category, latency_s, attempts = run_with_retries(
        "unit_provider_semantic_false",
        "submit",
        lambda: (False, "quota exhausted"),
        RetryPolicy(attempts=1, base_delay_s=0.0, max_delay_s=0.0, jitter_s=0.0),
        success_predicate=lambda result: result[0],
    )

    assert ok is False
    assert value == (False, "quota exhausted")
    assert category == "throttled"
    assert attempts == 1
    assert latency_s >= 0
    metrics = provider_metrics_snapshot()["unit_provider_semantic_false"]
    assert metrics["successes"] == 0
    assert metrics["failures"] == 1
    assert metrics["error_categories"]["throttled"] == 1


def test_run_with_retries_classifies_semantic_failure_reason_not_tuple_repr():
    """Classification must read the failure *reason*, not the truthy check's repr.

    `NoisyFalse` is falsy but reprs as unrelated auth-sounding noise; if
    `classify_error` were accidentally fed `repr(result[0])` instead of the
    actual reason string ("validation failed"), this test would catch the
    category coming back "auth" instead of the correct "permanent".
    """
    class NoisyFalse:
        """A falsy sentinel whose repr looks like an unrelated auth error.

        Exists to prove the retry harness classifies failures using the
        semantic reason string, not whatever `repr()` happens to say about
        the object that failed the success predicate.
        """

        def __bool__(self):
            """Report falsy, so `success_predicate=lambda r: r[0]` treats this as a failure."""
            return False

        def __repr__(self):
            """Return misleading auth-flavored text to catch reason/repr confusion."""
            return "api key noise"

    ok, value, category, latency_s, attempts = run_with_retries(
        "unit_provider_semantic_reason",
        "submit",
        lambda: (NoisyFalse(), "validation failed"),
        RetryPolicy(attempts=1, base_delay_s=0.0, max_delay_s=0.0, jitter_s=0.0),
        success_predicate=lambda result: result[0],
    )

    assert ok is False
    assert value[1] == "validation failed"
    assert category == "permanent"
    assert attempts == 1
    assert latency_s >= 0


def test_run_with_retries_latency_includes_semantic_retry_sleep():
    """Reported latency must include the sleep between semantic-failure retries.

    Asserts `latency_s >= 0.01` (the configured `base_delay_s`) so a
    latency figure that only timed the call attempts and silently dropped
    the backoff sleep can't understate real end-to-end request time in
    provider metrics.
    """
    calls = {"count": 0}

    def semantic_then_permanent():
        """Fail semantically (quota) once, then fail semantically (validation) again."""
        calls["count"] += 1
        if calls["count"] == 1:
            return (False, "quota exhausted")
        return (False, "validation failed")

    ok, value, category, latency_s, attempts = run_with_retries(
        "unit_provider_semantic_sleep_latency",
        "submit",
        semantic_then_permanent,
        RetryPolicy(attempts=2, base_delay_s=0.01, max_delay_s=0.01, jitter_s=0.0),
        success_predicate=lambda result: result[0],
    )

    assert ok is False
    assert value == (False, "validation failed")
    assert category == "permanent"
    assert attempts == 2
    assert latency_s >= 0.01


def test_run_with_retries_does_not_reuse_stale_semantic_failure_after_exception():
    """An exception on the retry must overwrite the prior semantic failure, not merge with it.

    Attempt 1 fails semantically ("throttled"); attempt 2 raises a timeout
    ("transient"). The final `category` must be "transient" -- a harness
    that kept the first attempt's category around would misreport a
    provider outage as a quota issue and page the wrong on-call runbook.
    """
    calls = {"count": 0}

    def semantic_then_exception():
        """Fail semantically (quota) once, then raise a transient timeout."""
        calls["count"] += 1
        if calls["count"] == 1:
            return (False, "quota exhausted")
        raise TimeoutError("temporary provider timeout")

    ok, value, category, latency_s, attempts = run_with_retries(
        "unit_provider_semantic_then_exception",
        "submit",
        semantic_then_exception,
        RetryPolicy(attempts=2, base_delay_s=0.0, max_delay_s=0.0, jitter_s=0.0),
        success_predicate=lambda result: result[0],
    )

    assert ok is False
    assert value is None
    assert category == "transient"
    assert attempts == 2
    assert latency_s >= 0
    metrics = provider_metrics_snapshot()["unit_provider_semantic_then_exception"]
    assert metrics["successes"] == 0
    assert metrics["failures"] == 1
    assert metrics["error_categories"]["transient"] == 1
