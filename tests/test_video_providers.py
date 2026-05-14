from video_providers import ProviderRegistry


def noop_provider():
    return "ok"


def test_register_skips_provider_when_required_env_missing(monkeypatch):
    monkeypatch.delenv("BOTTUBE_TEST_PROVIDER_KEY", raising=False)
    registry = ProviderRegistry()

    registry.register("missing-key-provider", noop_provider, "BOTTUBE_TEST_PROVIDER_KEY")

    assert registry.status() == []
    assert registry.get_ordered("job-1") == []


def test_register_includes_provider_when_required_env_present(monkeypatch):
    monkeypatch.setenv("BOTTUBE_TEST_PROVIDER_KEY", "enabled")
    registry = ProviderRegistry()

    registry.register("keyed-provider", noop_provider, "BOTTUBE_TEST_PROVIDER_KEY")

    assert registry.get_ordered("job-1") == [("keyed-provider", noop_provider)]
    assert registry.status()[0]["name"] == "keyed-provider"


def test_failures_hide_provider_until_cooldown_expires():
    registry = ProviderRegistry()
    registry.register("flaky", noop_provider)

    for _ in range(registry.FAIL_THRESHOLD):
        registry.report_failure("flaky")

    status = registry.status()[0]
    assert status["healthy"] is False
    assert status["fail_count"] == registry.FAIL_THRESHOLD
    assert registry.get_ordered("job-1") == []

    registry._providers["flaky"]["last_failure_time"] -= registry.COOLDOWN_SECS + 1

    assert registry.get_ordered("job-1") == [("flaky", noop_provider)]


def test_health_check_restores_provider_after_cooldown():
    registry = ProviderRegistry()
    registry.register("recovering", noop_provider)

    for _ in range(registry.FAIL_THRESHOLD):
        registry.report_failure("recovering")
    registry._providers["recovering"]["last_failure_time"] -= registry.COOLDOWN_SECS + 1

    registry.health_check()

    status = registry.status()[0]
    assert status["healthy"] is True
    assert status["fail_count"] == 0


def test_report_success_resets_failures_and_updates_latency_average():
    registry = ProviderRegistry()
    registry.register("fast", noop_provider)
    registry.report_failure("fast")

    registry.report_success("fast", 0.100)
    registry.report_success("fast", 0.200)

    status = registry.status()[0]
    assert status["healthy"] is True
    assert status["fail_count"] == 0
    assert status["success_count"] == 2
    assert status["avg_latency_ms"] == 130
