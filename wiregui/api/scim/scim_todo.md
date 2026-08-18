# SCIM provisioning — todo (see scim_design.md for detail)

## Phase 1 — schema & auth
- [ ] Add `users.external_id` and `configurations.scim_token_hash` + migration
- [ ] SCIM bearer-token dependency (404 when unconfigured, 401 on mismatch)
- [ ] Admin settings UI: generate/revoke SCIM token

## Phase 2 — endpoints
- [ ] Static documents: ServiceProviderConfig, Schemas, ResourceTypes
- [ ] GET /Users with `userName eq` filter + pagination; GET /Users/{id}
- [ ] POST /Users (create, 409 on duplicate)
- [ ] PUT + PATCH /Users/{id} (incl. `active` handling)
- [ ] DELETE /Users/{id} via delete_user_and_cleanup

## Phase 3 — deactivation semantics
- [ ] `set_user_active` service: disable removes WG peers, enable re-adds
- [ ] Apply same semantics to admin-UI disable toggle

## Phase 4 — tests & docs
- [ ] Unit tests: CRUD, filter, active toggle, auth failures
- [ ] E2E: full lifecycle with simulated Authentik SCIM client
- [ ] Manual acceptance against homelab Authentik
- [ ] Website feature card + Authentik setup docs
