# WireGUI — Pending Items

**Test count: 174 (164 unit + 10 E2E) | Coverage: ~35%**

---

## Testing

# WireGUI Implementation TODO

Migration of Wirezone (Elixir/Phoenix) to Python/NiceGUI.
Source: `/home/stefanob/PycharmProjects/personal/wirezone`

**Test count: 199 (164 unit + 35 E2E) | Coverage: 35%**
**Run:** `uv run pytest` (unit) / `uv run pytest tests/e2e/` (E2E via Playwright)


## Phase 7: Admin UI ✅

- [ ] **TODO:** SAML provider management in Authentication tab

## Phase 10: Polish, Testing & Deployment

### Testing (partially done)
- [ ] HTTP-level integration tests (OIDC redirect/callback flow with respx mocking)
- [ ] `wiregui/api/deps.py` — test get_current_api_user with real Bearer header parsing, require_admin rejection
- [ ] `wiregui/services/wireguard.py` — test ensure_interface, set_private_key, set_listen_port
- [ ] `wiregui/services/firewall.py` — test _nft/_nft_batch error handling, add_device_jump_rule with only ipv4/ipv6
- [ ] `wiregui/tasks/oidc_refresh.py` — test successful refresh, failure with notification, disable_vpn_on_oidc_error
- [ ] `wiregui/auth/saml.py` (0%) — needs mock SAML IdP metadata + response parsing
- [ ] `wiregui/auth/webauthn.py` — test verify_registration, verify_authentication with mock credential data
- [ ] E2E tests for admin pages (users, devices, rules, settings)

**E2E page tests (Playwright async API in `tests/e2e/`):**
- [x] `tests/e2e/test_login.py` (6 tests) — valid login, invalid password, nonexistent email, disabled user, logout, unauthenticated redirect
- [x] `tests/e2e/test_devices.py` (2 tests) — add device full flow, name validation
- [x] `tests/e2e/test_account.py` (8 tests) — change password (success/wrong/mismatch/short), create API token, TOTP registration + invalid code, account deletion
- [x] `tests/e2e/test_admin_users.py` (10 tests) — page renders, create user, duplicate email, edit role/password, disable/enable, delete, cascade delete, self-delete guard
- [x] `tests/e2e/test_idp_seed.py` (9 tests) — IdP YAML seeding (noop/missing/invalid, OIDC/SAML add, upsert, preserve), OIDC button visible, full OIDC login flow via mock-oidc

**E2E tests still needed:**

`tests/e2e/test_login.py` — Login & Auth flows (remaining):
- [ ] Login with MFA → redirects to /mfa challenge page
- [ ] MFA challenge: valid TOTP code → completes login
- [ ] MFA challenge: invalid code → shows error, stays on /mfa
- [ ] MFA challenge: cancel → returns to /login
- [ ] Magic link request page renders, shows success on submit

`tests/e2e/test_admin_devices.py` — Admin Device Management:
- [ ] List all devices across users
- [ ] Filter by user → shows only that user's devices
- [ ] Create device with full config overrides (DNS, endpoint, MTU, keepalive, allowed IPs)
- [ ] Create device with defaults → use_default flags all True
- [ ] Edit device name and description → persists
- [ ] Edit device config overrides (toggle use_default off, set custom values)
- [ ] Delete device → removed from table
- [ ] Config dialog shows valid WireGuard config with real server public key
- [ ] QR code renders in config dialog

`tests/e2e/test_admin_rules.py` — Admin Firewall Rules:
- [ ] List rules → table shows action, destination, protocol, port, user
- [ ] Create accept rule with CIDR → appears in table
- [ ] Create drop rule with TCP port range → appears correctly
- [ ] Create global rule (no user) → shows "Global"
- [ ] Edit rule action (accept → drop) → persists
- [ ] Edit rule destination → persists
- [ ] Delete rule → removed from table

`tests/e2e/test_admin_settings.py` — Admin Settings:
- [ ] Client defaults: save endpoint, DNS, MTU, keepalive, allowed IPs → persists in DB
- [ ] Client defaults: saved values reflected on page reload
- [ ] Security: toggle local auth → persists
- [ ] Security: change VPN session duration → persists
- [ ] Security: toggle unprivileged device management/configuration → persists
- [ ] OIDC: add provider → appears in table
- [ ] OIDC: delete provider → removed from table
- [ ] SAML: add provider → appears in table
- [ ] SAML: delete provider → removed from table

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
