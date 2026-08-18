# SCIM provisioning — design

## Goal

Close the deprovisioning gap left after issue #7: deleting or deactivating a user
in the IdP (Authentik) today leaves the WireGUI account, its devices and its
**live WireGuard peers** untouched — the user can no longer log in to the UI, but
their VPN tunnels keep working indefinitely. WireGUI will implement a SCIM 2.0
server (RFC 7643/7644 subset) so the IdP can push create / update / deactivate /
delete events, making the IdP the lifecycle authority for federated users.

## Chosen approach

A FastAPI router mounted at `/scim/v2`, Users resource only, authenticated by a
dedicated provisioning bearer token. Authentik's outbound **SCIM provider** is
pointed at it (Authentik pushes full syncs and incremental events; WireGUI stays
passive).

### Endpoints (phase 1)

| Endpoint | Behavior |
|---|---|
| `GET /scim/v2/ServiceProviderConfig` | static capability document (no bulk, no sort, filter: `eq` only, patch: true) |
| `GET /scim/v2/Schemas`, `/ResourceTypes` | static minimal documents for the User schema |
| `GET /scim/v2/Users` | list; supports `filter=userName eq "<email>"` and `startIndex`/`count` pagination (Authentik uses the filter to match existing users before creating) |
| `GET /scim/v2/Users/{id}` | fetch one |
| `POST /scim/v2/Users` | create (or 409 on existing `userName`, per RFC) |
| `PUT /scim/v2/Users/{id}` | full replace |
| `PATCH /scim/v2/Users/{id}` | partial update — must at minimum handle `active` and `userName`/`emails` changes |
| `DELETE /scim/v2/Users/{id}` | delete via `delete_user_and_cleanup` (cascade + WG peer teardown) |

### Attribute mapping

- `userName` ⇔ `User.email` — WireGUI keys users by email everywhere (OIDC login
  matches on email), so `userName` and the primary entry of `emails` both map to
  it. On conflict between the two, `userName` wins.
- `externalId` → new column `users.external_id` (nullable, unique). SCIM `id`
  returned to the IdP is WireGUI's user UUID. Lookups by Authentik use the
  filter on `userName`, so `external_id` is stored for traceability, not lookup.
- `active: false` → set `disabled_at` (see deactivation semantics below);
  `active: true` → clear it.
- `displayName`/`name` — accepted and ignored (no such fields in the model;
  adding them is out of scope).

### Deactivation semantics (the security-relevant decision)

`active: false` **removes the user's WireGuard peers immediately** (fires
`on_device_deleted` per device) in addition to setting `disabled_at`. Device
*rows* are kept, and re-activation re-adds the peers (`on_device_created`).
Rationale: the entire point of IdP-driven deprovisioning is cutting network
access; merely blocking UI login (what `disabled_at` alone does today) leaves
tunnels alive. Rejected: treating deactivate as UI-disable only — silently fails
the threat model that motivates SCIM. The same peer-removal-on-disable behavior
should also apply when an admin disables a user in the UI, for consistency
(small behavioral change, called out in release notes).

### Authentication

A dedicated SCIM bearer token: generated from the admin Settings page, stored
hashed (same scheme as `api_tokens`) in a new `configurations.scim_token_hash`
column. Constant-time comparison; 401 with a SCIM error body on mismatch; the
whole router returns 404 when no token is configured (feature off by default).
Rejected: reusing user `api_tokens` — those are tied to a user account with user
lifecycle and role semantics; a provisioning credential must survive any user's
deletion. Rejected: OAuth client-credentials — Authentik's SCIM provider only
does static tokens.

### SCIM-created users

Created with `password_hash = None`, role `unprivileged` — identical to OIDC
auto-create. They sign in through the OIDC provider. SCIM never touches
passwords or roles (role escalation stays a WireGUI-admin action; Groups-based
role mapping is deferred with Groups support).

## Rejected alternatives

- **Polling the Authentik API** for deleted users — couples WireGUI to one IdP's
  API and credentials; SCIM is the standard designed for exactly this.
- **OIDC back-channel logout** — kills sessions, not accounts; no deprovisioning.
- **Relying on `tasks/oidc_refresh.py` token-refresh failures** — only works when
  a refresh token was issued (`offline_access` scope) and reacts late; keep it as
  defense-in-depth, not the mechanism.
- **Groups resource in phase 1** — WireGUI has two roles; group→role mapping is
  real scope creep and Authentik works fine pushing Users only.

## Files touched

- `wiregui/models/user.py` — add `external_id` column
- `wiregui/models/configuration.py` — add `scim_token_hash`
- `alembic/versions/<rev>_add_scim_support.py` — the two columns
- `wiregui/api/scim/` — new package: `router.py` (endpoints), `schemas.py`
  (SCIM request/response models), `auth.py` (bearer dependency)
- `wiregui/services/users.py` — add `set_user_active(session, user, active)`
  (peer teardown/re-add); reuse `delete_user_and_cleanup`
- `wiregui/main.py` — mount the router
- `wiregui/pages/admin/settings.py` — SCIM token generate/revoke UI
- `tests/test_scim.py`, `tests/e2e/test_scim_provisioning.py`
- `website/` — feature card + Authentik setup snippet

## Verification

1. Unit: endpoint CRUD against the test DB — create, filter lookup, PATCH
   `active` both ways, DELETE cascades (reuses issue #7 fixtures); auth: no
   token configured → 404, wrong token → 401.
2. E2E: simulated Authentik client (httpx, real payload shapes captured from an
   Authentik SCIM sync) driving the full lifecycle: provision → OIDC login →
   deactivate (assert WG peer gone via `wg show` on WG-enabled test stack, or
   event-fire assertion) → reactivate → delete.
3. Manual acceptance on the homelab: point Authentik's SCIM provider at the VPN
   host, delete the test user in Authentik, confirm the WireGUI user disappears
   and `wg show` drops the peer.

## Deploy & blast radius

Additive schema migration; endpoints return 404 until an admin generates a SCIM
token, so existing deployments are unaffected. The one behavior change —
disable-also-removes-peers — is deliberate and documented above.
