# WireGUI — TODO

---

## WireGuard Metrics Collector

### Overview

Separate Python process dedicated to high-frequency WireGuard stats collection, with optional VictoriaMetrics time-series storage. Replaces the current 60s in-process polling with a 5s external collector.

### Current state
- `tasks/stats.py`: polls `wg show dump` every 60s inside the web process asyncio loop
- UI timers: 30s refresh on device pages
- Worst-case latency: ~90s before a stat change is visible

### Target state
- Collector process: polls every 5s, writes to DB + VictoriaMetrics
- UI timers: 10s refresh
- Worst-case latency: ~15s

### Phase 1: Configuration ✅

- [x] Add settings to `config.py`:
  - `WG_METRICS_ENABLED: bool = False`
  - `WG_METRICS_POLL_INTERVAL: int = 5` (seconds)
  - `WG_VICTORIAMETRICS_URL: str | None = None` (e.g. `http://localhost:8428`)
- [x] When `WG_METRICS_ENABLED=false`, keep existing `stats_loop` as fallback
- [x] When `WG_METRICS_ENABLED=true`, skip registering `stats_loop` in `main.py`

### Phase 2: Collector process ✅

- [x] Create `wiregui/collector.py` — standalone entry point (`python -m wiregui.collector`)
- [x] No NiceGUI dependency — only asyncio + asyncpg + httpx
- [x] Poll `wg show <iface> dump` every `WG_METRICS_POLL_INTERVAL` seconds
- [x] Update Device rows in PostgreSQL (same fields as current `stats_loop`)
- [x] Push metrics to VictoriaMetrics via `/api/v1/import/prometheus` (if URL configured)
- [x] Graceful shutdown on SIGTERM/SIGINT
- [x] Web app spawns collector as subprocess when `WG_METRICS_ENABLED=true`
- [x] Web app terminates collector on shutdown

### Phase 3: VictoriaMetrics metrics ✅

All metrics implemented in `collector.py` and verified by integration tests:
- [x] `wiregui_peer_rx_bytes{public_key, user_email, device_name}` — counter
- [x] `wiregui_peer_tx_bytes{public_key, user_email, device_name}` — counter
- [x] `wiregui_peer_latest_handshake_seconds{public_key, user_email, device_name}` — gauge
- [x] `wiregui_peer_connected{public_key, user_email, device_name}` — 1 if handshake < 180s, else 0
- [x] `wiregui_peers_total` — gauge, count of active peers

### Phase 4: UI improvements

- [x] Reduce UI timer from 30s to 5s on all device pages (devices.py, admin/devices.py, detail page)
- [x] Add connection status indicator (green/yellow/red dot) based on handshake age
  - Green: handshake < 2 min
  - Yellow: handshake < 5 min
  - Red: no recent handshake or never connected
- [x] Status column in both user and admin device tables
- [x] Status badge on device detail page (live-updating)
- [x] Add traffic rate display (RX/s, TX/s computed from delta between 5s polls)
- [x] Device detail page: live ECharts traffic rate chart (RX/s + TX/s area lines, 60-point rolling window, auto-scaled axis with human-readable byte formatting)

### Phase 5: Infrastructure ✅

- [x] Create `compose.test.yml` — full integration stack with real WG
- [x] Add VictoriaMetrics (single-node, port 8428, 7d retention)
- [x] Add 3 mock WG client containers (alpine + wireguard-tools)
- [x] Clients generate traffic by pinging each other through the tunnel every 3s
- [x] Setup script (`docker/mock-clients/setup.py`) generates keypairs and configs
- [x] Collector runs as subprocess inside the WireGUI container (shares network namespace)

### Design notes

- **Why a separate process?** The `wg show` subprocess call and DB writes at 5s intervals shouldn't share the asyncio loop with the web app. A separate process ensures UI responsiveness isn't affected by stats collection.
- **Why not `run.cpu_bound`?** That uses `ProcessPoolExecutor` for one-shot CPU tasks inside request handling — not suitable for a long-running daemon. A separate entry point is cleaner.
- **VictoriaMetrics push model:** Use the Prometheus remote write API. No scrape config needed — the collector pushes directly. VictoriaMetrics is optional; the collector works fine with just PostgreSQL.
- **Backward compatible:** When `WG_METRICS_ENABLED=false` (default), everything works exactly as it does today.

---

## CI/Testing

- [ ] Fix E2E tests in CI — tests pass locally but fail in the CI container environment (stale DB reads between app subprocess and test process, Playwright can't resolve Docker service hostnames for SAML redirect). Not currently wired into `.github/workflows/dev.yml`.

## UI

- [ ] SAML provider management in Authentication tab (admin settings)
- [ ] SSO Providers on account page: add Status column, "Disconnect" action
- [ ] Admin pages (users, devices, rules): apply same card-based styling as account/settings/diagnostics

## Features

- [ ] First-run CLI setup command

## Tech debt / warnings

- [ ] Replace deprecated `datetime.utcfromtimestamp()` in `wiregui/services/wireguard.py:176` with `datetime.fromtimestamp(ts, datetime.UTC)` (scheduled for removal in a future Python version)
- [ ] Migrate from deprecated `authlib.jose` to `joserfc` (authlib will drop it before 2.0.0) — impacts `wiregui/auth/oidc.py` and related modules
- [ ] Remove unknown `main_file` option from pytest config in `pyproject.toml` (triggers `PytestConfigWarning` on every run)
- [ ] Use a ≥32-byte HMAC key in `tests/test_auth.py::test_decode_tampered_token` and `tests/test_magic_link.py::test_magic_link_token_wrong_user` to silence `InsecureKeyLengthWarning` (test-only, no production impact)