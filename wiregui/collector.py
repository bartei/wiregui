"""WireGuard metrics collector — standalone process for high-frequency stats polling.

Run as: python -m wiregui.collector

Polls `wg show <iface> dump` at a configurable interval, updates device rows
in PostgreSQL, and optionally pushes Prometheus-format metrics to VictoriaMetrics.
"""

import asyncio
import signal
import time

import httpx
from loguru import logger
from sqlmodel import select

from wiregui.config import get_settings
from wiregui.db import async_session, engine
from wiregui.log_config import setup_logging
from wiregui.models.device import Device
from wiregui.models.user import User
from wiregui.services.wireguard import PeerInfo, get_peers

_shutdown = asyncio.Event()


def _handle_signal() -> None:
    logger.info("Shutdown signal received")
    _shutdown.set()


async def _update_db(peers: list[PeerInfo]) -> dict[str, dict]:
    """Update device rows in DB and return metadata for metrics labels.

    Returns: {public_key: {"device_name": ..., "user_email": ...}}
    """
    if not peers:
        return {}

    peer_map = {p.public_key: p for p in peers}

    async with async_session() as session:
        result = await session.execute(
            select(Device, User.email).join(User).where(
                Device.public_key.in_(list(peer_map.keys()))
            )
        )
        rows = result.all()

        labels = {}
        updated = 0
        for device, user_email in rows:
            peer = peer_map.get(device.public_key)
            if peer is None:
                continue
            # Only write connection status to PostgreSQL — traffic metrics go to VictoriaMetrics
            device.latest_handshake = peer.latest_handshake
            device.remote_ip = peer.endpoint.split(":")[0] if peer.endpoint else None
            device.rx_bytes = peer.rx_bytes
            device.tx_bytes = peer.tx_bytes
            session.add(device)
            updated += 1
            labels[device.public_key] = {
                "device_name": device.name,
                "user_email": user_email,
            }

        if updated:
            await session.commit()
            logger.debug("Updated stats for {} devices", updated)

    return labels


def _build_prometheus_payload(peers: list[PeerInfo], labels: dict[str, dict]) -> str:
    """Build Prometheus exposition format text for VictoriaMetrics import."""
    now_ms = int(time.time() * 1000)
    lines = []
    active_count = 0

    for peer in peers:
        meta = labels.get(peer.public_key)
        if not meta:
            continue

        tag = (
            f'public_key="{peer.public_key[:16]}",'
            f'device_name="{meta["device_name"]}",'
            f'user_email="{meta["user_email"]}"'
        )

        lines.append(f"wiregui_peer_rx_bytes{{{tag}}} {peer.rx_bytes} {now_ms}")
        lines.append(f"wiregui_peer_tx_bytes{{{tag}}} {peer.tx_bytes} {now_ms}")

        handshake_ts = int(peer.latest_handshake.timestamp()) if peer.latest_handshake else 0
        lines.append(f"wiregui_peer_latest_handshake_seconds{{{tag}}} {handshake_ts} {now_ms}")

        connected = 1 if (handshake_ts and (time.time() - handshake_ts) < 180) else 0
        lines.append(f"wiregui_peer_connected{{{tag}}} {connected} {now_ms}")

        if connected:
            active_count += 1

    lines.append(f"wiregui_peers_total {active_count} {now_ms}")
    return "\n".join(lines) + "\n"


async def _push_metrics(client: httpx.AsyncClient, url: str, payload: str) -> None:
    """Push Prometheus-format metrics to VictoriaMetrics."""
    try:
        resp = await client.post(
            f"{url}/api/v1/import/prometheus",
            content=payload,
            headers={"Content-Type": "text/plain"},
        )
        if resp.status_code >= 400:
            logger.warning("VictoriaMetrics push failed (HTTP {}): {}", resp.status_code, resp.text[:200])
    except httpx.HTTPError as e:
        logger.warning("VictoriaMetrics push error: {}", e)


async def run() -> None:
    """Main collector loop."""
    settings = get_settings()
    interval = settings.metrics_poll_interval
    vm_url = settings.victoriametrics_url

    logger.info(
        "Collector started: interval={}s, victoriametrics={}",
        interval, vm_url or "disabled",
    )

    client = httpx.AsyncClient(timeout=5) if vm_url else None

    try:
        while not _shutdown.is_set():
            try:
                peers = await get_peers()
                labels = await _update_db(peers)

                if client and vm_url and peers:
                    payload = _build_prometheus_payload(peers, labels)
                    await _push_metrics(client, vm_url, payload)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Collector poll failed: {}", e)

            try:
                await asyncio.wait_for(_shutdown.wait(), timeout=interval)
                break  # shutdown signalled
            except asyncio.TimeoutError:
                pass  # normal — interval elapsed, loop again
    finally:
        if client:
            await client.aclose()
        await engine.dispose()
        logger.info("Collector stopped")


def main() -> None:
    setup_logging(log_to_file=get_settings().log_to_file)

    loop = asyncio.new_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal)

    try:
        loop.run_until_complete(run())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
