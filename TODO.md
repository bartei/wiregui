# WireGUI — Pending Items

**Test count: 174 (164 unit + 10 E2E) | Coverage: ~35%**

---

## Testing

- [ ] HTTP-level integration tests (OIDC redirect/callback flow with respx mocking)
- [ ] `wiregui/api/deps.py` — test get_current_api_user with real Bearer header parsing, require_admin rejection
- [ ] `wiregui/services/wireguard.py` — test ensure_interface, set_private_key, set_listen_port
- [ ] `wiregui/services/firewall.py` — test _nft/_nft_batch error handling, add_device_jump_rule with only ipv4/ipv6
- [ ] `wiregui/tasks/oidc_refresh.py` — test successful refresh, failure with notification, disable_vpn_on_oidc_error
- [ ] `wiregui/auth/saml.py` (0%) — needs mock SAML IdP metadata + response parsing
- [ ] `wiregui/auth/webauthn.py` — test verify_registration, verify_authentication with mock credential data
- [ ] E2E tests for admin pages (users, devices, rules, settings)

## UI

- [ ] SSO Providers on account page: add Status column, "Disconnect" action
- [ ] Admin pages (users, devices, rules): apply same card-based styling as account/settings/diagnostics

## Features

- [ ] First-run CLI setup command
