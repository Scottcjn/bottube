import time

from generation.reliability import RetryPolicy, classify_error, provider_metrics_snapshot, run_with_retries


def test_classify_error_categories():
    """classify_error maps auth/throttle/transient/permanent markers to their categories."""
    assert classify_error("401 unauthorized api key") == "auth"
    assert classify_error("429 rate limit exceeded") == "throttled"
    assert classify_error(TimeoutError("request timed out")) == "transient"
    assert classify_error("validation failed: bad prompt") == "permanent"


def test_run_with_retries_retries_transient_then_succeeds():
    """A transient failure is retried and the run succeeds on a later attempt."""
    calls = {"count": 0}

    def flaky():
        """Callable that raises transiently for the first attempt then succeeds."""
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
    """Auth errors are not retried; the run fails immediately in the auth category."""
    calls = {"count": 0}

    def auth_failure():
        """Callable that always raises an auth-classified error."""
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
    """A (False, reason) result is recorded as a semantic failure rather than success."""
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
    """The semantic failure reason is used for classification, not the tuple repr."""
    class NoisyFalse:
        def __bool__(self):
            """Falsy value that prevents the tuple itself from being truthy."""
            return False

        def __repr__(self):
            """Readable repr carrying the classification marker ('api key noise')."""
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
    """Latency accounts for the sleep before a semantic retry, not just the exceptions."""
    calls = {"count": 0}

    def semantic_then_permanent():
        """Callable returning a semantic failure first, then a permanent one."""
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
    """A stale semantic failure is not reused for classification after a later exception."""
    calls = {"count": 0}

    def semantic_then_exception():
        """Callable returning a semantic failure first, then raising a transient exception."""
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
