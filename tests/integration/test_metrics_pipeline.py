"""Integration test: verify metrics flow from WG clients → collector → VictoriaMetrics.

Requires the full integration stack running: make test-stack-up
Run with: make test-stack-verify  (or: uv run pytest tests/integration/ -v)
"""

import os
import time

import httpx
import pytest

VM_URL = os.environ.get("WG_VICTORIAMETRICS_URL", "http://localhost:8428")
WIREGUI_URL = os.environ.get("WG_EXTERNAL_URL", "http://localhost:13000")

EXPECTED_CLIENTS = ["test-client-1", "test-client-2", "test-client-3"]
# Wait up to this long for metrics to appear (collector runs every 5s)
MAX_WAIT = 60
POLL_INTERVAL = 5


def _vm_query(query: str) -> dict:
    """Execute an instant query against VictoriaMetrics."""
    resp = httpx.get(f"{VM_URL}/api/v1/query", params={"query": query}, timeout=5)
    resp.raise_for_status()
    return resp.json()


def _vm_series(metric: str) -> list[dict]:
    """Get all series for a metric from VictoriaMetrics."""
    resp = httpx.get(f"{VM_URL}/api/v1/series", params={"match[]": metric}, timeout=5)
    resp.raise_for_status()
    return resp.json().get("data", [])


@pytest.fixture(scope="module", autouse=True)
def check_stack_running():
    """Skip all tests if the integration stack isn't running."""
    try:
        r = httpx.get(f"{WIREGUI_URL}/api/health", timeout=3)
        if r.status_code != 200:
            pytest.skip("WireGUI not running")
    except httpx.HTTPError:
        pytest.skip("WireGUI not running — start with: make test-stack-up")

    try:
        r = httpx.get(f"{VM_URL}/health", timeout=3)
        if r.status_code != 200:
            pytest.skip("VictoriaMetrics not running")
    except httpx.HTTPError:
        pytest.skip("VictoriaMetrics not running — start with: make test-stack-up")


@pytest.fixture(scope="module")
def wait_for_metrics():
    """Wait until at least one peer metric appears in VictoriaMetrics."""
    deadline = time.time() + MAX_WAIT
    while time.time() < deadline:
        result = _vm_query("wiregui_peers_total")
        data = result.get("data", {}).get("result", [])
        if data and float(data[0].get("value", [0, "0"])[1]) > 0:
            return
        time.sleep(POLL_INTERVAL)
    pytest.fail(f"No metrics appeared in VictoriaMetrics after {MAX_WAIT}s")


def test_peers_total(wait_for_metrics):
    """wiregui_peers_total reports at least 1 active peer."""
    result = _vm_query("wiregui_peers_total")
    data = result["data"]["result"]
    assert len(data) > 0
    value = float(data[0]["value"][1])
    assert value >= 1, f"Expected at least 1 peer, got {value}"


def test_rx_bytes_per_client(wait_for_metrics):
    """Each client has wiregui_peer_rx_bytes > 0."""
    series = _vm_series("wiregui_peer_rx_bytes")
    device_names = {s.get("device_name") for s in series}

    for client in EXPECTED_CLIENTS:
        assert client in device_names, (
            f"Missing rx_bytes metric for '{client}'. "
            f"Found: {device_names}"
        )

    # Verify values are non-zero (traffic is flowing)
    for client in EXPECTED_CLIENTS:
        result = _vm_query(f'wiregui_peer_rx_bytes{{device_name="{client}"}}')
        data = result["data"]["result"]
        assert len(data) > 0, f"No rx_bytes data for {client}"
        value = float(data[0]["value"][1])
        assert value > 0, f"rx_bytes for {client} is 0 — no traffic?"


def test_tx_bytes_per_client(wait_for_metrics):
    """Each client has wiregui_peer_tx_bytes > 0."""
    for client in EXPECTED_CLIENTS:
        result = _vm_query(f'wiregui_peer_tx_bytes{{device_name="{client}"}}')
        data = result["data"]["result"]
        assert len(data) > 0, f"No tx_bytes data for {client}"
        value = float(data[0]["value"][1])
        assert value > 0, f"tx_bytes for {client} is 0 — no traffic?"


def test_handshake_per_client(wait_for_metrics):
    """Each client has a recent handshake timestamp."""
    now = time.time()
    for client in EXPECTED_CLIENTS:
        result = _vm_query(f'wiregui_peer_latest_handshake_seconds{{device_name="{client}"}}')
        data = result["data"]["result"]
        assert len(data) > 0, f"No handshake data for {client}"
        ts = float(data[0]["value"][1])
        assert ts > 0, f"Handshake timestamp for {client} is 0"
        age = now - ts
        assert age < 300, f"Handshake for {client} is {age:.0f}s old (stale?)"


def test_connected_status_per_client(wait_for_metrics):
    """Each client reports wiregui_peer_connected = 1."""
    for client in EXPECTED_CLIENTS:
        result = _vm_query(f'wiregui_peer_connected{{device_name="{client}"}}')
        data = result["data"]["result"]
        assert len(data) > 0, f"No connected status for {client}"
        value = int(float(data[0]["value"][1]))
        assert value == 1, f"Client {client} not connected (wiregui_peer_connected={value})"


def test_db_devices_have_stats():
    """Verify device rows in PostgreSQL also have updated stats."""
    import asyncio
    from sqlmodel import select
    from wiregui.db import async_session, engine
    from wiregui.models.device import Device

    async def check():
        async with async_session() as session:
            result = await session.execute(
                select(Device).where(Device.name.in_(EXPECTED_CLIENTS))
            )
            devices = result.scalars().all()

            assert len(devices) == len(EXPECTED_CLIENTS), (
                f"Expected {len(EXPECTED_CLIENTS)} devices, found {len(devices)}"
            )

            for device in devices:
                assert device.latest_handshake is not None, (
                    f"Device {device.name} has no handshake in DB"
                )
                assert device.rx_bytes is not None and device.rx_bytes > 0, (
                    f"Device {device.name} has no rx_bytes in DB"
                )
        await engine.dispose()

    asyncio.run(check())
