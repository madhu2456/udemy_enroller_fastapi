"""Tests for the coupon-checker loop /health endpoint (F-ENRL-C15).

scripts/ is not a Python package, so the module is loaded by path — the same
mechanism scripts/coupon_checker_loop.py uses for coupon_checker.py. The
health server binds an ephemeral port (COUPON_CHECKER_HEALTH_PORT=0) so tests
never collide with a live checker on 8001.
"""

import importlib.util
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

_LOOP_PATH = Path(__file__).resolve().parents[1] / "scripts" / "coupon_checker_loop.py"


def _load_loop():
    spec = importlib.util.spec_from_file_location("coupon_checker_loop_tests", _LOOP_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


loop = _load_loop()


@pytest.fixture()
def health_server(monkeypatch):
    monkeypatch.setenv("COUPON_CHECKER_HEALTH_PORT", "0")
    state = loop.HealthState()
    server = loop._start_health_server(state)
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    yield base_url, state
    server.shutdown()
    server.server_close()


def _get(url: str, timeout: float = 5.0) -> tuple[int, dict | None]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def test_health_ok_with_age(health_server):
    base_url, state = health_server
    state.mark_started()
    state.mark_finished()
    status, body = _get(f"{base_url}/health")
    assert status == 200
    assert body["status"] == "ok"
    assert isinstance(body["last_run_age_seconds"], int)
    assert body["last_run_age_seconds"] >= 0


def test_health_ok_when_cycle_still_running(health_server):
    """Started but not finished: age measured from cycle start, still fresh."""
    base_url, state = health_server
    state.mark_started()
    status, body = _get(f"{base_url}/health")
    assert status == 200
    assert body["status"] == "ok"


def test_health_stale_when_no_run_ever(health_server):
    """No cycle ever started → no baseline age → stale (503)."""
    base_url, _ = health_server
    status, body = _get(f"{base_url}/health")
    assert status == 503
    assert body["status"] == "stale"
    assert body["last_run_age_seconds"] is None


def test_health_stale_after_26h(health_server):
    """A successful cycle finished more than 26h ago → stale (503)."""
    base_url, state = health_server
    state.mark_started()
    state.mark_finished()
    with state._lock:
        state._finished_at = time.time() - 27 * 3600
    status, body = _get(f"{base_url}/health")
    assert status == 503
    assert body["status"] == "stale"
    assert body["last_run_age_seconds"] > 26 * 3600


def test_health_unknown_path_404(health_server):
    base_url, _ = health_server
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(f"{base_url}/nope", timeout=5.0)
    assert excinfo.value.code == 404
