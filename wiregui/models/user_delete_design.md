# User deletion cascade — design

Fixes [issue #7](https://github.com/bartei/wiregui/issues/7): deleting an
OIDC-auto-created user from `/admin/users` silently does nothing.

## Root cause

All five child tables reference `users.id` with foreign keys created **without any
`ON DELETE` behavior** (initial migration `647a4418cc8c`):

| table              | `user_id` nullable | cleaned up by admin delete? |
|--------------------|--------------------|-----------------------------|
| `devices`          | no                 | yes (explicit, fires WG events) |
| `rules`            | yes (global rules) | yes (explicit)              |
| `mfa_methods`      | no                 | **no**                      |
| `api_tokens`       | no                 | **no**                      |
| `oidc_connections` | no                 | **no**                      |

An OIDC login **always** creates an `oidc_connections` row (`pages/auth_oidc.py`
callback), so an OIDC-created user can never be deleted by the admin page: the
`session.delete(user)` flush fails (SQLAlchemy tries to null out non-nullable child
FKs / Postgres raises a FK violation), the exception aborts the NiceGUI handler,
and the Delete button appears to "do nothing". The REST `DELETE /api/v0/users/{id}`
endpoint has the same failure for *any* user with child rows since it deletes
nothing explicitly.

Latent related bug: the account-page self-delete removes child rows explicitly but
never fires `on_device_deleted`, so WireGuard peers/routes of the deleted user's
devices stayed configured until restart.

## Chosen approach

**DB-level `ON DELETE CASCADE` on all five FKs**, plus a single shared deletion
helper that handles the one side-effect the database cannot: WireGuard peer
removal.

1. **Models** — `Field(..., foreign_key="users.id", ondelete="CASCADE")` on the five
   child models, and `passive_deletes="all"` on the corresponding `User`
   relationships so the ORM emits a single `DELETE FROM users` and lets Postgres
   cascade (no lazy-load of children during flush — required anyway under asyncio,
   where implicit lazy loads raise `MissingGreenlet`). Requires sqlmodel ≥ 0.0.22
   for the `ondelete` Field param; we're on 0.0.37.
2. **Migration** (`alembic/versions/*_user_fk_cascade.py`) — drop and recreate the
   five FK constraints with `ondelete="CASCADE"`. The initial migration created them
   unnamed, so they carry Postgres default names (`devices_user_id_fkey`, …).
   Downgrade restores plain FKs.
3. **Shared helper** `wiregui/services/users.py::delete_user_and_cleanup(session, user)`
   — snapshots the user's devices, deletes the user (DB cascades everything),
   commits, **then** fires `on_device_deleted` per device (after commit is safer
   than the previous before-commit ordering: WG state only changes once the DB
   delete is durable). Used by:
   - `pages/admin/users.py::delete_user` (the reported bug)
   - `api/v0/users.py::delete_user` (same bug + now gets WG cleanup)
   - `pages/account.py` self-delete (gets WG cleanup, loses hand-rolled child loop)

## Decisions & rationale

- **CASCADE for `rules` too (not SET NULL).** Only user-owned rules have
  `user_id`; global rules are NULL and unaffected. Both existing delete paths
  already deleted the user's rules explicitly, so CASCADE preserves behavior.
  SET NULL would silently convert personal rules into global ones — a security
  hazard.
- **DB cascade over application-level deletes (rejected).** This bug *is* an
  application-level delete path missing tables; every future child table would
  need N delete paths updated. The FK does it atomically and covers ad-hoc
  deletions too.
- **Keep explicit device snapshot in the helper.** WG peer removal is an external
  side-effect Postgres can't cascade; devices are read before the delete so events
  can fire after commit.

## Files touched

- `wiregui/models/{device,rule,mfa_method,api_token,oidc_connection}.py` — `ondelete="CASCADE"`
- `wiregui/models/user.py` — `passive_deletes="all"` on the five relationships
- `alembic/versions/<rev>_user_fk_cascade.py` — new migration
- `wiregui/services/users.py` — new `delete_user_and_cleanup`
- `wiregui/pages/admin/users.py`, `wiregui/api/v0/users.py`, `wiregui/pages/account.py` — use helper
- `tests/test_user_deletion.py` — fixtures + unit tests (cascade, helper, API endpoint)
- `tests/e2e/test_oidc_user_delete.py` — acceptance test reproducing issue #7

## Deploy & blast radius

- `alembic upgrade head` (Docker image already runs it on start). The migration
  only swaps FK constraints — instant, no data rewrite, no downtime concern.
- Behavior change: deleting a user now *actually deletes* MFA methods, API tokens
  and OIDC connections that previously blocked deletion. That is the intended
  semantics of the admin Delete button.

## Verification

1. `uv run pytest tests/test_user_deletion.py` — cascade + helper unit tests pass.
2. `uv run pytest tests/e2e/test_oidc_user_delete.py` — full repro: OIDC login via
   mock-oidc auto-creates user; admin deletes it from `/admin/users`; row gone,
   zero child rows left. (Needs `docker compose up -d postgres valkey mock-oidc`
   and a migrated DB.)
3. Existing suites stay green: `uv run pytest` and `uv run pytest tests/e2e`.
4. Manual: `alembic upgrade head` then
   `psql -c "\d devices"` shows `ON DELETE CASCADE` on `devices_user_id_fkey`.
