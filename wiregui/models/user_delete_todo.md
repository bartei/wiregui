# User deletion cascade — todo (see user_delete_design.md for detail)

## Phase 1 — schema
- [x] Add `ondelete="CASCADE"` to the five child model FKs
- [x] Add `passive_deletes="all"` to User relationships
- [x] Write alembic migration recreating the five FK constraints
- [x] Apply migration to dev DB and inspect constraints

## Phase 2 — delete paths
- [x] Add `services/users.py` with `delete_user_and_cleanup`
- [x] Use helper in admin users page
- [x] Use helper in REST users delete endpoint
- [x] Use helper in account self-delete

## Phase 3 — tests
- [x] Unit test fixtures: user with all five child row types
- [x] Unit tests: DB cascade, helper, API endpoint
- [x] E2E: admin deletes OIDC-auto-created user via UI (issue #7 repro)
- [x] Full suite green (unit + e2e)
