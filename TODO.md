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

### Phase 3: VictoriaMetrics metrics

Metrics to push (Prometheus exposition format):
- [ ] `wiregui_peer_rx_bytes{public_key, user_email, device_name}` — counter
- [ ] `wiregui_peer_tx_bytes{public_key, user_email, device_name}` — counter
- [ ] `wiregui_peer_latest_handshake_seconds{public_key, user_email, device_name}` — gauge
- [ ] `wiregui_peer_connected{public_key, user_email, device_name}` — 1 if handshake < 180s, else 0
- [ ] `wiregui_peers_total` — gauge, count of active peers

### Phase 4: UI improvements

- [ ] Reduce UI timer from 30s to 10s on device pages (devices.py, admin/devices.py)
- [ ] Add connection status indicator (green/yellow/red dot) based on handshake age
  - Green: handshake < 2 min
  - Yellow: handshake < 5 min
  - Red: no recent handshake or never connected
- [ ] Add traffic rate display (bytes/sec computed from delta between polls)
- [ ] Device detail page: mini traffic chart (query VictoriaMetrics if available, else show last-known values)

### Phase 5: Infrastructure ✅

- [x] Create `compose.test.yml` — full integration stack with real WG
- [x] Add VictoriaMetrics (single-node, port 8428, 7d retention)
- [x] Add 3 mock WG client containers (alpine + wireguard-tools)
- [x] Clients generate traffic by pinging each other through the tunnel every 3s
- [x] Setup script (`docker/mock-clients/setup.py`) generates keypairs and configs
- [x] Collector runs as subprocess inside the WireGUI container (shares network namespace)
- [ ] Add VictoriaMetrics to dev `compose.yml` (optional, for local testing)

### Design notes

- **Why a separate process?** The `wg show` subprocess call and DB writes at 5s intervals shouldn't share the asyncio loop with the web app. A separate process ensures UI responsiveness isn't affected by stats collection.
- **Why not `run.cpu_bound`?** That uses `ProcessPoolExecutor` for one-shot CPU tasks inside request handling — not suitable for a long-running daemon. A separate entry point is cleaner.
- **VictoriaMetrics push model:** Use the Prometheus remote write API. No scrape config needed — the collector pushes directly. VictoriaMetrics is optional; the collector works fine with just PostgreSQL.
- **Backward compatible:** When `WG_METRICS_ENABLED=false` (default), everything works exactly as it does today.

---

## UI

- [ ] SAML provider management in Authentication tab (admin settings)
- [ ] SSO Providers on account page: add Status column, "Disconnect" action
- [ ] Admin pages (users, devices, rules): apply same card-based styling as account/settings/diagnostics

## Features

- [ ] First-run CLI setup command