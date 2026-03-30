# WireGUI Implementation TODO

Migration of Wirezone (Elixir/Phoenix) to Python/NiceGUI.
Source: `/home/stefanob/PycharmProjects/personal/wirezone`

**Test count: 164 passing | Coverage: 35%**

---

## Phase 1: Foundation — Models, DB, Config ✅

- [x] `pyproject.toml` with dependencies, `uv sync`
- [x] Package directory structure
- [x] `wiregui/config.py` — pydantic-settings (DB, Redis, WG, auth, SMTP, logging)
- [x] `wiregui/db.py` — async engine, sessionmaker, `init_db()`
- [x] `wiregui/redis.py` — Valkey connection pool
- [x] All 8 SQLModel models (User, Device, Rule, MFAMethod, OIDCConnection, ApiToken, ConnectivityCheck, Configuration)
- [x] Alembic init + initial migration + `alembic upgrade head`
- [x] `wiregui/main.py` — app entrypoint
- [x] `compose.yml` — PostgreSQL 17 + Valkey 8
- [x] `wiregui/utils/time.py` — `utcnow()` helper for naive UTC timestamps

---

## Phase 2: Auth System — Login + Sessions ✅

- [x] `wiregui/auth/passwords.py` — bcrypt hash/verify (direct bcrypt, not passlib)
- [x] `wiregui/auth/jwt.py` — create/decode JWT via python-jose
- [x] `wiregui/auth/session.py` — `authenticate_user()` email/password verification
- [x] `wiregui/auth/middleware.py` — HTTP-level auth middleware (available for REST API)
- [x] `wiregui/auth/seed.py` — auto-create admin on first startup
- [x] `wiregui/pages/login.py` — login page with email/password form
- [x] `wiregui/pages/home.py` — authenticated home (redirects to /devices)
- [x] Auth guards via `app.storage.user` on each page
- [x] Logout clears storage and redirects

---

## Phase 3: Device UI — User-Facing CRUD ✅

- [x] `wiregui/pages/layout.py` — shared sidebar + header
- [x] `wiregui/utils/network.py` — IPv4/IPv6 allocation (random offset + scan)
- [x] `wiregui/utils/crypto.py` — WG keypair + PSK generation via `wg` CLI
- [x] `wiregui/utils/wg_conf.py` — WG client `.conf` builder
- [x] `wiregui/pages/devices.py` — `/devices` list + create dialog + delete
- [x] `/devices/{device_id}` — detail page with stats and config flags
- [x] QR code generation + `.conf` download
- [x] Full device create/edit form with all wirezone options (description, per-device config overrides, use_default_* toggles with bound inputs, better layout)

---

## Phase 4: WireGuard Integration ✅

- [x] `wiregui/services/wireguard.py` — async subprocess: ensure_interface, add/remove_peer, get_peers, set_private_key, set_listen_port
- [x] `wiregui/services/events.py` — event bridge: device CRUD → WG + firewall
- [x] Device create/delete in UI fires WG events
- [x] `wiregui/tasks/__init__.py` — background task registry + cancel_all
- [x] `wiregui/tasks/stats.py` — poll WG stats every 60s, update DB
- [x] `wiregui/tasks/reconcile.py` — startup reconciliation (diff DB vs WG, add/remove)
- [x] `config.py` — `wg_enabled` flag (default False for dev)
- [x] Startup: ensure_interface → reconcile → stats_loop (when wg_enabled)

---

## Phase 5: Firewall (nftables) ✅

- [x] `wiregui/services/firewall.py` — nft CLI: setup_base_tables, masquerade, per-user chains, jump rules, apply_rule, rebuild_all_rules
- [x] IPv4/IPv6 aware, TCP/UDP port range support
- [x] `wiregui/pages/admin/rules.py` — `/admin/rules` CRUD (action, CIDR, protocol, port, user)
- [x] Events: on_rule_created/deleted, on_device_created adds jump rules
- [x] Startup: setup_base_tables + setup_masquerade (when wg_enabled)
- [x] Edit rule — edit dialog in admin rules page with all fields
- [x] Full user chain rebuild on rule update/delete via `_rebuild_user_chain()` in events.py

---

## Phase 6: REST API (v0) ✅

- [x] `wiregui/auth/api_token.py` — token generation (random → sha256), Bearer resolution with expiry + disabled user checks
- [x] `wiregui/api/deps.py` — get_db, get_current_api_user, require_admin
- [x] `wiregui/schemas/` — Pydantic schemas: UserRead/Create/Update, DeviceRead/Create/Update, RuleRead/Create/Update, ConfigurationRead/Update
- [x] `wiregui/api/v0/users.py` — full CRUD (admin only)
- [x] `wiregui/api/v0/devices.py` — full CRUD (owner or admin, triggers WG/firewall events)
- [x] `wiregui/api/v0/rules.py` — full CRUD (admin only, triggers firewall events)
- [x] `wiregui/api/v0/configuration.py` — GET/PUT (admin only, auto-creates singleton)
- [x] Mounted on NiceGUI app at `/api/v0`

---

## Phase 7: Admin UI ✅

- [x] `/admin/users` — table (email, role, devices, status, last sign-in, method, created), create (email/password/role), edit (email/role/password/disabled), delete with cascading cleanup (devices → WG events, rules)
- [x] `/admin/devices` — all devices with user filter, full create form (owner, name, description, all use_default_* toggles with bound override inputs), full edit form, delete with WG events, config + QR on creation
- [x] `/admin/settings` — 3 tabs:
  - Client Defaults (endpoint, DNS, allowed IPs, MTU, keepalive)
  - Security (VPN session duration, local auth, unpriv device mgmt/config, OIDC auto-disable)
  - Authentication (OIDC provider CRUD with table + dialog; SAML placeholder for Phase 8)
- [x] `/admin/diagnostics` — WG interface status, active peers, connectivity checks, system notifications with clear/clear-all
- [x] `wiregui/services/notifications.py` — in-memory deque (capped at 100), add/clear/count/current
- [x] Header notification bell badge (admin only, links to diagnostics)
- [ ] **TODO:** SAML provider management in Authentication tab

---

## Phase 8: Advanced Auth (MFA, OIDC, Magic Links, SAML) ✅

- [x] TOTP MFA (`wiregui/auth/mfa.py`) — secret generation, URI/QR, verification with clock drift tolerance
- [x] MFA challenge page (`/mfa`) — 6-digit code entry, multi-method support, last-used tracking
- [x] Login page updated: checks for MFA methods after password auth, redirects to `/mfa` if present
- [x] OIDC (`wiregui/auth/oidc.py`) — provider registry from Configuration, authlib Starlette integration
- [x] OIDC routes (`/auth/oidc/{provider}` + `/auth/oidc/{provider}/callback`) — auth code flow, user lookup/auto-create, refresh token storage in OIDCConnection
- [x] Login page shows OIDC provider buttons dynamically from config
- [x] OIDC refresh task (`wiregui/tasks/oidc_refresh.py`) — every 10min, refreshes all stored tokens, creates notifications on failure, respects `disable_vpn_on_oidc_error`
- [x] Magic links (`/auth/magic-link` + `/auth/magic/{user_id}/{token}`) — request page, signed JWT with 15min expiry, email via aiosmtplib
- [x] Email service (`wiregui/services/email.py`) — aiosmtplib send, magic link template
- [x] `/account` page — 3 tabs: Profile (details + password change), Two-Factor Auth (TOTP registration with QR + verification, list/delete methods), API Tokens (create with configurable expiry, list, delete)
- [x] OIDC providers registered on startup from Configuration
- [x] WebAuthn MFA (`wiregui/auth/webauthn.py`) — registration/authentication options generation, response verification, credential storage
- [x] SAML (`wiregui/auth/saml.py` + `wiregui/pages/auth_saml.py`) — SP-initiated SSO, metadata endpoint, ACS callback, IdP metadata parsing, attribute mapping
- [x] WebAuthn browser-side JS integration in account page — `ui.run_javascript()` calls `navigator.credentials.create()`, serializes response, server verifies and stores credential
- [x] SAML provider management UI in admin settings Authentication tab — table + add/delete dialog (config ID, label, XML metadata, sign requests/metadata/assertions/envelopes toggles, auto-create users)

---

## Phase 9: Background Tasks & VPN Session Management

- [x] Task scheduler (`wiregui/tasks/__init__.py`) — register/cancel
- [x] Stats polling task (Phase 4)
- [x] OIDC refresh task (Phase 8)
- [x] VPN session expiry task (`wiregui/tasks/vpn_session.py`) — every 60s, finds expired sessions based on `vpn_session_duration` + `last_signed_in_at`, removes WG peers, creates notifications
- [x] Connectivity check poller (`wiregui/tasks/connectivity.py`) — fetches URL, stores result in DB, notification on failure
- [x] Live stats push — `ui.timer(30, ...)` on `/devices` (table refresh), `/devices/{id}` (RX/TX/handshake/remote IP labels), `/admin/devices` (table refresh)

---

## Phase 10: Polish, Testing & Deployment

### Testing (partially done)
- [x] pytest + pytest-asyncio setup, conftest with test DB
- [x] test_models.py (10 tests), test_auth.py (8 tests), test_utils.py (6 tests), test_services.py (6 tests), test_firewall.py (7 tests)
- [x] test_api.py (6 tests) — token generation, resolution, expiry, disabled user
- [x] test_notifications.py (9 tests) — add, ordering, count, clear, max cap, to_dict
- [x] test_admin.py (13 tests) — user CRUD, cascading deletes, config CRUD, OIDC providers, device overrides
- [x] test_mfa.py (11 tests) — TOTP secret gen, URI, code verification (valid/invalid/wrong secret/empty), QR SVG, DB integration, multi-method
- [x] test_magic_link.py (4 tests) — token creation/expiry/user mismatch, disabled user rejection
- [x] test_account.py (8 tests) — password change flow, API token CRUD, OIDC connection CRUD, refresh token update
- [x] test_integration_mfa.py (7 tests) — full TOTP registration flow, MFA blocks login, wrong code, multi-method, last-used tracking, delete allows bypass, disabled user
- [x] test_integration_oidc.py (10 tests) — provider config loading, connection create/update, auto-create user, disabled user, refresh token, multi-provider
- [x] test_tasks.py (6 tests) — VPN session expiry (expired/unlimited/no-config/disabled user), connectivity check (success/failure with notification)
- [ ] HTTP-level integration tests (OIDC redirect/callback flow with respx mocking)

### Coverage gaps (35% overall — run `uv run pytest --cov=wiregui --cov-report=term-missing --cov-branch`)

**100% covered:** models, schemas, config, auth/passwords, auth/jwt, auth/mfa, auth/api_token, utils/crypto, utils/time, services/notifications

**API routes (32-84% — partially covered via httpx TestClient):**
- [x] `wiregui/api/v0/users.py` (84%) — list/get/create/update/delete
- [x] `wiregui/api/v0/rules.py` (71%) — CRUD
- [x] `wiregui/api/v0/devices.py` (67%) — CRUD, permissions
- [x] `wiregui/api/v0/configuration.py` (61%) — get/update, auto-create
- [ ] `wiregui/api/deps.py` (32%) — test get_current_api_user with real Bearer header parsing, require_admin rejection

**Services (62-89% covered):**
- [x] `wiregui/services/wireguard.py` (62%) — add/remove/get peers mocked
- [x] `wiregui/services/firewall.py` (73%) — base tables, chains, rules, rebuild mocked
- [x] `wiregui/services/events.py` (80%) — device + rule events, rebuild chain
- [x] `wiregui/services/email.py` (89%) — send_email, magic link, no-smtp fallback
- [ ] `wiregui/services/wireguard.py` — test ensure_interface, set_private_key, set_listen_port
- [ ] `wiregui/services/firewall.py` — test _nft/_nft_batch error handling, add_device_jump_rule with only ipv4/ipv6

**Tasks (40-84% covered):**
- [x] `wiregui/tasks/stats.py` (77%) — update from peers, no-op, unmatched peer
- [x] `wiregui/tasks/reconcile.py` (84%) — add missing, remove orphaned, in-sync
- [x] `wiregui/tasks/oidc_refresh.py` (40%) — no connections, skip unknown provider
- [ ] `wiregui/tasks/oidc_refresh.py` — test successful refresh, failure with notification, disable_vpn_on_oidc_error

**Auth modules (85-92% covered):**
- [x] `wiregui/auth/oidc.py` (87%) — register providers, get_client, load from config
- [x] `wiregui/auth/webauthn.py` (85%) — registration/authentication options
- [x] `wiregui/auth/session.py` (90%) — no-password, disabled, nonexistent user
- [ ] `wiregui/auth/saml.py` (0%) — needs mock SAML IdP metadata + response parsing
- [ ] `wiregui/auth/webauthn.py` — test verify_registration, verify_authentication with mock credential data

**Pages (0% — requires E2E testing):**
- [ ] Consider Playwright or NiceGUI's testing utilities for E2E page tests

### Logging (done)
- [x] Loguru configured (wiregui/logging.py), no print statements
- [x] File logging to `logs/` when `WG_LOG_TO_FILE=true`

### Deployment
- [ ] Dockerfile (multi-stage)
- [ ] compose.prod.yml (app + postgres + valkey + caddy)
- [ ] Health endpoint `GET /api/health`
- [ ] First-run CLI setup command
- [ ] README.md
