# WireGUI — Test Suite

**Test count: 271 (201 unit + 70 E2E) | Unit coverage: 36% | Effective: ~81% (incl. E2E)**
**Run:** `uv run pytest` (unit) / `uv run pytest tests/e2e/` (E2E via Playwright)

---

## Unit Tests — Coverage by Module

**Done:**
- [x] `wiregui/api/deps.py` (91%) — 11 tests: Bearer token auth, get_current_api_user, require_admin
- [x] `wiregui/services/wireguard.py` (98%) — 6 tests: ensure_interface, set_private_key, set_listen_port, configure_interface
- [x] `wiregui/services/firewall.py` (94%) — 17 tests: _nft/_nft_batch errors, jump rules, policies, get_ruleset
- [x] `wiregui/auth/api_token.py` (100%) — covered via test_api_deps.py
- [x] `wiregui/auth/saml.py` — full SAML flow tested via mock SimpleSAMLphp IdP (e2e)
- [x] `wiregui/utils/server_key.py` (100%) — 3 tests: returns key, raises when missing, raises when empty

**Remaining unit test gaps (by coverage):**
- [ ] `wiregui/auth/seed.py` (29%) — test seed_admin, seed_idp_providers with various YAML configs, ensure_server_keypair
- [ ] `wiregui/tasks/__init__.py` (35%) — test register_task, cancel_all
- [ ] `wiregui/tasks/oidc_refresh.py` (40%) — test successful refresh, failure with notification, disable_vpn_on_oidc_error
- [ ] `wiregui/api/v0/configuration.py` (55%) — test GET/PUT configuration endpoints
- [ ] `wiregui/api/v0/devices.py` (65%) — test CRUD device API endpoints
- [ ] `wiregui/api/v0/rules.py` (70%) — test CRUD rule API endpoints
- [ ] `wiregui/tasks/connectivity.py` (72%) — test connectivity check loop
- [ ] `wiregui/utils/network.py` (73%) — test IPv6 allocation, edge cases in CIDR validation
- [ ] `wiregui/tasks/stats.py` (74%) — test WG stats polling loop
- [ ] `wiregui/tasks/vpn_session.py` (77%) — test session expiry loop
- [ ] `wiregui/auth/webauthn.py` (87%) — test verify_registration, verify_authentication with mock credential data
- [ ] `wiregui/auth/middleware.py` (0%) — test NiceGUI auth middleware redirect logic

---

## E2E Tests (Playwright)

**Completed test suites:**
- [x] `tests/e2e/test_login.py` (6 tests) — valid login, invalid password, nonexistent email, disabled user, logout, unauthenticated redirect
- [x] `tests/e2e/test_devices.py` (2 tests) — add device full flow, name validation
- [x] `tests/e2e/test_account.py` (8 tests) — change password (success/wrong/mismatch/short), create API token, TOTP registration + invalid code, account deletion
- [x] `tests/e2e/test_admin_users.py` (10 tests) — page renders, create user, duplicate email, edit role/password, disable/enable, delete, cascade delete, self-delete guard
- [x] `tests/e2e/test_idp_seed.py` (9 tests) — IdP YAML seeding (noop/missing/invalid, OIDC/SAML add, upsert, preserve), OIDC button visible, full OIDC login flow via mock-oidc
- [x] `tests/e2e/test_mfa_login.py` (4 tests) — MFA redirect on login, valid TOTP completes login, invalid code error, cancel returns to login
- [x] `tests/e2e/test_magic_link_page.py` (4 tests) — page renders, success on submit, empty email error, back to login
- [x] `tests/e2e/test_admin_devices.py` (7 tests) — list all devices, filter by user, create with defaults, create with overrides, edit name/description, delete, config dialog with QR
- [x] `tests/e2e/test_admin_rules.py` (7 tests) — list rules table, create accept/drop/global rules, edit action/destination, delete rule (all verified in DB)
- [x] `tests/e2e/test_admin_settings.py` (9 tests) — client defaults save/reload, security toggles (local auth, VPN session, unprivileged), OIDC add/delete, SAML add/delete (all verified in DB)
- [x] `tests/e2e/test_saml_login.py` (4 tests) — SAML button visible, redirect to IdP, SP metadata endpoint, full SAML login flow via mock SimpleSAMLphp

**Remaining E2E test suites:**

`tests/e2e/test_admin_diagnostics.py` — Admin Diagnostics:
- [ ] Page renders WireGuard interface status
- [ ] Active peers table shows devices with handshakes
- [ ] Connectivity checks table shows recent results
- [ ] Notifications list shows system notifications
- [ ] Clear single notification → removed
- [ ] Clear all notifications → list empty

`tests/e2e/test_devices_user.py` — User Device Pages:
- [ ] Device list shows only own devices (not other users')
- [ ] Create device → shows in table with allocated IPs
- [ ] Device detail page shows public key, IPs, stats, active config
- [ ] Device detail: edit name → persists
- [ ] Device detail: toggle config overrides → custom values saved
- [ ] Device detail: delete with confirmation → redirects to /devices
- [ ] Auto-refresh: stats labels update after timer fires (mock timer)

`tests/e2e/test_account_extended.py` — Account Page (additional):
- [ ] SSO providers section shows connected providers
- [ ] SSO providers section shows "No SSO providers" when empty
- [ ] MFA: add security key (WebAuthn) → method appears in table (mock navigator.credentials)
- [ ] MFA: delete method with confirmation → removed from table
- [ ] API tokens: expired token shows "Expired" badge
- [ ] API tokens: delete token → removed from table
- [ ] API tokens: copy button calls clipboard API
- [ ] Danger zone: disabled when only admin
- [ ] Danger zone: wrong email in confirmation → shows error