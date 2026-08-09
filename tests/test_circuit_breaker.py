import time

from prash.circuit_breaker import CircuitBreaker


def _breaker(tmp_path, max_actions=3, window=10):
    return CircuitBreaker(max_actions=max_actions, window_seconds=window, path=tmp_path / "circuit.json")


def test_closed_until_cap_reached(tmp_path):
    b = _breaker(tmp_path)
    assert b.is_open("acme/api") is False
    b.record("acme/api")
    b.record("acme/api")
    assert b.is_open("acme/api") is False
    b.record("acme/api")
    assert b.is_open("acme/api") is True


def test_open_is_per_resource(tmp_path):
    b = _breaker(tmp_path)
    for _ in range(3):
        b.record("acme/api")
    assert b.is_open("acme/api") is True
    assert b.is_open("other/svc") is False


def test_window_expiry_closes(tmp_path):
    b = _breaker(tmp_path)
    b.record("acme/api")
    b._state["acme/api"] = [time.time() - b.window_seconds - 1]
    assert b.is_open("acme/api") is False


def test_reset_resource_and_all(tmp_path):
    b = _breaker(tmp_path)
    for _ in range(3):
        b.record("acme/api")
        b.record("other/svc")
    assert b.is_open("acme/api") and b.is_open("other/svc")
    b.reset("acme/api")
    assert b.is_open("acme/api") is False
    assert b.is_open("other/svc") is True
    b.reset()
    assert b.is_open("other/svc") is False


def test_state_persists_across_instances(tmp_path):
    path = tmp_path / "circuit.json"
    b1 = CircuitBreaker(max_actions=2, window_seconds=10, path=path)
    b1.record("acme/api")
    b1.record("acme/api")
    b2 = CircuitBreaker(max_actions=2, window_seconds=10, path=path)
    assert b2.is_open("acme/api") is True
