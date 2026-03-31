# WireGUI — Pending Items

**Test count: 268 (198 unit + 70 E2E) | Coverage: 36% unit, ~63% effective (incl. E2E)**

---

## Testing

# WireGUI Implementation TODO

Migration of Wirezone (Elixir/Phoenix) to Python/NiceGUI.
Source: `/home/stefanob/PycharmProjects/personal/wirezone`

**Test count: 268 (198 unit + 70 E2E) | Coverage: 36% unit, ~63% effective (incl. E2E)**
**Run:** `uv run pytest` (unit) / `uv run pytest tests/e2e/` (E2E via Playwright)


## Phase 7: Admin UI ✅

- [ ] **TODO:** SAML provider management in Authentication tab

## Phase 10: Polish, Testing & Deployment

### Testing (partially done)
- [ ] HTTP-level integration tests (OIDC redirect/callback flow with respx mocking)
- [x] `wiregui/api/deps.py` (11 tests) — resolve_bearer_token (valid/expired/invalid/disabled/no-expiry), get_current_api_user (missing header/bad scheme/invalid token/valid token), require_admin (admin/unprivileged)
- [x] `wiregui/services/wireguard.py` (6 tests) — ensure_interface (exists/creates new), set_private_key, set_listen_port, configure_interface (no config/sets key+port)
- [x] `wiregui/services/firewall.py` (17 tests) — _nft error/success, _nft_batch error/stdin, add_device_jump_rule (ipv4-only/ipv6-only/no-ips/both), setup_base_tables error handling, masquerade error, peer-to-peer/lan-to-peers policies, get_ruleset fallback
- [ ] `wiregui/tasks/oidc_refresh.py` — test successful refresh, failure with notification, disable_vpn_on_oidc_error
- [x] `wiregui/auth/saml.py` — full SAML flow tested via mock SimpleSAMLphp IdP (e2e)
- [ ] `wiregui/auth/webauthn.py` — test verify_registration, verify_authentication with mock credential data
- [ ] E2E tests for admin pages (users, devices, rules, settings)

**E2E page tests (Playwright async API in `tests/e2e/`):**
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

**E2E tests still needed:**

`tests/e2e/test_login.py` — Login & Auth flows (remaining):
- [x] Login with MFA → redirects to /mfa challenge page
- [x] MFA challenge: valid TOTP code → completes login
- [x] MFA challenge: invalid code → shows error, stays on /mfa
- [x] MFA challenge: cancel → returns to /login
- [x] Magic link request page renders, shows success on submit

`tests/e2e/test_admin_devices.py` — Admin Device Management:
- [x] List all devices across users
- [x] Filter by user → shows only that user's devices
- [x] Create device with full config overrides (DNS, endpoint, MTU, keepalive, allowed IPs)
- [x] Create device with defaults → use_default flags all True
- [x] Edit device name and description → persists
- [x] Edit device config overrides (toggle use_default off, set custom values)
- [x] Delete device → removed from table
- [x] Config dialog shows valid WireGuard config with real server public key
- [x] QR code renders in config dialog

`tests/e2e/test_admin_rules.py` — Admin Firewall Rules:
- [x] List rules → table shows action, destination, protocol, port, user
- [x] Create accept rule with CIDR → appears in table
- [x] Create drop rule with TCP port range → appears correctly
- [x] Create global rule (no user) → shows "Global"
- [x] Edit rule action (accept → drop) → persists
- [x] Edit rule destination → persists
- [x] Delete rule → removed from table

`tests/e2e/test_admin_settings.py` — Admin Settings:
- [x] Client defaults: save endpoint, DNS, MTU, keepalive, allowed IPs → persists in DB
- [x] Client defaults: saved values reflected on page reload
- [x] Security: toggle local auth → persists
- [x] Security: change VPN session duration → persists
- [x] Security: toggle unprivileged device management/configuration → persists
- [x] OIDC: add provider → appears in table
- [x] OIDC: delete provider → removed from table
- [x] SAML: add provider → appears in table
- [x] SAML: delete provider → removed from table

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

## UI

- [ ] SSO Providers on account page: add Status column, "Disconnect" action
- [ ] Admin pages (users, devices, rules): apply same card-based styling as account/settings/diagnostics
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


## Features

### Deployment ✅

- [ ] First-run CLI setup command

---

### Remaining
- [ ] SSO Providers: add Status column, "Disconnect" action
- [ ] Admin pages (users, devices, rules): apply same card-based styling
